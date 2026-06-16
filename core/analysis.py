"""
Cortex Analysis Engine — stateless computation functions.

All functions take a kuzu.Connection and/or a project root Path.
They return plain Python dicts/lists — no FastAPI or MCP imports.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import kuzu


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rows(result: Any) -> list[dict]:
    rows = []
    cols = result.get_column_names()
    while result.has_next():
        rows.append(dict(zip(cols, result.get_next())))
    return rows


def _all_node_docs(conn: kuzu.Connection) -> list[dict]:
    """Return id, name, label, description for every node in the graph."""
    from core.graph_api import NODE_TABLES
    docs = []
    for table in NODE_TABLES:
        try:
            r = conn.execute(
                f"MATCH (n:{table}) RETURN n.id AS id, n.name AS name, n.description AS description"
            )
            for row in _rows(r):
                docs.append({
                    "id": row.get("id") or "",
                    "name": row.get("name") or "",
                    "label": table,
                    "text": (row.get("name") or "") + " " + (row.get("description") or ""),
                })
        except Exception:
            pass
    return docs


def _tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())


# ---------------------------------------------------------------------------
# Pulse Search
# ---------------------------------------------------------------------------

def pulse_search(conn: kuzu.Connection, query: str, top_n: int = 20) -> list[dict]:
    """
    TF-IDF ranked node search across name + description of all nodes.

    Returns list of {id, name, label, score} sorted by descending score.
    Returns [] when query is empty or no matches found.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    docs = _all_node_docs(conn)
    if not docs:
        return []

    N = len(docs)
    df: dict[str, int] = defaultdict(int)
    tokenized: list[list[str]] = []

    for doc in docs:
        tokens = _tokenize(doc["text"])
        tokenized.append(tokens)
        for t in set(tokens):
            df[t] += 1

    idf = {t: math.log((N + 1) / (df[t] + 1)) + 1.0 for t in df}

    results = []
    for doc, tokens in zip(docs, tokenized):
        if not tokens:
            continue
        tf: dict[str, int] = defaultdict(int)
        for t in tokens:
            tf[t] += 1
        total = len(tokens)
        score = sum(
            (tf[qt] / total) * idf.get(qt, 0.0)
            for qt in query_tokens
            if qt in tf
        )
        if score > 0:
            results.append({
                "id": doc["id"],
                "name": doc["name"],
                "label": doc["label"],
                "score": round(score, 6),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_n]


# ---------------------------------------------------------------------------
# Keystones
# ---------------------------------------------------------------------------

def get_keystones(conn: kuzu.Connection, top_n: int = 10) -> list[dict]:
    """
    Return top-N nodes by total edge degree (in + out), highest first.

    Returns list of {id, name, label, degree}.
    """
    from core.graph_api import NODE_TABLES, REL_TABLES

    node_meta: dict[str, dict] = {}
    for table in NODE_TABLES:
        try:
            r = conn.execute(f"MATCH (n:{table}) RETURN n.id AS id, n.name AS name")
            for row in _rows(r):
                nid = row.get("id")
                if nid:
                    node_meta[nid] = {"id": nid, "name": row.get("name") or "", "label": table}
        except Exception:
            pass

    degree: dict[str, int] = defaultdict(int)
    for rel in REL_TABLES:
        try:
            r = conn.execute(f"MATCH (a)-[:{rel}]->(b) RETURN a.id AS src, b.id AS dst")
            for row in _rows(r):
                if row.get("src"):
                    degree[row["src"]] += 1
                if row.get("dst"):
                    degree[row["dst"]] += 1
        except Exception:
            pass

    ranked = sorted(
        node_meta.values(),
        key=lambda n: degree.get(n["id"], 0),
        reverse=True,
    )[:top_n]

    for n in ranked:
        n["degree"] = degree.get(n["id"], 0)
    return ranked


# ---------------------------------------------------------------------------
# Signal Clusters
# ---------------------------------------------------------------------------

_CLUSTER_PALETTE = [
    "#3b82f6", "#7c3aed", "#ea580c", "#059669", "#dc2626",
    "#0891b2", "#d97706", "#be185d", "#15803d", "#92400e",
]


def detect_signal_clusters(
    conn: kuzu.Connection,
    project_root: Path,
    resolution: float = 1.0,
) -> list[dict]:
    """
    Detect node communities using the Leiden algorithm (leidenalg + igraph required).
    Falls back to BFS connected components if leidenalg is not installed.

    Writes .cortex/clusters.json. Returns the clusters list directly.
    Cache is considered fresh if the file is newer than the latest snapshot unix_ts,
    or if no versions.json exists (treat cache as always fresh).
    """
    from core.graph_api import NODE_TABLES, REL_TABLES

    cortex_dir = project_root / ".cortex"
    clusters_path = cortex_dir / "clusters.json"
    meta_path = cortex_dir / "versions.json"

    # Staleness check: return cached data if file is newer than latest snapshot
    if clusters_path.exists():
        if not meta_path.exists():
            # No snapshot history — treat cache as always fresh
            return json.loads(clusters_path.read_text())["clusters"]
        meta = json.loads(meta_path.read_text())
        versions = meta.get("versions", [])
        if versions:
            latest_ts = max(v.get("unix_ts", 0.0) for v in versions)
            if clusters_path.stat().st_mtime > latest_ts:
                return json.loads(clusters_path.read_text())["clusters"]

    # Build node index
    node_ids: list[str] = []
    node_index: dict[str, int] = {}
    for table in NODE_TABLES:
        try:
            r = conn.execute(f"MATCH (n:{table}) RETURN n.id AS id")
            for row in _rows(r):
                nid = row.get("id")
                if nid and nid not in node_index:
                    node_index[nid] = len(node_ids)
                    node_ids.append(nid)
        except Exception:
            pass

    if not node_ids:
        return []

    # Build edge pairs
    edge_pairs: list[tuple[int, int]] = []
    for rel in REL_TABLES:
        try:
            r = conn.execute(f"MATCH (a)-[:{rel}]->(b) RETURN a.id AS src, b.id AS dst")
            for row in _rows(r):
                s, d = row.get("src"), row.get("dst")
                if s in node_index and d in node_index:
                    edge_pairs.append((node_index[s], node_index[d]))
        except Exception:
            pass

    # Community detection — Leiden or BFS fallback
    try:
        import igraph as ig
        import leidenalg
        g = ig.Graph(n=len(node_ids), edges=edge_pairs, directed=False)
        partition = leidenalg.find_partition(
            g,
            leidenalg.RBConfigurationVertexPartition,
            resolution_parameter=resolution,
        )
        membership = partition.membership
    except ImportError:
        # BFS connected components
        adj: dict[int, list[int]] = defaultdict(list)
        for s, d in edge_pairs:
            adj[s].append(d)
            adj[d].append(s)
        membership = [-1] * len(node_ids)
        cluster_id = 0
        for start in range(len(node_ids)):
            if membership[start] != -1:
                continue
            queue = [start]
            while queue:
                cur = queue.pop()
                if membership[cur] != -1:
                    continue
                membership[cur] = cluster_id
                queue.extend(adj[cur])
            cluster_id += 1

    # Group nodes by cluster
    cluster_map: dict[int, list[str]] = defaultdict(list)
    for i, cid in enumerate(membership):
        if cid >= 0:
            cluster_map[cid].append(node_ids[i])

    clusters = [
        {
            "id": cid,
            "label": f"Cluster {cid}",
            "color": _CLUSTER_PALETTE[cid % len(_CLUSTER_PALETTE)],
            "members": members,
        }
        for cid, members in sorted(cluster_map.items())
    ]

    cortex_dir.mkdir(exist_ok=True)
    clusters_path.write_text(json.dumps({
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "clusters": clusters,
    }, indent=2))
    return clusters


# ---------------------------------------------------------------------------
# Latent Bridges
# ---------------------------------------------------------------------------

def get_latent_bridges(
    conn: kuzu.Connection,
    project_root: Path,
    top_n: int = 20,
) -> list[dict]:
    """
    Find edges that cross cluster boundaries — surprising cross-section connections.

    Returns [] if .cortex/clusters.json has not been generated yet.
    Returns list of {src, dst, rel, src_cluster, dst_cluster}.
    """
    from core.graph_api import REL_TABLES

    clusters_path = project_root / ".cortex" / "clusters.json"
    if not clusters_path.exists():
        return []

    cluster_data = json.loads(clusters_path.read_text())
    node_to_cluster: dict[str, int] = {}
    for c in cluster_data["clusters"]:
        for member in c["members"]:
            node_to_cluster[member] = c["id"]

    bridges = []
    for rel in REL_TABLES:
        try:
            r = conn.execute(
                f"MATCH (a)-[:{rel}]->(b) RETURN a.id AS src, b.id AS dst"
            )
            for row in _rows(r):
                src, dst = row.get("src"), row.get("dst")
                if not src or not dst:
                    continue
                sc = node_to_cluster.get(src)
                dc = node_to_cluster.get(dst)
                if sc is not None and dc is not None and sc != dc:
                    bridges.append({
                        "src": src,
                        "dst": dst,
                        "rel": rel,
                        "src_cluster": sc,
                        "dst_cluster": dc,
                    })
        except Exception:
            pass

    return bridges[:top_n]


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def ledger_write(
    project_root: Path,
    feature: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """Append a cost entry to .cortex/ledger.jsonl."""
    cortex_dir = project_root / ".cortex"
    cortex_dir.mkdir(exist_ok=True)
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "feature": feature,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }
    with (cortex_dir / "ledger.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Cortex Brief
# ---------------------------------------------------------------------------

def generate_brief(conn: kuzu.Connection, project_root: Path) -> str:
    """
    Generate a markdown project summary with no LLM required.

    Includes node counts by type, SystemDesign nodes grouped by section,
    and the three most recent snapshots.
    """
    from core.graph_api import NODE_TABLES

    lines = ["# Cortex Project Brief\n", f"**Project:** `{project_root.name}`\n"]

    lines.append("## Node Counts\n")
    total = 0
    for table in NODE_TABLES:
        try:
            r = conn.execute(f"MATCH (n:{table}) RETURN count(*) AS c")
            count = 0
            if r.has_next():
                count = r.get_next()[0]
            lines.append(f"- **{table}**: {count}")
            total += count
        except Exception:
            pass
    lines.append(f"\n**Total**: {total} nodes\n")

    lines.append("## Architecture Sections\n")
    try:
        r = conn.execute(
            "MATCH (n:SystemDesign) RETURN n.section AS section, n.name AS name, n.status AS status"
        )
        rows = _rows(r)
        sections: dict[str, list] = {}
        for row in rows:
            sec = row.get("section") or "Unsectioned"
            sections.setdefault(sec, []).append(row)
        for sec, nodes in sorted(sections.items()):
            lines.append(f"### {sec}")
            for n in nodes:
                lines.append(f"- [{n.get('status', '?')}] {n.get('name', '?')}")
            lines.append("")
    except Exception:
        pass

    meta_path = project_root / ".cortex" / "versions.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        versions = list(reversed(meta.get("versions", [])))[:3]
        if versions:
            lines.append("## Recent Snapshots\n")
            for v in versions:
                lines.append(f"- `{v['timestamp'][:19]}` — {v['message']}")

    return "\n".join(lines)
