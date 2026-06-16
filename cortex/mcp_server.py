"""
Cortex MCP Server — exposes the knowledge graph to AI agents via the
Model Context Protocol.

Tools
-----
  get_graph_timeline()
  query_graph_diff(from_version, to_version)
  explore_neighborhood(node_id, depth)
  find_structural_path(start_node_id, end_node_id)
  write_system_design_node(id, title, type, description, connections)

Run (stdio transport, for Cursor / Claude Desktop / Windsurf):
    python -m cortex.mcp_server

Run (SSE transport, for web debugging):
    python -m cortex.mcp_server --sse
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP

# Resolve the project root (directory that contains .cortex/)
# When run as `python -m cortex.mcp_server`, cwd is the project root.
PROJECT_ROOT = Path.cwd()

# Lazy-initialised singletons — created on first tool call
_mgr = None
_ws_broadcast: Any = None   # injected by the web server when running combined


def _get_mgr():
    global _mgr
    if _mgr is None:
        from core.db import DatabaseManager
        _mgr = DatabaseManager(PROJECT_ROOT)
        _mgr.init()
    return _mgr


def set_ws_broadcast(fn):
    """Called by the FastAPI web server to inject a WebSocket broadcast hook."""
    global _ws_broadcast
    _ws_broadcast = fn


# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="cortex",
    instructions=(
        "Cortex is a knowledge graph MCP server for software projects. "
        "SystemDesign node IDs follow the format SystemDesign:Section:Name "
        "(e.g. SystemDesign:Auth:GoogleOAuth). "
        "ALWAYS call list_design_sections first to understand the project architecture. "
        "Use explore_neighborhood to drill into specific nodes. "
        "Use write_system_design_node to document new design decisions with connects_to edges. "
        "Call commit_snapshot (via /api/commit POST) before any git commit."
    ),
)


# ---------------------------------------------------------------------------
# Tool: get_graph_timeline
# ---------------------------------------------------------------------------

@mcp.tool()
def get_graph_timeline() -> str:
    """
    Returns the list of up to 5 historical graph snapshots with their
    slot numbers, timestamps, and commit messages — newest first.

    Use this to understand what changed over time before calling
    query_graph_diff.
    """
    mgr = _get_mgr()
    timeline = mgr.get_timeline()
    if not timeline:
        return "No snapshots found. The graph has not been committed yet."

    lines = ["# Graph Timeline\n"]
    for v in timeline:
        lines.append(
            f"[{v['label']}]  slot={v['slot']}  "
            f"ts={v['timestamp']}  \"{v['message']}\""
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: query_graph_diff
# ---------------------------------------------------------------------------

@mcp.tool()
def query_graph_diff(
    from_version: Annotated[int, "Slot number of the older snapshot (1-5)"],
    to_version: Annotated[int, "Slot number of the newer snapshot (1-5)"],
) -> str:
    """
    Returns a dense text summary of exactly what changed between two
    committed graph snapshots: added/deleted/modified nodes and edges.

    Call get_graph_timeline first to discover valid slot numbers.
    """
    mgr = _get_mgr()
    from core.graph_api import compute_diff

    try:
        diff = compute_diff(mgr, from_version, to_version)
    except FileNotFoundError as exc:
        return f"Error: {exc}"

    lines = [
        f"# Graph Diff: slot {from_version} → slot {to_version}\n",
        f"Added nodes    ({len(diff['added_nodes'])}): {', '.join(diff['added_nodes']) or 'none'}",
        f"Deleted nodes  ({len(diff['deleted_nodes'])}): {', '.join(diff['deleted_nodes']) or 'none'}",
        f"Modified nodes ({len(diff['modified_nodes'])}): {', '.join(diff['modified_nodes']) or 'none'}",
        f"Added edges    ({len(diff['added_edges'])})",
        f"Deleted edges  ({len(diff['deleted_edges'])})\n",
        "## Change Log (Semantic Triples)",
    ]
    if diff["summary_triples"]:
        lines += [f"  {t}" for t in diff["summary_triples"]]
    else:
        lines.append("  (no structural changes detected)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: explore_neighborhood
# ---------------------------------------------------------------------------

@mcp.tool()
def explore_neighborhood(
    node_id: Annotated[str, "Target node ID, e.g. @File:auth.py:f89a2"],
    depth: Annotated[int, "Hop radius (1 or 2, default 1)"] = 1,
) -> str:
    """
    Returns all nodes and relationships within `depth` hops of `node_id`,
    expressed as compact Semantic Triples: (Subject)-[REL]->(Object).

    Use depth=1 for a quick scan of direct neighbours and depth=2 to
    discover indirect dependencies one hop further out.
    """
    from core.graph_api import get_neighborhood

    mgr = _get_mgr()
    result = get_neighborhood(mgr.conn, node_id, depth=depth)

    if not result["nodes"]:
        return f"Node `{node_id}` not found in the graph."

    lines = [
        f"# Neighborhood of {node_id}  (depth={depth})\n",
        f"Nodes found: {len(result['nodes'])}",
        f"Edges found: {len(result['edges'])}\n",
        "## Semantic Triples",
    ]
    if result["triples"]:
        lines += [f"  {t}" for t in result["triples"]]
    else:
        lines.append("  (isolated node — no relationships found)")

    lines.append("\n## Node Details")
    for node in result["nodes"]:
        nid = node.get("id", "?")
        label = node.get("label", "?")
        name = node.get("name", "")
        desc = node.get("description", "")
        lines.append(f"  [{label}] {nid}  name={name!r}  desc={desc!r}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: find_structural_path
# ---------------------------------------------------------------------------

@mcp.tool()
def find_structural_path(
    start_node_id: Annotated[str, "Source node ID, e.g. @SystemDesign:AuthFlow:sd001"],
    end_node_id: Annotated[str, "Target node ID, e.g. @Infrastructure:AWS_EC2:inf001"],
) -> str:
    """
    Finds the shortest transactional path between two nodes across any
    relationship type in the graph.

    Useful for questions like: "How does the OAuth task reach our AWS
    infrastructure?" or "Which services are in the chain between this
    file and the database?"
    """
    from core.graph_api import find_path

    mgr = _get_mgr()
    result = find_path(mgr.conn, start_node_id, end_node_id)

    if result.get("error"):
        return f"Path not found: {result['error']}"

    lines = [
        f"# Structural Path\n",
        f"From: {start_node_id}",
        f"To:   {end_node_id}",
        f"Hops: {result['path_length']}\n",
        "## Path (Semantic Triples)",
    ]
    lines += [f"  {t}" for t in result["triples"]]
    lines.append(f"\n## Node Sequence")
    lines.append("  " + " -> ".join(result["node_ids"]))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: write_system_design_node
# ---------------------------------------------------------------------------

@mcp.tool()
def write_system_design_node(
    id: Annotated[str, "Node ID: SystemDesign:Section:Name e.g. SystemDesign:Auth:GoogleOAuth"],
    name: Annotated[str, "Human-readable name for this design node"],
    section: Annotated[str, "Design section this belongs to, e.g. Auth, Payments, Storage"],
    description: Annotated[str, "Full description of the design intent"],
    status: Annotated[str, "planned | in-progress | done"] = "planned",
    rationale: Annotated[str, "Why this approach was chosen"] = "",
    connects_to: Annotated[
        str,
        "JSON array of {rel, target_id} e.g. "
        '[{"rel":"IMPLEMENTS","target_id":"File:auth.py"}]. Pass \'[]\' for none.',
    ] = "[]",
) -> str:
    """
    Writes a SystemDesign node into the live graph and wires it to existing nodes.

    ID format: SystemDesign:<Section>:<Name>
      - Section groups related design decisions (e.g. Auth, Payments, Storage)
      - Name identifies this specific decision (e.g. GoogleOAuth, StripeWebhook)

    Valid relationship types for connects_to:
      IMPLEMENTS  -> File           (this design is implemented in that file)
      PART_OF     -> SystemDesign   (this design is part of a broader design)
      USES        -> Service        (this design depends on that external service)
      STORES_IN   -> Database       (this design stores data in that database)
      RUNS_ON     -> Infrastructure (this design runs on that infra node)
      MODIFIES    -> File           (this design modifies that file)
      TALKS_TO    -> Service        (this design communicates with that service)

    Automatically snapshots the graph after writing.
    """
    mgr = _get_mgr()
    conn = mgr.conn

    try:
        conn_list: list[dict] = json.loads(connects_to)
    except json.JSONDecodeError as exc:
        return f"Error: `connects_to` is not valid JSON — {exc}"

    valid_rels = {
        "CONTAINS", "MODIFIES", "DEPENDS_ON", "QUERIES", "TALKS_TO", "HOSTED_ON",
        "IMPLEMENTS", "PART_OF", "USES", "STORES_IN", "RUNS_ON",
    }
    for c in conn_list:
        if c.get("rel") not in valid_rels:
            return (
                f"Error: unknown relationship '{c.get('rel')}'. "
                f"Valid: {', '.join(sorted(valid_rels))}"
            )

    # Check existence (Kùzu has no MERGE)
    exists_r = conn.execute(
        "MATCH (n:SystemDesign {id: $id}) RETURN count(*) AS c", {"id": id}
    )
    rows = []
    while exists_r.has_next():
        rows.append(exists_r.get_next())
    node_exists = rows and rows[0][0] > 0

    def _set(prop: str, value: str) -> None:
        conn.execute(
            f"MATCH (n:SystemDesign {{id: $id}}) SET n.{prop} = $val",
            {"id": id, "val": value},
        )

    if not node_exists:
        conn.execute(
            "CREATE (n:SystemDesign {id: $id, name: '', description: '', "
            "design_type: '', status: '', code_block: '', section: '', rationale: ''})",
            {"id": id},
        )

    _set("name", name)
    _set("description", description)
    _set("section", section)
    _set("status", status)
    _set("rationale", rationale)

    from core.graph_api import _node_label, _format_triple
    created_edges: list[str] = []
    errors: list[str] = []

    for c in conn_list:
        rel = c["rel"]
        target_id = c["target_id"]
        target_label = _node_label(conn, target_id)
        if not target_label:
            errors.append(f"Target not found: {target_id}")
            continue
        try:
            conn.execute(
                f"MATCH (a:SystemDesign {{id: $src}}), (b:{target_label} {{id: $dst}}) "
                f"CREATE (a)-[:{rel}]->(b)",
                {"src": id, "dst": target_id},
            )
            created_edges.append(_format_triple(id, rel, target_id))
        except Exception as exc:
            errors.append(f"Edge ({id})-[{rel}]->({target_id}) failed: {exc}")

    snapshot = mgr.commit_snapshot(f"write_system_design_node: {name}")

    if _ws_broadcast:
        payload = {
            "event": "node_added",
            "node": {
                "id": id, "label": "SystemDesign", "name": name,
                "description": description, "section": section,
                "status": status, "rationale": rationale,
            },
            "edges": created_edges,
        }
        try:
            asyncio.get_event_loop().run_until_complete(_ws_broadcast(json.dumps(payload)))
        except Exception:
            pass

    lines = [
        f"# SystemDesign Node Written\n",
        f"ID:          {id}",
        f"Section:     {section}",
        f"Name:        {name}",
        f"Status:      {status}",
        f"Description: {description}",
        f"Rationale:   {rationale}",
        f"\nEdges created ({len(created_edges)}):",
    ]
    lines += [f"  {e}" for e in created_edges] or ["  (none)"]
    if errors:
        lines.append(f"\nWarnings ({len(errors)}):")
        lines += [f"  {e}" for e in errors]
    lines.append(f"\nSnapshot: slot={snapshot['slot']} ts={snapshot['timestamp']}")
    return "\n".join(lines)


@mcp.tool()
def write_agent_instructions() -> str:
    """
    Writes (or appends) a Cortex usage section to CLAUDE.md and AGENTS.md
    in the current project root.

    Call this once after bootstrapping the graph for a new project. It ensures
    every future AI session on this project knows to use Cortex for architecture
    queries instead of grep/glob/file search.

    - If CLAUDE.md / AGENTS.md already exist, the section is appended at the
      bottom (only if no Cortex section is present yet).
    - If neither file exists, both are created.
    - Returns a summary of what was written.
    """
    section = """
## Cortex Knowledge Graph

This project uses **Cortex**, a local knowledge graph MCP server (server name: `cortex`).

**Whenever you need to find something about this project — structure, dependencies, architecture, design decisions — look in Cortex first. Do not use grep, glob, ls, or file search to understand the codebase.**

At the start of every session:
1. Call `list_design_sections` to get a structural map of the project
2. Use `explore_neighborhood(node_id)` to drill into any component
3. Use `find_structural_path(src_id, dst_id)` to trace dependency chains
4. Call `commit_snapshot` (or POST to `http://localhost:7842/api/commit`) before every `git commit`
5. Document new architectural decisions with `write_system_design_node` before writing code
"""

    marker = "## Cortex Knowledge Graph"
    written: list[str] = []
    skipped: list[str] = []

    for filename in ("CLAUDE.md", "AGENTS.md"):
        target = PROJECT_ROOT / filename
        if target.exists():
            content = target.read_text(encoding="utf-8")
            if marker in content:
                skipped.append(filename)
                continue
            target.write_text(content.rstrip("\n") + "\n" + section, encoding="utf-8")
        else:
            target.write_text(section.lstrip("\n"), encoding="utf-8")
        written.append(filename)

    lines = ["# write_agent_instructions\n"]
    if written:
        lines.append(f"Written to: {', '.join(written)}")
    if skipped:
        lines.append(f"Already had Cortex section (skipped): {', '.join(skipped)}")
    if not written and not skipped:
        lines.append("No files written (unexpected state).")
    lines.append(f"\nProject root: {PROJECT_ROOT}")
    return "\n".join(lines)


@mcp.tool()
def list_design_sections() -> str:
    """
    Returns a structured overview of all SystemDesign nodes grouped by section.

    Call this first when exploring an unfamiliar project to understand its
    architecture before drilling into specific nodes with explore_neighborhood.
    """
    mgr = _get_mgr()
    rows = mgr.query_to_dicts(
        "MATCH (n:SystemDesign) RETURN n.id AS id, n.name AS name, "
        "n.section AS section, n.status AS status, n.description AS description"
    )
    if not rows:
        return "No SystemDesign nodes found. Use write_system_design_node to document architecture."

    sections: dict[str, list] = {}
    for row in rows:
        sec = row.get("section") or "Unsectioned"
        sections.setdefault(sec, []).append(row)

    lines = ["# Project Architecture — SystemDesign Sections\n"]
    for sec, nodes in sorted(sections.items()):
        lines.append(f"## {sec} ({len(nodes)} nodes)")
        for n in nodes:
            status = n.get("status") or "unknown"
            desc = (n.get("description") or "")[:80]
            lines.append(f"  [{status:12s}] {n['id']}")
            lines.append(f"               {n['name']}: {desc}")
        lines.append("")

    lines.append(f"Total: {len(rows)} design nodes across {len(sections)} sections.")
    lines.append("Use explore_neighborhood(node_id) to drill into any node.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = "sse" if "--sse" in sys.argv else "stdio"
    if transport == "sse":
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
