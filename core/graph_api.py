"""
Core graph query helpers for Cortex.

All functions accept a kuzu.Connection and return plain Python dicts/lists
so they can be consumed by both the MCP tools and the FastAPI endpoints.

Semantic Triple format: "(Subject)-[REL]->(Object)"
"""

from __future__ import annotations

from typing import Any

import kuzu

from core.db import DatabaseManager

# All node table names defined in the schema
NODE_TABLES = ["File", "SystemDesign", "Service", "Database", "Infrastructure", "NodeGroup"]

# All rel table names defined in the schema
REL_TABLES = [
    "CONTAINS", "MODIFIES", "DEPENDS_ON", "QUERIES", "TALKS_TO", "HOSTED_ON",
    "IMPLEMENTS", "PART_OF", "USES", "STORES_IN", "RUNS_ON", "MEMBER_OF",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rows(result: Any) -> list[dict]:
    """Drain a Kùzu QueryResult into a list of dicts."""
    rows = []
    cols = result.get_column_names()
    while result.has_next():
        rows.append(dict(zip(cols, result.get_next())))
    return rows


def _node_label(conn: kuzu.Connection, node_id: str) -> str | None:
    """Return the table name (label) for a node with the given id."""
    for table in NODE_TABLES:
        r = conn.execute(
            f"MATCH (n:{table} {{id: $id}}) RETURN n.id LIMIT 1",
            {"id": node_id},
        )
        if r.has_next():
            return table
    return None


def _fetch_node(conn: kuzu.Connection, node_id: str, hint_label: str = "") -> dict:
    """
    Return full properties for a node by id.
    Tries hint_label first, then falls back to scanning all tables.
    """
    candidates = (
        [hint_label] + [t for t in NODE_TABLES if t != hint_label]
        if hint_label and hint_label in NODE_TABLES
        else NODE_TABLES
    )
    for table in candidates:
        try:
            r = conn.execute(
                f"MATCH (n:{table} {{id: $id}}) RETURN n.*",
                {"id": node_id},
            )
            rows = _rows(r)
            if rows:
                # Normalise column names: strip the "n." prefix added by Kùzu
                flat = {k[2:] if k.startswith("n.") else k: v for k, v in rows[0].items()}
                return {"label": table, **flat}
        except Exception:
            pass
    return {"label": hint_label or "Unknown", "id": node_id}


def _format_triple(src_id: str, rel: str, dst_id: str) -> str:
    return f"({src_id})-[{rel}]->({dst_id})"


# ---------------------------------------------------------------------------
# Neighborhood exploration
# ---------------------------------------------------------------------------

def get_neighborhood(
    conn: kuzu.Connection,
    node_id: str,
    depth: int = 1,
) -> dict:
    """
    Return the ego-graph around `node_id` up to `depth` hops.

    Returns:
        {
            "center": node_id,
            "nodes": [ {id, label, name, ...}, ... ],
            "edges": [ {src, rel, dst}, ... ],
            "triples": [ "(src)-[REL]->(dst)", ... ],
        }
    """
    depth = max(1, min(depth, 3))  # cap at 3 to avoid runaway queries

    found_nodes: dict[str, dict] = {}
    found_edges: list[dict] = []

    for table in NODE_TABLES:
        # Check if the center node lives in this table
        r = conn.execute(
            f"MATCH (n:{table} {{id: $id}}) RETURN n.*",
            {"id": node_id},
        )
        rows = _rows(r)
        if rows:
            flat = {k[2:] if k.startswith("n.") else k: v for k, v in rows[0].items()}
            found_nodes[node_id] = {"label": table, **flat}
            break

    if not found_nodes:
        return {"center": node_id, "nodes": [], "edges": [], "triples": []}

    # BFS up to `depth` hops across all rel types
    frontier = {node_id}
    visited_edges: set[tuple] = set()

    for _ in range(depth):
        next_frontier: set[str] = set()
        for src_id in frontier:
            src_label = _node_label(conn, src_id)
            if not src_label:
                continue
            for rel in REL_TABLES:
                # Outgoing
                try:
                    r = conn.execute(
                        f"MATCH (a:{src_label} {{id: $id}})-[r:{rel}]->(b) "
                        "RETURN b.id AS dst_id, labels(b)[0] AS dst_label, b.*",
                        {"id": src_id},
                    )
                    for row in _rows(r):
                        dst_id = row.get("dst_id") or row.get("b.id")
                        if not dst_id:
                            continue
                        key = (src_id, rel, dst_id)
                        if key not in visited_edges:
                            visited_edges.add(key)
                            found_edges.append({"src": src_id, "rel": rel, "dst": dst_id})
                        if dst_id not in found_nodes:
                            dst_label = row.get("dst_label", "Unknown")
                            # Pull full properties for the neighbour node
                            node_detail = _fetch_node(conn, dst_id, dst_label)
                            found_nodes[dst_id] = node_detail
                            next_frontier.add(dst_id)
                except Exception:
                    pass  # rel not defined for this src label — skip

                # Incoming
                try:
                    r = conn.execute(
                        f"MATCH (b)-[r:{rel}]->(a:{src_label} {{id: $id}}) "
                        "RETURN b.id AS src2_id, labels(b)[0] AS src2_label",
                        {"id": src_id},
                    )
                    for row in _rows(r):
                        src2_id = row.get("src2_id") or row.get("b.id")
                        if not src2_id:
                            continue
                        key = (src2_id, rel, src_id)
                        if key not in visited_edges:
                            visited_edges.add(key)
                            found_edges.append({"src": src2_id, "rel": rel, "dst": src_id})
                        if src2_id not in found_nodes:
                            src2_label = row.get("src2_label", "Unknown")
                            node_detail = _fetch_node(conn, src2_id, src2_label)
                            found_nodes[src2_id] = node_detail
                            next_frontier.add(src2_id)
                except Exception:
                    pass

        frontier = next_frontier
        if not frontier:
            break

    triples = [_format_triple(e["src"], e["rel"], e["dst"]) for e in found_edges]

    return {
        "center": node_id,
        "nodes": list(found_nodes.values()),
        "edges": found_edges,
        "triples": triples,
    }


# ---------------------------------------------------------------------------
# Shortest structural path
# ---------------------------------------------------------------------------

def find_path(
    conn: kuzu.Connection,
    start_node_id: str,
    end_node_id: str,
    max_depth: int = 6,
) -> dict:
    """
    Find the shortest directed path between two nodes using BFS over all
    relationship types.  Kùzu's variable-length path syntax varies across
    releases, so we implement BFS ourselves for portability.

    Returns:
        {
            "start": start_node_id,
            "end": end_node_id,
            "path_length": int | None,
            "triples": [ "(src)-[REL]->(dst)", ... ],
            "node_ids": [ str, ... ],
        }
    """
    if not _node_label(conn, start_node_id):
        return _path_not_found(start_node_id, end_node_id, "Start node not found.")
    if not _node_label(conn, end_node_id):
        return _path_not_found(start_node_id, end_node_id, "End node not found.")

    # BFS: each entry is (current_node_id, path_so_far_as_edge_list)
    queue: list[tuple[str, list[dict]]] = [(start_node_id, [])]
    visited: set[str] = {start_node_id}

    while queue:
        current, path = queue.pop(0)
        if current == end_node_id and path:
            node_ids = [path[0]["src"]] + [e["dst"] for e in path]
            triples = [_format_triple(e["src"], e["rel"], e["dst"]) for e in path]
            return {
                "start": start_node_id,
                "end": end_node_id,
                "path_length": len(triples),
                "triples": triples,
                "node_ids": node_ids,
            }

        if len(path) >= max_depth:
            continue

        current_label = _node_label(conn, current)
        if not current_label:
            continue

        for rel in REL_TABLES:
            try:
                r = conn.execute(
                    f"MATCH (a:{current_label} {{id: $id}})-[:{rel}]->(b) RETURN b.id AS nid",
                    {"id": current},
                )
                for row in _rows(r):
                    nid = row.get("nid")
                    if nid and nid not in visited:
                        visited.add(nid)
                        queue.append((nid, path + [{"src": current, "rel": rel, "dst": nid}]))
            except Exception:
                pass

    return _path_not_found(start_node_id, end_node_id, "No path found between the two nodes.")


def _path_not_found(start: str, end: str, reason: str) -> dict:
    return {
        "start": start,
        "end": end,
        "path_length": None,
        "triples": [],
        "node_ids": [],
        "error": reason,
    }


# ---------------------------------------------------------------------------
# Graph diff
# ---------------------------------------------------------------------------

def _get_all_nodes(conn: kuzu.Connection) -> dict[str, dict]:
    """Return every node in the DB keyed by its id string."""
    nodes: dict[str, dict] = {}
    for table in NODE_TABLES:
        try:
            r = conn.execute(f"MATCH (n:{table}) RETURN n.*")
            for row in _rows(r):
                flat = {k[2:] if k.startswith("n.") else k: v for k, v in row.items()}
                node_id = flat.get("id")
                if node_id:
                    nodes[node_id] = {"label": table, **flat}
        except Exception:
            pass
    return nodes


def _get_all_edges(conn: kuzu.Connection) -> dict[tuple, dict]:
    """Return every edge in the DB keyed by (src_id, rel_type, dst_id)."""
    edges: dict[tuple, dict] = {}
    for rel in REL_TABLES:
        try:
            r = conn.execute(
                f"MATCH (a)-[r:{rel}]->(b) RETURN a.id AS src, b.id AS dst, r.*"
            )
            for row in _rows(r):
                src = row.get("src")
                dst = row.get("dst")
                if src and dst:
                    edges[(src, rel, dst)] = row
        except Exception:
            pass
    return edges


def _node_fingerprint(node: dict) -> str:
    """Stable hash of node properties for change detection."""
    import json as _json
    clean = {k: v for k, v in node.items() if k not in ("label",)}
    return _json.dumps(clean, sort_keys=True)


def compute_diff(mgr: DatabaseManager, from_slot: int, to_slot: int) -> dict:
    """
    Compare two snapshot slots and return structured diff metadata.

    Returns:
        {
            "from_slot": int,
            "to_slot": int,
            "added_nodes":    [ node_id, ... ],
            "deleted_nodes":  [ node_id, ... ],
            "modified_nodes": [ node_id, ... ],
            "added_edges":    [ {src, rel, dst}, ... ],
            "deleted_edges":  [ {src, rel, dst}, ... ],
            "summary_triples": [ str, ... ],   # human-readable change log
        }
    """
    from_conn = mgr.open_version_conn(from_slot)
    to_conn = mgr.open_version_conn(to_slot)

    from_nodes = _get_all_nodes(from_conn)
    to_nodes = _get_all_nodes(to_conn)
    from_edges = _get_all_edges(from_conn)
    to_edges = _get_all_edges(to_conn)

    from_ids = set(from_nodes)
    to_ids = set(to_nodes)

    added_nodes = sorted(to_ids - from_ids)
    deleted_nodes = sorted(from_ids - to_ids)
    modified_nodes = [
        nid for nid in (from_ids & to_ids)
        if _node_fingerprint(from_nodes[nid]) != _node_fingerprint(to_nodes[nid])
    ]

    from_edge_keys = set(from_edges)
    to_edge_keys = set(to_edges)
    added_edge_keys = to_edge_keys - from_edge_keys
    deleted_edge_keys = from_edge_keys - to_edge_keys

    added_edges = [{"src": k[0], "rel": k[1], "dst": k[2]} for k in added_edge_keys]
    deleted_edges = [{"src": k[0], "rel": k[1], "dst": k[2]} for k in deleted_edge_keys]

    summary_triples: list[str] = []
    for nid in added_nodes:
        summary_triples.append(f"[ADDED]    ({nid})")
    for nid in deleted_nodes:
        summary_triples.append(f"[DELETED]  ({nid})")
    for nid in modified_nodes:
        summary_triples.append(f"[MODIFIED] ({nid})")
    for e in added_edges:
        summary_triples.append(f"[ADDED]    {_format_triple(e['src'], e['rel'], e['dst'])}")
    for e in deleted_edges:
        summary_triples.append(f"[DELETED]  {_format_triple(e['src'], e['rel'], e['dst'])}")

    return {
        "from_slot": from_slot,
        "to_slot": to_slot,
        "added_nodes": added_nodes,
        "deleted_nodes": deleted_nodes,
        "modified_nodes": modified_nodes,
        "added_edges": added_edges,
        "deleted_edges": deleted_edges,
        "summary_triples": summary_triples,
    }
