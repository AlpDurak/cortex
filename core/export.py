"""
Graph Export — converts the Kùzu graph to external formats.

Functions:
  export_graphml(conn) -> str
  export_obsidian(conn, output_dir)
  export_wiki(conn, project_root) -> str
  export_svg(conn) -> str
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


def export_graphml(conn: kuzu.Connection) -> str:
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


def export_obsidian(conn: kuzu.Connection, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    nodes = _get_all_nodes(conn)
    edges = _get_all_edges(conn)

    node_by_id = {n.get("id"): n for n in nodes}

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


def export_wiki(conn: kuzu.Connection, project_root: Path) -> str:
    nodes = _get_all_nodes(conn)
    edges = _get_all_edges(conn)

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


def export_svg(conn: kuzu.Connection) -> str:
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
    total_rows = (len(nodes) + COLS - 1) // COLS if nodes else 1
    SVG_W = PADDING * 2 + total_cols * (NODE_W + GAP_X)
    SVG_H = PADDING * 2 + total_rows * (NODE_H + GAP_Y) + 20

    TYPE_COLORS = {
        "File": "#3b82f6",
        "SystemDesign": "#7c3aed",
        "Service": "#ea580c",
        "Database": "#059669",
        "Infrastructure": "#6b7280",
        "NodeGroup": "#7c3aed",
    }

    def _esc(s: str) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SVG_W}" height="{SVG_H}">',
        f'  <rect width="{SVG_W}" height="{SVG_H}" fill="#1e1e1e"/>',
    ]

    for e in edges:
        src_pos = positions.get(e["src"])
        dst_pos = positions.get(e["dst"])
        if src_pos and dst_pos:
            lines.append(
                f'  <line x1="{src_pos[0]}" y1="{src_pos[1]}" '
                f'x2="{dst_pos[0]}" y2="{dst_pos[1]}" '
                f'stroke="#555" stroke-width="1" opacity="0.6"/>'
            )

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
