# Cortex v2 — Phase 4: Export & Integrations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Graph Export (GraphML, Obsidian, wiki, SVG), Graph Relay (Neo4j, FalkorDB push), Graph Reconciler (git merge driver for versions.json), and Cortex Connect (interactive checkbox installer for AI tool MCP configs).

**Architecture:** Each integration is a standalone module. `core/export.py` has four export functions. `core/relay.py` has two relay functions. `core/reconciler.py` has one merge function. Cortex Connect lives in `cortex/connect.py` and is invoked by `cortex connect`. New CLI subcommands (`relay`, `connect`) are wired in `cortex/main.py`.

**Tech Stack:** Python 3.11+ stdlib only for export/relay/connect. Optional: `neo4j` driver (`[neo4j]`), `falkordb` driver (`[falkordb]`). Cortex Connect uses `sys.stdin`/`sys.stdout` for interactive checkbox UI — no npm.

**Prerequisites:** Phase 1 complete (Group node table, trail.jsonl). Phase 2 complete (analysis endpoints exist for wiki fallback).

---

## Task 1: Graph Export — GraphML and Obsidian

**Files:**
- Create: `core/export.py`
- Create: `tests/test_export.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_export.py`:

```python
import pytest
from pathlib import Path
from core.db import DatabaseManager
from core.export import export_graphml, export_obsidian, export_wiki


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    m.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth.py', description: 'auth module', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    m.conn.execute(
        "CREATE (n:SystemDesign {id: 'sd1', name: 'OAuthFlow', description: 'OAuth impl', "
        "code_block: '', design_type: 'task', status: 'proposed', section: 'Auth', "
        "rationale: 'industry standard', source_file: '', source_line: 0})"
    )
    m.conn.execute(
        "MATCH (d:SystemDesign {id: 'sd1'}), (f:File {id: 'f1'}) CREATE (d)-[:IMPLEMENTS]->(f)"
    )
    yield m
    m.close()


def test_export_graphml_returns_xml(mgr):
    xml = export_graphml(mgr.conn)
    assert xml.startswith('<?xml')
    assert '<graphml' in xml
    assert 'auth.py' in xml or 'f1' in xml


def test_export_graphml_contains_edges(mgr):
    xml = export_graphml(mgr.conn)
    assert '<edge' in xml


def test_export_obsidian_creates_md_files(mgr, tmp_path):
    out_dir = tmp_path / "obsidian_vault"
    export_obsidian(mgr.conn, out_dir)
    md_files = list(out_dir.glob("*.md"))
    assert len(md_files) >= 2


def test_export_obsidian_file_contains_wikilinks(mgr, tmp_path):
    out_dir = tmp_path / "obsidian_vault"
    export_obsidian(mgr.conn, out_dir)
    # SystemDesign node should link to its connected File
    sd_file = out_dir / "OAuthFlow.md"
    assert sd_file.exists()
    content = sd_file.read_text()
    assert "[[auth.py]]" in content or "[[f1" in content or "IMPLEMENTS" in content


def test_export_wiki_returns_markdown(mgr, tmp_path):
    md = export_wiki(mgr.conn, tmp_path)
    assert "# " in md
    assert "Auth" in md
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_export.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'core.export'`

- [ ] **Step 3: Create core/export.py**

```python
"""
Graph Export — converts the Kùzu graph to external formats.

Functions:
  export_graphml(conn) -> str             — GraphML XML string
  export_obsidian(conn, output_dir)       — writes .md files to output_dir
  export_wiki(conn, project_root) -> str  — markdown wiki string
  export_svg(conn) -> str                 — simple SVG string (no layout engine)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import kuzu


def _rows(result: Any) -> list[dict]:
    rows = []
    cols = result.get_column_names()
    while result.has_next():
        rows.append(dict(zip(cols, result.get_next())))
    return rows


def _get_all_nodes(conn: kuzu.Connection) -> list[dict]:
    from core.graph_api import NODE_TABLES
    nodes = []
    for table in NODE_TABLES:
        try:
            r = conn.execute(f"MATCH (n:{table}) RETURN n.*")
            for row in _rows(r):
                flat = {k[2:] if k.startswith("n.") else k: v for k, v in row.items()}
                nodes.append({"label": table, **flat})
        except Exception:
            pass
    return nodes


def _get_all_edges(conn: kuzu.Connection) -> list[dict]:
    from core.graph_api import REL_TABLES
    edges = []
    for rel in REL_TABLES:
        try:
            r = conn.execute(f"MATCH (a)-[:{rel}]->(b) RETURN a.id AS src, b.id AS dst")
            for row in _rows(r):
                if row.get("src") and row.get("dst"):
                    edges.append({"src": row["src"], "rel": rel, "dst": row["dst"]})
        except Exception:
            pass
    return edges


# ---------------------------------------------------------------------------
# GraphML
# ---------------------------------------------------------------------------

def export_graphml(conn: kuzu.Connection) -> str:
    """Export the graph as a GraphML XML string."""
    nodes = _get_all_nodes(conn)
    edges = _get_all_edges(conn)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphstruct.org/graphml"',
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '         xsi:schemaLocation="http://graphml.graphstruct.org/graphml '
        'http://graphml.graphstruct.org/graphml/1.0.0/graphml.xsd">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="name"  for="node" attr.name="name"  attr.type="string"/>',
        '  <key id="desc"  for="node" attr.name="description" attr.type="string"/>',
        '  <key id="rel"   for="edge" attr.name="rel"   attr.type="string"/>',
        '  <graph id="G" edgedefault="directed">',
    ]

    def _esc(s: str) -> str:
        return (str(s or "")
                .replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    for n in nodes:
        nid = _esc(n.get("id", ""))
        lines.append(f'    <node id="{nid}">')
        lines.append(f'      <data key="label">{_esc(n.get("label",""))}</data>')
        lines.append(f'      <data key="name">{_esc(n.get("name",""))}</data>')
        lines.append(f'      <data key="desc">{_esc(n.get("description",""))}</data>')
        lines.append('    </node>')

    for i, e in enumerate(edges):
        src = _esc(e["src"])
        dst = _esc(e["dst"])
        rel = _esc(e["rel"])
        lines.append(f'    <edge id="e{i}" source="{src}" target="{dst}">')
        lines.append(f'      <data key="rel">{rel}</data>')
        lines.append('    </edge>')

    lines += ['  </graph>', '</graphml>']
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Obsidian vault
# ---------------------------------------------------------------------------

def export_obsidian(conn: kuzu.Connection, output_dir: Path) -> None:
    """
    Write one .md file per node into output_dir.

    Each file contains the node's properties and wiki-links ([[Name]]) to
    connected nodes. Group nodes get an index page listing all members.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    nodes = _get_all_nodes(conn)
    edges = _get_all_edges(conn)

    node_by_id = {n.get("id"): n for n in nodes}

    # Build adjacency: nodeId → [(rel, neighbour_node)]
    outgoing: dict[str, list[tuple[str, dict]]] = {}
    for n in nodes:
        outgoing[n.get("id", "")] = []

    for e in edges:
        src, dst, rel = e["src"], e["dst"], e["rel"]
        if src in outgoing and dst in node_by_id:
            outgoing[src].append((rel, node_by_id[dst]))

    def _safe_name(name: str) -> str:
        return "".join(c if c.isalnum() or c in ("-", "_", " ", ".") else "_" for c in name)

    for n in nodes:
        nid = n.get("id", "")
        name = n.get("name") or nid
        filename = _safe_name(name)[:60] + ".md"
        filepath = output_dir / filename

        lines = [f"# {name}", f"", f"**Type:** {n.get('label', '?')}"]
        if n.get("description"):
            lines += ["", f"**Description:** {n['description']}"]
        if n.get("status"):
            lines += [f"**Status:** {n['status']}"]
        if n.get("section"):
            lines += [f"**Section:** {n['section']}"]
        if n.get("rationale"):
            lines += ["", f"**Rationale:** {n['rationale']}"]
        if n.get("source_file"):
            sf = n["source_file"]
            sl = n.get("source_line") or 0
            lines += [f"**Source:** `{sf}:{sl}`" if sl else f"**Source:** `{sf}`"]
        lines += ["", "## Connections", ""]

        nbrs = outgoing.get(nid, [])
        if nbrs:
            for rel, nbr in nbrs:
                nbr_name = nbr.get("name") or nbr.get("id", "?")
                lines.append(f"- **{rel}** → [[{_safe_name(nbr_name)}]]")
        else:
            lines.append("*(no outgoing connections)*")

        lines += ["", f"---", f"*ID: `{nid}`*"]
        filepath.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Wiki (section-grouped markdown)
# ---------------------------------------------------------------------------

def export_wiki(conn: kuzu.Connection, project_root: Path) -> str:
    """
    Export the graph as a single markdown wiki document.

    Groups SystemDesign nodes by section. Falls back to section-based grouping
    when Signal Clusters haven't been computed.
    """
    nodes = _get_all_nodes(conn)
    edges = _get_all_edges(conn)

    # Try to load cluster data for section grouping enrichment
    clusters_path = project_root / ".cortex" / "clusters.json"
    cluster_labels: dict[str, str] = {}
    if clusters_path.exists():
        try:
            data = json.loads(clusters_path.read_text())
            for c in data.get("clusters", []):
                for m in c.get("members", []):
                    cluster_labels[m] = c["label"]
        except Exception:
            pass

    # Organise SystemDesign nodes by section
    sections: dict[str, list[dict]] = {}
    for n in nodes:
        if n.get("label") == "SystemDesign":
            sec = n.get("section") or "Unsectioned"
            sections.setdefault(sec, []).append(n)

    lines = ["# Project Architecture Wiki", ""]
    lines.append(f"*{len(nodes)} total nodes · {len(edges)} total edges*")
    lines.append("")

    for sec, sec_nodes in sorted(sections.items()):
        lines.append(f"## {sec}")
        for n in sec_nodes:
            status = n.get("status", "?")
            name = n.get("name", "?")
            desc = n.get("description", "")
            lines.append(f"### {name} `[{status}]`")
            if desc:
                lines.append(f"{desc}")
            if n.get("rationale"):
                lines.append(f"> **Why:** {n['rationale']}")
            cl = cluster_labels.get(n.get("id", ""))
            if cl:
                lines.append(f"> *Signal Cluster: {cl}*")
            lines.append("")

    # Non-design nodes summary
    other = [n for n in nodes if n.get("label") != "SystemDesign"]
    if other:
        lines.append("## Other Nodes")
        lines.append("")
        by_label: dict[str, list] = {}
        for n in other:
            by_label.setdefault(n.get("label", "Unknown"), []).append(n)
        for label, label_nodes in sorted(by_label.items()):
            lines.append(f"### {label} ({len(label_nodes)})")
            for n in label_nodes[:10]:
                lines.append(f"- **{n.get('name', n.get('id', '?'))}** — {n.get('description', '')[:80]}")
            if len(label_nodes) > 10:
                lines.append(f"  *(+{len(label_nodes)-10} more)*")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SVG (basic, no layout engine)
# ---------------------------------------------------------------------------

def export_svg(conn: kuzu.Connection) -> str:
    """
    Generate a simple SVG representation of the graph.

    Nodes are arranged in a grid. Edges are drawn as lines.
    No layout engine required — this is a structural overview, not a visual layout.
    """
    nodes = _get_all_nodes(conn)
    edges = _get_all_edges(conn)

    COLS = 5
    NODE_W, NODE_H = 140, 40
    GAP_X, GAP_Y = 30, 60
    PADDING = 40

    positions: dict[str, tuple[int, int]] = {}
    for i, n in enumerate(nodes):
        col = i % COLS
        row = i // COLS
        x = PADDING + col * (NODE_W + GAP_X)
        y = PADDING + row * (NODE_H + GAP_Y)
        positions[n.get("id", "")] = (x + NODE_W // 2, y + NODE_H // 2)

    total_cols = min(len(nodes), COLS)
    total_rows = (len(nodes) + COLS - 1) // COLS
    SVG_W = PADDING * 2 + total_cols * (NODE_W + GAP_X)
    SVG_H = PADDING * 2 + total_rows * (NODE_H + GAP_Y) + 20

    TYPE_COLORS = {
        "File": "#3b82f6",
        "SystemDesign": "#7c3aed",
        "Service": "#ea580c",
        "Database": "#059669",
        "Infrastructure": "#6b7280",
        "Group": "#7c3aed",
    }

    def _esc(s: str) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}">',
        f'  <rect width="{SVG_W}" height="{SVG_H}" fill="#1e1e1e"/>',
    ]

    # Draw edges first
    for e in edges:
        src_pos = positions.get(e["src"])
        dst_pos = positions.get(e["dst"])
        if src_pos and dst_pos:
            lines.append(
                f'  <line x1="{src_pos[0]}" y1="{src_pos[1]}" '
                f'x2="{dst_pos[0]}" y2="{dst_pos[1]}" '
                f'stroke="#555" stroke-width="1" opacity="0.6"/>'
            )

    # Draw nodes
    for i, n in enumerate(nodes):
        col = i % COLS
        row = i // COLS
        x = PADDING + col * (NODE_W + GAP_X)
        y = PADDING + row * (NODE_H + GAP_Y)
        color = TYPE_COLORS.get(n.get("label", ""), "#6b7280")
        name = (n.get("name") or n.get("id") or "")[:18]
        lines.append(
            f'  <rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" '
            f'rx="6" fill="#2d2d2d" stroke="{color}" stroke-width="2"/>'
        )
        lines.append(
            f'  <text x="{x + NODE_W//2}" y="{y + NODE_H//2 + 4}" '
            f'text-anchor="middle" fill="#ccc" font-size="11" '
            f'font-family="monospace">{_esc(name)}</text>'
        )

    lines.append('</svg>')
    return "\n".join(lines)
```

- [ ] **Step 4: Run export tests**

```bash
pytest tests/test_export.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Wire POST /api/export to use real export functions in web_server.py**

In `cortex/web_server.py`, replace the stub `api_export` route:

```python
    @app.post("/api/export")
    async def api_export(body: dict[str, Any] = {}):
        fmt = body.get("format", "graphml")
        from core.export import export_graphml, export_obsidian, export_wiki, export_svg
        if fmt == "graphml":
            return Response(content=export_graphml(mgr.conn), media_type="application/xml")
        elif fmt == "svg":
            return Response(content=export_svg(mgr.conn), media_type="image/svg+xml")
        elif fmt == "wiki":
            return Response(content=export_wiki(mgr.conn, project_root), media_type="text/markdown")
        elif fmt == "obsidian":
            import tempfile, zipfile, io
            with tempfile.TemporaryDirectory() as tmpdir:
                export_obsidian(mgr.conn, Path(tmpdir))
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    for f in Path(tmpdir).glob("*.md"):
                        zf.write(f, f.name)
                buf.seek(0)
                return Response(
                    content=buf.read(),
                    media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="cortex-obsidian.zip"'},
                )
        return JSONResponse({"error": f"Unknown format: {fmt}"}, status_code=400)
```

- [ ] **Step 6: Commit**

```bash
git add core/export.py tests/test_export.py cortex/web_server.py
git commit -m "feat(export): Graph Export — GraphML, Obsidian, wiki, SVG via POST /api/export"
```

---

## Task 2: Graph Relay (Neo4j + FalkorDB)

**Files:**
- Create: `core/relay.py`
- Modify: `cortex/main.py` — add `relay` subcommand

- [ ] **Step 1: Write the failing test**

Create `tests/test_relay.py`:

```python
import pytest
from pathlib import Path
from core.db import DatabaseManager


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    m.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth.py', description: 'auth', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    yield m
    m.close()


def test_relay_neo4j_returns_cypher_only(mgr):
    """--cypher-only mode should return Cypher strings without connecting."""
    from core.relay import relay_neo4j
    cypher_lines = relay_neo4j(mgr.conn, uri="bolt://localhost:7687", cypher_only=True)
    assert isinstance(cypher_lines, list)
    assert len(cypher_lines) >= 1
    assert any("MERGE" in line for line in cypher_lines)


def test_relay_falkordb_returns_cypher_only(mgr):
    from core.relay import relay_falkordb
    cypher_lines = relay_falkordb(mgr.conn, host="localhost", port=6379, cypher_only=True)
    assert isinstance(cypher_lines, list)
    assert any("MERGE" in line for line in cypher_lines)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_relay.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'core.relay'`

- [ ] **Step 3: Create core/relay.py**

```python
"""
Graph Relay — pushes the Kùzu graph to external graph databases.

Functions:
  relay_neo4j(conn, uri, user, password, database, cypher_only) -> list[str]
  relay_falkordb(conn, host, port, password, graph_name, cypher_only) -> list[str]

When cypher_only=True, both functions return the Cypher statements as a list
of strings without connecting to any database. Use this to preview the push
or pipe to a file.
"""
from __future__ import annotations

from typing import Any

import kuzu


def _rows(result: Any) -> list[dict]:
    rows = []
    cols = result.get_column_names()
    while result.has_next():
        rows.append(dict(zip(cols, result.get_next())))
    return rows


def _build_cypher_statements(conn: kuzu.Connection) -> list[str]:
    """Generate MERGE Cypher for all nodes and CREATE for all edges."""
    from core.graph_api import NODE_TABLES, REL_TABLES

    def _esc(v: Any) -> str:
        if isinstance(v, str):
            return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
        if v is None:
            return "null"
        return str(v)

    statements: list[str] = []

    for table in NODE_TABLES:
        try:
            r = conn.execute(f"MATCH (n:{table}) RETURN n.*")
            for row in _rows(r):
                flat = {k[2:] if k.startswith("n.") else k: v for k, v in row.items()}
                nid = flat.get("id", "")
                props = ", ".join(f"{k}: {_esc(v)}" for k, v in flat.items())
                statements.append(
                    f"MERGE (n:{table} {{id: {_esc(nid)}}}) SET n += {{{props}}};"
                )
        except Exception:
            pass

    for rel in REL_TABLES:
        try:
            r = conn.execute(f"MATCH (a)-[:{rel}]->(b) RETURN a.id AS src, b.id AS dst")
            for row in _rows(r):
                src, dst = row.get("src"), row.get("dst")
                if src and dst:
                    statements.append(
                        f"MATCH (a {{id: {_esc(src)}}}), (b {{id: {_esc(dst)}}}) "
                        f"MERGE (a)-[:{rel}]->(b);"
                    )
        except Exception:
            pass

    return statements


def relay_neo4j(
    conn: kuzu.Connection,
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "",
    database: str = "neo4j",
    cypher_only: bool = False,
) -> list[str]:
    """
    Push the graph to Neo4j.

    When cypher_only=True, returns the list of Cypher statements without
    connecting to Neo4j. Install the neo4j driver: pip install cortex[neo4j].
    """
    statements = _build_cypher_statements(conn)
    if cypher_only:
        return statements

    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise ImportError(
            "neo4j driver not installed. Run: pip install cortex[neo4j]\n"
            "Or use --cypher-only to export Cypher without connecting."
        )

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session(database=database) as session:
        for stmt in statements:
            session.run(stmt.rstrip(";"))
    driver.close()
    return statements


def relay_falkordb(
    conn: kuzu.Connection,
    host: str = "localhost",
    port: int = 6379,
    password: str = "",
    graph_name: str = "cortex",
    cypher_only: bool = False,
) -> list[str]:
    """
    Push the graph to FalkorDB (Redis-based graph database).

    When cypher_only=True, returns the list of Cypher statements without
    connecting to FalkorDB. Install the driver: pip install cortex[falkordb].
    """
    statements = _build_cypher_statements(conn)
    if cypher_only:
        return statements

    try:
        import falkordb
    except ImportError:
        raise ImportError(
            "falkordb driver not installed. Run: pip install cortex[falkordb]\n"
            "Or use --cypher-only to export Cypher without connecting."
        )

    client = falkordb.FalkorDB(host=host, port=port, password=password or None)
    graph = client.select_graph(graph_name)
    for stmt in statements:
        graph.query(stmt.rstrip(";"))
    return statements
```

- [ ] **Step 4: Add relay subcommand to cortex/main.py**

Add `relay` to `main()` subparsers:

```python
    # ── relay ────────────────────────────────────────────────────────────────
    p_relay = sub.add_parser("relay", help="Push graph to Neo4j or FalkorDB")
    p_relay.add_argument("target", choices=["neo4j", "falkordb"], help="Target graph DB")
    p_relay.add_argument("--root", default=".", metavar="DIR")
    p_relay.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j bolt URI")
    p_relay.add_argument("--host", default="localhost", help="FalkorDB host")
    p_relay.add_argument("--port", type=int, default=6379, help="FalkorDB port")
    p_relay.add_argument("--user", default="neo4j", help="Neo4j username")
    p_relay.add_argument("--password", default="", help="Database password")
    p_relay.add_argument("--database", default="neo4j", help="Neo4j database name")
    p_relay.add_argument("--graph", default="cortex", help="FalkorDB graph name")
    p_relay.add_argument("--cypher-only", action="store_true",
                         help="Print Cypher statements without connecting")
```

Add `_cmd_relay` function:

```python
def _cmd_relay(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    from core.db import DatabaseManager
    from core.relay import relay_neo4j, relay_falkordb

    mgr = DatabaseManager(root)
    mgr.init()

    if args.target == "neo4j":
        stmts = relay_neo4j(
            mgr.conn,
            uri=args.uri,
            user=args.user,
            password=args.password,
            database=args.database,
            cypher_only=args.cypher_only,
        )
    else:
        stmts = relay_falkordb(
            mgr.conn,
            host=args.host,
            port=args.port,
            password=args.password,
            graph_name=args.graph,
            cypher_only=args.cypher_only,
        )

    mgr.close()

    if args.cypher_only:
        for stmt in stmts:
            print(stmt)
    else:
        print(f"[Cortex] Relayed {len(stmts)} statements to {args.target}.")
```

Add to `main()` dispatch:
```python
    elif args.command == "relay":
        _cmd_relay(args)
```

- [ ] **Step 5: Run relay tests**

```bash
pytest tests/test_relay.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add core/relay.py tests/test_relay.py cortex/main.py
git commit -m "feat(relay): Graph Relay — push to Neo4j or FalkorDB (--cypher-only preview)"
```

---

## Task 3: Graph Reconciler (git merge driver)

**Files:**
- Create: `core/reconciler.py`
- Create: `tests/test_reconciler.py`
- Modify: `cortex/main.py` — add `reconcile` subcommand

The reconciler merges two versions of `.cortex/versions.json` using a 3-way merge strategy: union the versions arrays by `slot`, keeping the version with the highest `unix_ts` on conflict. Called as a git merge driver: `cortex reconcile %O %A %B`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reconciler.py`:

```python
import json
import pytest
from pathlib import Path
from core.reconciler import reconcile_versions


def test_reconcile_non_overlapping():
    base = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 1000, "message": "a"}]}
    ours = {"current_slot": 2, "versions": [
        {"slot": 1, "unix_ts": 1000, "message": "a"},
        {"slot": 2, "unix_ts": 2000, "message": "ours"},
    ]}
    theirs = {"current_slot": 3, "versions": [
        {"slot": 1, "unix_ts": 1000, "message": "a"},
        {"slot": 3, "unix_ts": 3000, "message": "theirs"},
    ]}
    result = reconcile_versions(base, ours, theirs)
    slots = {v["slot"] for v in result["versions"]}
    assert slots == {1, 2, 3}


def test_reconcile_conflict_keeps_newer():
    base = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 1000, "message": "a"}]}
    ours = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 2000, "message": "newer"}]}
    theirs = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 1500, "message": "older"}]}
    result = reconcile_versions(base, ours, theirs)
    assert result["versions"][0]["message"] == "newer"


def test_reconcile_preserves_up_to_max_5():
    base = {"current_slot": 0, "versions": []}
    ours = {"current_slot": 3, "versions": [
        {"slot": i, "unix_ts": i * 1000, "message": f"v{i}"} for i in range(1, 4)
    ]}
    theirs = {"current_slot": 5, "versions": [
        {"slot": i, "unix_ts": i * 1000, "message": f"v{i}"} for i in range(3, 6)
    ]}
    result = reconcile_versions(base, ours, theirs)
    assert len(result["versions"]) <= 5
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_reconciler.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'core.reconciler'`

- [ ] **Step 3: Create core/reconciler.py**

```python
"""
Graph Reconciler — 3-way merge strategy for .cortex/versions.json.

Used as a git merge driver:
  [merge "cortex-versions"]
      name = Cortex graph versions merge driver
      driver = cortex reconcile %O %A %B

git attributes (.gitattributes):
  .cortex/versions.json merge=cortex-versions
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_VERSIONS = 5


def reconcile_versions(base: dict, ours: dict, theirs: dict) -> dict:
    """
    3-way merge of versions.json metadata.

    Strategy: union all versions by slot, keeping the entry with the higher
    unix_ts on conflict. Truncate to MAX_VERSIONS (5) oldest-first.
    """
    by_slot: dict[int, dict] = {}

    for v in base.get("versions", []):
        slot = v.get("slot")
        if slot is not None:
            by_slot[slot] = v

    for v in ours.get("versions", []):
        slot = v.get("slot")
        if slot is None:
            continue
        existing = by_slot.get(slot)
        if existing is None or v.get("unix_ts", 0) > existing.get("unix_ts", 0):
            by_slot[slot] = v

    for v in theirs.get("versions", []):
        slot = v.get("slot")
        if slot is None:
            continue
        existing = by_slot.get(slot)
        if existing is None or v.get("unix_ts", 0) > existing.get("unix_ts", 0):
            by_slot[slot] = v

    merged = sorted(by_slot.values(), key=lambda v: v.get("unix_ts", 0))
    if len(merged) > MAX_VERSIONS:
        merged = merged[-MAX_VERSIONS:]

    current_slot = merged[-1]["slot"] if merged else 0
    return {"current_slot": current_slot, "versions": merged}


def reconcile_files(base_path: str, ours_path: str, theirs_path: str) -> int:
    """
    Read three versions.json files, merge them, write result to ours_path.
    Returns 0 on success, 1 on error. Intended for use as a git merge driver.
    """
    try:
        base = json.loads(Path(base_path).read_text())
        ours = json.loads(Path(ours_path).read_text())
        theirs = json.loads(Path(theirs_path).read_text())
    except Exception as exc:
        print(f"[cortex reconcile] Error reading merge inputs: {exc}", file=sys.stderr)
        return 1

    result = reconcile_versions(base, ours, theirs)
    Path(ours_path).write_text(json.dumps(result, indent=2))
    return 0
```

- [ ] **Step 4: Add reconcile subcommand to cortex/main.py**

Add parser:
```python
    # ── reconcile (git merge driver — not shown in --help) ──────────────────
    p_rec = sub.add_parser("reconcile", add_help=False)
    p_rec.add_argument("base")
    p_rec.add_argument("ours")
    p_rec.add_argument("theirs")
```

Add dispatch:
```python
    elif args.command == "reconcile":
        from core.reconciler import reconcile_files
        sys.exit(reconcile_files(args.base, args.ours, args.theirs))
```

Add function:
```python
def _cmd_reconcile(args: argparse.Namespace) -> None:
    from core.reconciler import reconcile_files
    sys.exit(reconcile_files(args.base, args.ours, args.theirs))
```

- [ ] **Step 5: Run reconciler tests**

```bash
pytest tests/test_reconciler.py -v
```
Expected: 3 PASSED

- [ ] **Step 6: Print gitattributes setup instructions**

In `cortex/main.py`, update `_cmd_init` to print merge driver setup instructions:

After the hook reminder line, add:
```python
    print()
    print("Optional: to enable the Graph Reconciler merge driver, add to your project:")
    print("  echo '.cortex/versions.json merge=cortex-versions' >> .gitattributes")
    print("  git config merge.cortex-versions.driver 'cortex reconcile %O %A %B'")
```

- [ ] **Step 7: Commit**

```bash
git add core/reconciler.py tests/test_reconciler.py cortex/main.py
git commit -m "feat(reconciler): Graph Reconciler — 3-way merge driver for .cortex/versions.json"
```

---

## Task 4: Cortex Connect (Interactive Installer)

**Files:**
- Create: `cortex/connect.py`
- Modify: `cortex/main.py` — add `connect` subcommand

Cortex Connect is an interactive checkbox installer. It shows 9 AI tool platforms, lets the user toggle with SPACE, confirms with ENTER, then writes the MCP config to each selected platform's config file.

- [ ] **Step 1: Create cortex/connect.py**

```python
"""
Cortex Connect — interactive MCP config installer.

Displays a checkbox list of AI tool platforms. User toggles with SPACE,
confirms with ENTER. Writes the Cortex MCP config to selected platform
config files.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PLATFORMS = [
    {
        "name": "Claude Code",
        "key": "claude-code",
        "config_path": "~/.claude/settings.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Cursor",
        "key": "cursor",
        "config_path": "~/.cursor/mcp.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Gemini CLI",
        "key": "gemini",
        "config_path": "~/.gemini/settings.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Codex CLI",
        "key": "codex",
        "config_path": "~/.codex/config.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Windsurf",
        "key": "windsurf",
        "config_path": "~/.codeium/windsurf/mcp_config.json",
        "config_key": "mcpServers",
    },
    {
        "name": "VS Code Copilot Chat",
        "key": "vscode",
        "config_path": "~/.vscode/mcp.json",
        "config_key": "servers",
    },
    {
        "name": "Amp",
        "key": "amp",
        "config_path": "~/.amp/mcp.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Kiro",
        "key": "kiro",
        "config_path": "~/.kiro/settings/mcp.json",
        "config_key": "mcpServers",
    },
    {
        "name": "OpenCode",
        "key": "opencode",
        "config_path": "~/.config/opencode/config.json",
        "config_key": "mcp.servers",
    },
]


def _mcp_entry(cortex_bin: str, project_root: str) -> dict:
    return {
        "command": cortex_bin,
        "args": ["mcp", "--root", project_root],
    }


def _write_config(platform: dict, entry: dict) -> tuple[bool, str]:
    """Write or update the MCP server entry for a platform. Returns (success, message)."""
    config_path = Path(platform["config_path"]).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    key = platform["config_key"]

    # Handle nested keys like "mcp.servers"
    if "." in key:
        parts = key.split(".", 1)
        if parts[0] not in existing:
            existing[parts[0]] = {}
        existing[parts[0]][parts[1]] = existing.get(parts[0], {}).get(parts[1], {})
        existing[parts[0]][parts[1]]["cortex"] = entry
    else:
        if key not in existing:
            existing[key] = {}
        existing[key]["cortex"] = entry

    try:
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return True, f"Written to {config_path}"
    except Exception as exc:
        return False, f"Failed: {exc}"


def _find_cortex_bin() -> str:
    """Find the cortex binary path (sys.executable's sibling or PATH)."""
    import shutil
    which = shutil.which("cortex")
    if which:
        return which
    # Fallback: use the same Python as the current process
    scripts_dir = Path(sys.executable).parent
    for name in ("cortex", "cortex.exe"):
        candidate = scripts_dir / name
        if candidate.exists():
            return str(candidate)
    return "cortex"


def _checkbox_ui(platforms: list[dict]) -> list[str]:
    """
    Interactive checkbox UI (pure terminal, no npm).
    Returns list of selected platform keys.

    Controls:
      UP/DOWN arrows — move cursor
      SPACE — toggle selection
      ENTER — confirm
      q — quit without installing
    """
    import tty
    import termios

    selected = set()
    cursor = 0
    N = len(platforms)

    def _render():
        # Move cursor to top of the list
        sys.stdout.write(f"\033[{N + 3}A")
        sys.stdout.write("\033[0J")  # clear to end of screen
        sys.stdout.write("\r\n")
        sys.stdout.write("  Cortex Connect — select AI tools to install MCP config\r\n")
        sys.stdout.write("  SPACE=toggle  ENTER=install  q=quit\r\n\r\n")
        for i, p in enumerate(platforms):
            check = "●" if p["key"] in selected else "○"
            arrow = ">" if i == cursor else " "
            sys.stdout.write(f"  {arrow} [{check}] {p['name']}\r\n")
        sys.stdout.flush()

    # Initial render
    for _ in range(N + 3):
        sys.stdout.write("\r\n")
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            _render()
            ch = sys.stdin.read(1)
            if ch == "\r" or ch == "\n":
                break
            elif ch in ("q", "Q"):
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                sys.stdout.write("\r\n[Cortex Connect] Aborted.\r\n")
                sys.stdout.flush()
                return []
            elif ch == " ":
                key = platforms[cursor]["key"]
                if key in selected:
                    selected.discard(key)
                else:
                    selected.add(key)
            elif ch == "\x1b":  # escape sequence
                seq = sys.stdin.read(2)
                if seq == "[A":  # up
                    cursor = max(0, cursor - 1)
                elif seq == "[B":  # down
                    cursor = min(N - 1, cursor + 1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    sys.stdout.write("\r\n")
    sys.stdout.flush()
    return list(selected)


def _checkbox_ui_windows(platforms: list[dict]) -> list[str]:
    """Fallback checkbox UI for Windows (no tty/termios)."""
    print("\nCortex Connect — select AI tools to install MCP config")
    print("Enter numbers separated by spaces (e.g. 1 3 5), or 'all', or 'q' to quit:\n")
    for i, p in enumerate(platforms, 1):
        print(f"  {i}. {p['name']}")
    print()
    choice = input("Your selection: ").strip()
    if not choice or choice.lower() == "q":
        return []
    if choice.lower() == "all":
        return [p["key"] for p in platforms]
    selected = []
    for part in choice.split():
        try:
            idx = int(part) - 1
            if 0 <= idx < len(platforms):
                selected.append(platforms[idx]["key"])
        except ValueError:
            pass
    return selected


def run_connect(project_root: Path, preselect: list[str] | None = None) -> None:
    """Run the interactive Cortex Connect installer."""
    cortex_bin = _find_cortex_bin()
    root_str = str(project_root)

    if preselect is not None:
        selected_keys = preselect
    elif sys.platform == "win32":
        selected_keys = _checkbox_ui_windows(PLATFORMS)
    else:
        try:
            selected_keys = _checkbox_ui(PLATFORMS)
        except Exception:
            selected_keys = _checkbox_ui_windows(PLATFORMS)

    if not selected_keys:
        print("[Cortex Connect] No platforms selected. Nothing installed.")
        return

    entry = _mcp_entry(cortex_bin, root_str)
    print(f"\n[Cortex Connect] Installing for: {', '.join(selected_keys)}\n")

    for platform in PLATFORMS:
        if platform["key"] not in selected_keys:
            continue
        ok, msg = _write_config(platform, entry)
        icon = "✓" if ok else "✗"
        print(f"  {icon} {platform['name']}: {msg}")

    print(f"\n[Cortex Connect] Done. MCP binary: {cortex_bin}")
    print("  Start the MCP server with: cortex mcp --root <project-root>")
```

- [ ] **Step 2: Add connect subcommand to cortex/main.py**

Add parser:
```python
    # ── connect ──────────────────────────────────────────────────────────────
    p_connect = sub.add_parser("connect", help="Install Cortex MCP config into AI tool configs")
    p_connect.add_argument("--root", default=".", metavar="DIR",
                           help="Project root (default: current directory)")
    p_connect.add_argument("--select", nargs="*", metavar="PLATFORM",
                           help="Non-interactive: pre-select platforms by key")
```

Add dispatch:
```python
    elif args.command == "connect":
        _cmd_connect(args)
```

Add function:
```python
def _cmd_connect(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    from cortex.connect import run_connect
    run_connect(root, preselect=args.select)
```

- [ ] **Step 3: Smoke-test connect in non-interactive mode**

```bash
python -c "
from pathlib import Path
from cortex.connect import run_connect
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    # --select with no platforms = nothing installed
    run_connect(Path(d), preselect=[])
print('connect ran without error')
"
```
Expected: prints "[Cortex Connect] No platforms selected."

- [ ] **Step 4: Commit**

```bash
git add cortex/connect.py cortex/main.py
git commit -m "feat(connect): Cortex Connect — interactive MCP config installer for 9 AI tool platforms"
```

---

## Task 5: pyproject.toml Optional Extras

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add optional extras to pyproject.toml**

```toml
[project.optional-dependencies]
analysis = [
    "leidenalg>=0.10.0",
    "python-igraph>=0.11.0",
]
svg = [
    "cairosvg>=2.7.0",
]
neo4j = [
    "neo4j>=5.0.0",
]
falkordb = [
    "falkordb>=1.0.0",
]
```

- [ ] **Step 2: Verify pyproject.toml parses correctly**

```bash
python -c "import tomllib; tomllib.loads(open('pyproject.toml').read()); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add optional extras [analysis], [svg], [neo4j], [falkordb] to pyproject.toml"
```

---

Phase 4 complete. Delivers: Graph Export (GraphML/Obsidian/wiki/SVG), Graph Relay (Neo4j/FalkorDB), Graph Reconciler (git merge driver), Cortex Connect (interactive installer).
