# Cortex v2 — Phase 2: Analysis Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `core/analysis.py` with six functions (Pulse Search, Keystones, Signal Clusters, Latent Bridges, Ledger, Cortex Brief), wire them into new REST endpoints on the web server, and expose four as MCP tools.

**Architecture:** `core/analysis.py` is a pure computation module — it takes a Kùzu connection and/or a project root Path, and returns plain Python data. No FastAPI imports, no MCP imports. REST endpoints in `web_server.py` call analysis functions. MCP tools in `mcp_server.py` call the same functions. Signal Clusters writes a cache file `.cortex/clusters.json` and uses staleness checking instead of explicit invalidation.

**Tech Stack:** Python 3.11+ (math, re, json, collections.defaultdict), Kùzu, FastMCP, FastAPI. Optional: `leidenalg`, `python-igraph` (for Signal Clusters; BFS connected-components fallback when absent).

**Prerequisites:** Phase 1 must be complete (Group in NODE_TABLES, MEMBER_OF in REL_TABLES, trail.jsonl infrastructure).

---

## Task 1: Pulse Search (TF-IDF node search)

**Files:**
- Create: `core/analysis.py`
- Create: `tests/test_analysis.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_analysis.py`:

```python
import pytest
from pathlib import Path
from core.db import DatabaseManager


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    yield m
    m.close()


def _seed(mgr):
    mgr.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth_handler', description: 'handles authentication tokens', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "CREATE (n:File {id: 'f2', name: 'payment_processor', description: 'processes stripe payments', "
        "code_block: '', file_path: 'pay.py', language: 'python', source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "CREATE (n:File {id: 'f3', name: 'auth_middleware', description: 'authentication middleware layer', "
        "code_block: '', file_path: 'mid.py', language: 'python', source_file: '', source_line: 0})"
    )


def test_pulse_search_returns_matching_nodes(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "authentication")
    ids = [r["id"] for r in results]
    assert "f1" in ids
    assert "f3" in ids


def test_pulse_search_ranks_by_score(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "authentication")
    assert len(results) >= 2
    assert results[0]["score"] >= results[1]["score"]


def test_pulse_search_excludes_no_match(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "authentication")
    ids = [r["id"] for r in results]
    assert "f2" not in ids


def test_pulse_search_empty_query(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "")
    assert results == []
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_analysis.py::test_pulse_search_returns_matching_nodes -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'core.analysis'`

- [ ] **Step 3: Create core/analysis.py with pulse_search**

```python
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
```

- [ ] **Step 4: Run pulse_search tests**

```bash
pytest tests/test_analysis.py -k "pulse_search" -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/analysis.py tests/test_analysis.py
git commit -m "feat(analysis): Pulse Search — TF-IDF node search in core/analysis.py"
```

---

## Task 2: Keystones

**Files:**
- Modify: `core/analysis.py` — add `get_keystones`
- Modify: `tests/test_analysis.py` — add keystone tests

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analysis.py`:

```python
def _seed_with_edges(mgr):
    """Seed 3 nodes; f1 has 2 edges (highest degree), f2 has 1, f3 has 0."""
    _seed(mgr)
    mgr.conn.execute(
        "CREATE (n:Service {id: 'sv1', name: 'Stripe', description: 'Payments', "
        "code_block: '', service_type: 'third_party', endpoint: 'https://api.stripe.com', "
        "source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "MATCH (f:File {id: 'f1'}), (s:Service {id: 'sv1'}) CREATE (f)-[:TALKS_TO {protocol: 'HTTPS'}]->(s)"
    )
    mgr.conn.execute(
        "MATCH (f:File {id: 'f2'}), (s:Service {id: 'sv1'}) CREATE (f)-[:TALKS_TO {protocol: 'HTTPS'}]->(s)"
    )


def test_keystones_returns_top_n(mgr):
    from core.analysis import get_keystones
    _seed_with_edges(mgr)
    results = get_keystones(mgr.conn, top_n=3)
    assert len(results) <= 3


def test_keystones_ranked_by_degree(mgr):
    from core.analysis import get_keystones
    _seed_with_edges(mgr)
    results = get_keystones(mgr.conn, top_n=10)
    # sv1 has 2 incoming edges — highest degree
    assert results[0]["id"] == "sv1"
    assert results[0]["degree"] >= 2


def test_keystones_includes_degree_field(mgr):
    from core.analysis import get_keystones
    _seed_with_edges(mgr)
    results = get_keystones(mgr.conn, top_n=5)
    for r in results:
        assert "degree" in r
        assert "id" in r
        assert "name" in r
        assert "label" in r
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_analysis.py -k "keystone" -v
```
Expected: FAIL — `ImportError: cannot import name 'get_keystones' from 'core.analysis'`

- [ ] **Step 3: Add get_keystones to core/analysis.py**

```python
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
```

- [ ] **Step 4: Run keystone tests**

```bash
pytest tests/test_analysis.py -k "keystone" -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/analysis.py tests/test_analysis.py
git commit -m "feat(analysis): Keystones — degree-ranked god nodes"
```

---

## Task 3: Signal Clusters (Community Detection)

**Files:**
- Modify: `core/analysis.py` — add `detect_signal_clusters`
- Modify: `tests/test_analysis.py` — add cluster tests

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analysis.py`:

```python
def test_signal_clusters_returns_list(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    _seed_with_edges(mgr)
    clusters = detect_signal_clusters(mgr.conn, tmp_path)
    assert isinstance(clusters, list)
    assert len(clusters) >= 1


def test_signal_clusters_each_has_required_fields(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    _seed_with_edges(mgr)
    clusters = detect_signal_clusters(mgr.conn, tmp_path)
    for c in clusters:
        assert "id" in c
        assert "label" in c
        assert "color" in c
        assert "members" in c
        assert isinstance(c["members"], list)


def test_signal_clusters_writes_cache_file(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    _seed_with_edges(mgr)
    detect_signal_clusters(mgr.conn, tmp_path)
    cache = tmp_path / ".cortex" / "clusters.json"
    assert cache.exists()
    data = json.loads(cache.read_text())
    assert "generated_at" in data
    assert "clusters" in data


def test_signal_clusters_uses_cache_when_fresh(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    import time
    _seed_with_edges(mgr)
    # First call writes the cache
    detect_signal_clusters(mgr.conn, tmp_path)
    cache = tmp_path / ".cortex" / "clusters.json"
    mtime_before = cache.stat().st_mtime
    time.sleep(0.05)
    # Second call should return cached data without re-running
    detect_signal_clusters(mgr.conn, tmp_path)
    mtime_after = cache.stat().st_mtime
    assert mtime_after == mtime_before
```

Also add `import json` at the top of `tests/test_analysis.py`.

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_analysis.py -k "cluster" -v
```
Expected: FAIL — `ImportError: cannot import name 'detect_signal_clusters'`

- [ ] **Step 3: Add detect_signal_clusters to core/analysis.py**

```python
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
    Cache is considered fresh if the file is newer than the latest snapshot unix_ts.
    """
    from core.graph_api import NODE_TABLES, REL_TABLES

    cortex_dir = project_root / ".cortex"
    clusters_path = cortex_dir / "clusters.json"
    meta_path = cortex_dir / "versions.json"

    # Staleness check: return cached data if file is newer than latest snapshot
    if clusters_path.exists() and meta_path.exists():
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
```

- [ ] **Step 4: Run cluster tests**

```bash
pytest tests/test_analysis.py -k "cluster" -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add core/analysis.py tests/test_analysis.py
git commit -m "feat(analysis): Signal Clusters — community detection with Leiden/BFS fallback"
```

---

## Task 4: Latent Bridges + Ledger + Cortex Brief

**Files:**
- Modify: `core/analysis.py` — add `get_latent_bridges`, `ledger_write`, `generate_brief`
- Modify: `tests/test_analysis.py` — add tests for each

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_analysis.py`:

```python
def test_latent_bridges_returns_empty_without_clusters(mgr, tmp_path):
    from core.analysis import get_latent_bridges
    results = get_latent_bridges(mgr.conn, tmp_path)
    assert results == []


def test_latent_bridges_finds_cross_cluster_edges(mgr, tmp_path):
    from core.analysis import detect_signal_clusters, get_latent_bridges
    _seed_with_edges(mgr)
    detect_signal_clusters(mgr.conn, tmp_path)
    results = get_latent_bridges(mgr.conn, tmp_path)
    assert isinstance(results, list)
    for r in results:
        assert "src" in r
        assert "dst" in r
        assert "rel" in r
        assert r["src_cluster"] != r["dst_cluster"]


def test_ledger_write_appends_to_file(tmp_path):
    from core.analysis import ledger_write
    cortex_dir = tmp_path / ".cortex"
    cortex_dir.mkdir()
    ledger_write(tmp_path, "signal-clusters", "claude-sonnet-4-6", 1000, 500, 0.003)
    ledger_path = cortex_dir / "ledger.jsonl"
    assert ledger_path.exists()
    entry = json.loads(ledger_path.read_text().strip())
    assert entry["feature"] == "signal-clusters"
    assert entry["model"] == "claude-sonnet-4-6"
    assert entry["input_tokens"] == 1000
    assert entry["cost_usd"] == 0.003
    assert "ts" in entry


def test_ledger_write_accumulates(tmp_path):
    from core.analysis import ledger_write
    (tmp_path / ".cortex").mkdir()
    ledger_write(tmp_path, "feat-a", "m1", 100, 50, 0.001)
    ledger_write(tmp_path, "feat-b", "m2", 200, 100, 0.002)
    lines = (tmp_path / ".cortex" / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_generate_brief_contains_sections(mgr, tmp_path):
    from core.analysis import generate_brief
    mgr.conn.execute(
        "CREATE (n:SystemDesign {id: 'sd1', name: 'OAuthFlow', description: 'OAuth', "
        "code_block: '', design_type: 'task', status: 'proposed', section: 'Auth', "
        "rationale: '', source_file: '', source_line: 0})"
    )
    brief = generate_brief(mgr.conn, tmp_path)
    assert "Auth" in brief
    assert "OAuthFlow" in brief
    assert "Node Counts" in brief
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_analysis.py -k "latent or ledger or brief" -v
```
Expected: FAIL — `ImportError`s for the missing functions.

- [ ] **Step 3: Add get_latent_bridges, ledger_write, generate_brief to core/analysis.py**

```python
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
        rows = []
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
```

- [ ] **Step 4: Run all analysis tests**

```bash
pytest tests/test_analysis.py -v
```
Expected: All PASSED

- [ ] **Step 5: Commit**

```bash
git add core/analysis.py tests/test_analysis.py
git commit -m "feat(analysis): Latent Bridges, Ledger, Cortex Brief"
```

---

## Task 5: REST Endpoints

**Files:**
- Modify: `cortex/web_server.py` — add 7 new GET endpoints + POST /api/export stub

- [ ] **Step 1: Verify endpoints don't exist yet**

```bash
python -c "
import inspect
from cortex.web_server import _build_app
from pathlib import Path
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    app = _build_app(Path(d))
    routes = [r.path for r in app.routes]
    for ep in ['/api/search', '/api/clusters', '/api/keystones', '/api/latent-bridges', '/api/ledger', '/api/brief']:
        assert ep not in routes, f'{ep} already exists'
print('All new endpoints are missing — good')
"
```
Expected: prints "All new endpoints are missing — good"

- [ ] **Step 2: Add the 7 new endpoints to web_server.py inside _build_app**

After the `/api/trail` endpoint, add:

```python
    @app.get("/api/search")
    async def api_search(q: str = "", top_n: int = 20):
        if not q:
            return JSONResponse([])
        from core.analysis import pulse_search
        return JSONResponse(pulse_search(mgr.conn, q, top_n=top_n))

    @app.get("/api/clusters")
    async def api_clusters():
        from core.analysis import detect_signal_clusters
        clusters = detect_signal_clusters(mgr.conn, project_root)
        return JSONResponse(clusters)

    @app.get("/api/keystones")
    async def api_keystones(top_n: int = 10):
        from core.analysis import get_keystones
        return JSONResponse(get_keystones(mgr.conn, top_n=top_n))

    @app.get("/api/latent-bridges")
    async def api_latent_bridges(top_n: int = 20):
        from core.analysis import get_latent_bridges
        return JSONResponse(get_latent_bridges(mgr.conn, project_root, top_n=top_n))

    @app.get("/api/ledger")
    async def api_ledger(limit: int = 200):
        ledger_path = project_root / ".cortex" / "ledger.jsonl"
        if not ledger_path.exists():
            return JSONResponse([])
        entries = []
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        return JSONResponse(entries[-limit:])

    @app.get("/api/brief")
    async def api_brief():
        from core.analysis import generate_brief
        return JSONResponse({"brief": generate_brief(mgr.conn, project_root)})

    @app.post("/api/export")
    async def api_export(body: dict[str, Any] = {}):
        fmt = body.get("format", "graphml")
        from core.analysis import generate_brief
        from core.graph_api import _get_all_nodes, _get_all_edges
        if fmt == "brief":
            return JSONResponse({"content": generate_brief(mgr.conn, project_root), "format": "md"})
        nodes = list(_get_all_nodes(mgr.conn).values())
        raw_edges = _get_all_edges(mgr.conn)
        edges = [{"src": k[0], "rel": k[1], "dst": k[2]} for k in raw_edges]
        return JSONResponse({"nodes": nodes, "edges": edges, "format": fmt})
```

- [ ] **Step 3: Smoke-test the endpoints by starting the server**

```bash
cortex init --root .
cortex run &
sleep 2
curl -s http://localhost:7842/api/search?q=auth | python -m json.tool
curl -s http://localhost:7842/api/keystones | python -m json.tool
curl -s http://localhost:7842/api/clusters | python -m json.tool
curl -s http://localhost:7842/api/brief | python -m json.tool
kill %1
```
Expected: each returns valid JSON (empty lists/objects is fine for empty graph).

- [ ] **Step 4: Commit**

```bash
git add cortex/web_server.py
git commit -m "feat(api): REST endpoints for search, clusters, keystones, latent-bridges, ledger, brief"
```

---

## Task 6: MCP Tools for Analysis

**Files:**
- Modify: `cortex/mcp_server.py` — add 4 new MCP tools

- [ ] **Step 1: Add detect_signal_clusters, get_keystones, get_latent_bridges, get_cortex_brief tools**

Add after `get_session_trail` tool in `cortex/mcp_server.py`:

```python
@mcp.tool()
def detect_signal_clusters_tool(
    resolution: Annotated[float, "Leiden resolution parameter (default 1.0 — higher = more clusters)"] = 1.0,
) -> str:
    """
    Run community detection on the graph to find Signal Clusters.

    Uses the Leiden algorithm when leidenalg + python-igraph are installed
    (pip install cortex[analysis]). Falls back to BFS connected components otherwise.

    Results are cached in .cortex/clusters.json and reused until the next snapshot.
    """
    _trail_append("detect_signal_clusters")
    from core.analysis import detect_signal_clusters
    clusters = detect_signal_clusters(_get_mgr().conn, PROJECT_ROOT, resolution=resolution)
    if not clusters:
        return "No nodes in graph — nothing to cluster."
    lines = [f"# Signal Clusters ({len(clusters)} found)\n"]
    for c in clusters:
        lines.append(f"## {c['label']} (color={c['color']})")
        lines.append(f"Members ({len(c['members'])}): {', '.join(c['members'][:10])}" +
                     (" …" if len(c['members']) > 10 else ""))
    return "\n".join(lines)


@mcp.tool()
def get_keystones_tool(
    top_n: Annotated[int, "Number of top nodes to return (default 10)"] = 10,
) -> str:
    """
    Return the top-N highest-degree nodes — the architectural 'god nodes'.

    Keystones are nodes with the most connections. They are often central
    services, shared utilities, or load-bearing design decisions.
    """
    _trail_append("get_keystones")
    from core.analysis import get_keystones
    keystones = get_keystones(_get_mgr().conn, top_n=top_n)
    if not keystones:
        return "No nodes found."
    lines = [f"# Keystones (top {top_n} by degree)\n"]
    for i, n in enumerate(keystones, 1):
        lines.append(f"{i}. [{n['label']}] {n['id']}  degree={n['degree']}  name={n['name']!r}")
    return "\n".join(lines)


@mcp.tool()
def get_latent_bridges_tool(
    top_n: Annotated[int, "Max bridges to return (default 20)"] = 20,
) -> str:
    """
    Return edges that cross cluster boundaries — surprising architectural connections.

    Latent Bridges highlight non-obvious dependencies between subsystems.
    Run detect_signal_clusters first to generate .cortex/clusters.json.
    """
    _trail_append("get_latent_bridges")
    from core.analysis import get_latent_bridges
    bridges = get_latent_bridges(_get_mgr().conn, PROJECT_ROOT, top_n=top_n)
    if not bridges:
        return "No cross-cluster edges found. Run detect_signal_clusters first."
    lines = [f"# Latent Bridges ({len(bridges)})\n"]
    for b in bridges:
        lines.append(
            f"({b['src']})-[{b['rel']}]->({b['dst']})  "
            f"cluster {b['src_cluster']} → {b['dst_cluster']}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_cortex_brief() -> str:
    """
    Generate a markdown summary of the project knowledge graph.

    Returns node counts by type, architecture sections with design nodes,
    and the three most recent graph snapshots. No LLM required.
    """
    _trail_append("get_cortex_brief")
    from core.analysis import generate_brief
    return generate_brief(_get_mgr().conn, PROJECT_ROOT)
```

- [ ] **Step 2: Smoke-test MCP tools**

```bash
python -c "
import cortex.mcp_server as srv
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory() as d:
    srv.PROJECT_ROOT = Path(d)
    srv._mgr = None
    print(srv.get_cortex_brief())
    print(srv.get_keystones_tool())
    print(srv.detect_signal_clusters_tool())
    print(srv.get_latent_bridges_tool())
"
```
Expected: each prints a valid text block with "# ..." headers and no exceptions.

- [ ] **Step 3: Run all analysis tests**

```bash
pytest tests/test_analysis.py -v
```
Expected: All PASSED

- [ ] **Step 4: Commit**

```bash
git add cortex/mcp_server.py
git commit -m "feat(mcp): analysis MCP tools — signal clusters, keystones, latent bridges, cortex brief"
```

---

Phase 2 complete. Delivers: `core/analysis.py` with 6 functions, 7 REST endpoints, 4 MCP tools, full test suite.
