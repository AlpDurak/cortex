# Cortex UI Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pill-shaped icon nodes, clean up dead UI elements, add Node Search / Edge Filter / Minimap / Export Graph features, and promote SystemDesign into a hierarchical sectioned knowledge layer with new schema columns, rel types, and MCP tools.

**Architecture:** All UI changes live in `static/canvas.js` and `static/index.html`. Backend changes are confined to `core/db.py` (schema) and `cortex/mcp_server.py` (tools). No new files are created — every change extends an existing file.

**Tech Stack:** Kùzu graph DB (Python), FastMCP, FastAPI, Vis-Network 9.1.9, vanilla JS/CSS, inline SVG data-URIs for node images.

---

## File Map

| File | What changes |
|---|---|
| `core/db.py` | Add `section`/`rationale` columns to SystemDesign; add 5 new rel tables; migrate existing live DBs via `ALTER TABLE` |
| `cortex/mcp_server.py` | Update `write_system_design_node` (new params, new valid rels); add `list_design_sections` tool |
| `static/canvas.js` | Pill SVG node images; section group `beforeDrawing`; minimap `afterDrawing`; search + filter helpers; export; new rel colours |
| `static/index.html` | Remove dead elements; add Search/Filter panels; Export dropdown; minimap `<canvas>`; updated inspector for SystemDesign |

---

### Task 1: DB schema — new SystemDesign columns + new rel tables

**Files:**
- Modify: `core/db.py`

- [ ] **Step 1: Add `section` and `rationale` to SystemDesign DDL and add migration**

Replace the `SystemDesign` entry in `_NODE_TABLES` and add a `_migrate_schema` function:

```python
# In _NODE_TABLES, replace SystemDesign block (lines 33-42):
    """
    CREATE NODE TABLE IF NOT EXISTS SystemDesign(
        id STRING,
        name STRING,
        description STRING,
        code_block STRING,
        design_type STRING,
        status STRING,
        section STRING,
        rationale STRING,
        PRIMARY KEY (id)
    )
    """,
```

```python
# Add 5 new entries to _REL_TABLES (append after HOSTED_ON line):
    "CREATE REL TABLE IF NOT EXISTS IMPLEMENTS(FROM SystemDesign TO File)",
    "CREATE REL TABLE IF NOT EXISTS PART_OF(FROM SystemDesign TO SystemDesign)",
    "CREATE REL TABLE IF NOT EXISTS USES(FROM SystemDesign TO Service)",
    "CREATE REL TABLE IF NOT EXISTS STORES_IN(FROM SystemDesign TO Database)",
    "CREATE REL TABLE IF NOT EXISTS RUNS_ON(FROM SystemDesign TO Infrastructure)",
```

```python
# Add this function after _apply_schema():
def _migrate_schema(conn: kuzu.Connection) -> None:
    """Add columns to existing tables that were created before this version."""
    migrations = [
        "ALTER TABLE SystemDesign ADD section STRING DEFAULT ''",
        "ALTER TABLE SystemDesign ADD rationale STRING DEFAULT ''",
    ]
    for ddl in migrations:
        try:
            conn.execute(ddl)
        except Exception:
            pass  # column already exists
```

- [ ] **Step 2: Call `_migrate_schema` in `DatabaseManager.init()`**

In `init()`, after `_apply_schema(self._conn)`, add:

```python
        _migrate_schema(self._conn)
```

- [ ] **Step 3: Verify server starts without error**

```bash
cd C:\Users\USER\Documents\Code\cortex
python -c "from core.db import DatabaseManager; from pathlib import Path; m = DatabaseManager(Path('.')); m.init(); print('OK'); m.close()"
```

Expected: `OK` with no traceback.

- [ ] **Step 4: Commit**

```bash
git add core/db.py
git commit -m "feat: add SystemDesign section/rationale columns and new rel tables"
```

---

### Task 2: MCP — update `write_system_design_node` + add `list_design_sections`

**Files:**
- Modify: `cortex/mcp_server.py`

- [ ] **Step 1: Expand `valid_rels` and update `write_system_design_node` signature**

Replace the entire `write_system_design_node` function (lines 225–354) with:

```python
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
      IMPLEMENTS  → File           (this design is implemented in that file)
      PART_OF     → SystemDesign   (this design is part of a broader design)
      USES        → Service        (this design depends on that external service)
      STORES_IN   → Database       (this design stores data in that database)
      RUNS_ON     → Infrastructure (this design runs on that infra node)
      MODIFIES    → File           (this design modifies that file)
      TALKS_TO    → Service        (this design communicates with that service)

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
```

- [ ] **Step 2: Add `list_design_sections` tool** — insert after `write_system_design_node`:

```python
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
```

- [ ] **Step 3: Update MCP server instructions string** (line 61–65):

```python
mcp = FastMCP(
    name="cortex",
    instructions=(
        "Cortex is a knowledge graph MCP server for software projects. "
        "SystemDesign node IDs follow the format SystemDesign:Section:Name "
        "(e.g. SystemDesign:Auth:GoogleOAuth). "
        "ALWAYS call list_design_sections first to understand the project architecture. "
        "Use explore_neighborhood to drill into specific nodes. "
        "Use write_system_design_node to document new design decisions with connects_to edges. "
        "Call commit_snapshot via /api/commit before any git commit."
    ),
)
```

- [ ] **Step 4: Verify MCP tools list**

```bash
cd C:\Users\USER\Documents\Code\cortex
python -c "from cortex.mcp_server import mcp; print([t.name for t in mcp._tool_manager.tools.values()])"
```

Expected output contains: `['get_graph_timeline', 'query_graph_diff', 'explore_neighborhood', 'find_structural_path', 'write_system_design_node', 'list_design_sections']`

- [ ] **Step 5: Commit**

```bash
git add cortex/mcp_server.py
git commit -m "feat: update write_system_design_node with section/rationale, add list_design_sections tool"
```

---

### Task 3: HTML — remove dead elements, restructure sidebar panels

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Remove `#canvas-placeholder` block** (lines 341–348)

Delete from index.html:
```html
      <div id="canvas-placeholder">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
          <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
        </svg>
        <p>Graph canvas loads in Phase 5</p>
      </div>
```

Also delete the CSS rule for `#canvas-placeholder` (lines 213–222).

- [ ] **Step 2: Replace icon dock buttons — remove inspector btn, add filter btn**

Replace the entire `<div id="icon-dock">` contents (lines 301–314) with:

```html
  <div id="icon-dock">
    <button class="dock-btn active" id="btn-timeline" title="Timeline" onclick="setActivePanel('timeline')">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><polyline points="12 6 12 12 16.5 12"/></svg>
    </button>
    <button class="dock-btn" id="btn-search" title="Search Nodes" onclick="setActivePanel('search')">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="16.65" y1="16.65" x2="21" y2="21"/></svg>
    </button>
    <button class="dock-btn" id="btn-filter" title="Edge Filters" onclick="setActivePanel('filter')">
      <svg viewBox="0 0 24 24"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
    </button>
  </div>
```

- [ ] **Step 3: Add Search and Filter panel HTML** — inside `#secondary-sidebar`, before `#timeline-panel`:

```html
    <!-- SEARCH PANEL -->
    <div id="search-panel" style="display:none; flex-direction:column; flex-shrink:0; border-bottom:1px solid var(--border)">
      <div class="panel-header">Node Search</div>
      <div style="padding:0 10px 10px">
        <input id="search-input" type="text" placeholder="Name or ID…"
          style="width:100%;padding:5px 8px;background:var(--bg);border:1px solid var(--border);
                 border-radius:4px;color:var(--text-bright);font-size:12px;outline:none"
          oninput="onSearchInput(this.value)" />
        <ul id="search-results" style="list-style:none;margin-top:6px;max-height:180px;overflow-y:auto"></ul>
      </div>
    </div>

    <!-- FILTER PANEL -->
    <div id="filter-panel" style="display:none; flex-direction:column; flex-shrink:0; border-bottom:1px solid var(--border)">
      <div class="panel-header">Edge Filters</div>
      <div id="filter-toggles" style="padding:6px 10px 10px;display:flex;flex-wrap:wrap;gap:6px"></div>
    </div>
```

- [ ] **Step 4: Add panel show/hide CSS** — add inside `<style>`:

```css
    /* Sidebar panel visibility */
    .sidebar-panel { display: flex; flex-direction: column; }
    .sidebar-panel.hidden { display: none !important; }

    /* Search result items */
    #search-results li {
      padding: 4px 6px; border-radius: 4px; cursor: pointer;
      font-size: 11px; font-family: 'Cascadia Code', 'Fira Code', monospace;
      color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    #search-results li:hover { background: var(--bg-hover); }

    /* Filter toggle pills */
    .filter-pill {
      padding: 2px 10px; border-radius: 10px; font-size: 11px; cursor: pointer;
      border: 1px solid var(--border); color: var(--text); background: var(--bg-panel);
      transition: background 0.1s, color 0.1s;
    }
    .filter-pill.active { background: var(--accent); color: #fff; border-color: var(--accent); }
```

- [ ] **Step 5: Rewrite `setActivePanel` JS function** (lines 664–668):

```js
function setActivePanel(panel) {
  _activePanel = panel;
  document.querySelectorAll('.dock-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + panel)?.classList.add('active');

  const panels = { timeline: 'timeline-panel', search: 'search-panel', filter: 'filter-panel' };
  Object.values(panels).forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  const active = document.getElementById(panels[panel]);
  if (active) active.style.display = 'flex';

  if (panel === 'filter') buildFilterToggles();
}
```

- [ ] **Step 6: Make timeline panel default to flex** — update `#timeline-panel` CSS:

```css
    #timeline-panel { flex: 0 0 auto; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; }
```

- [ ] **Step 7: Remove `_activePanel` variable and dead reference** — delete `let _activePanel = 'timeline';` from the JS state block.

- [ ] **Step 8: Verify page loads without JS errors**

Start the server (`python -m cortex.web_server` or however it's run) and open the browser. Check console for errors.

- [ ] **Step 9: Commit**

```bash
git add static/index.html
git commit -m "feat: restructure sidebar panels, remove dead UI elements, add Search/Filter panel slots"
```

---

### Task 4: HTML — Export button + dropdown

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add Export button HTML in `#header`** — insert before `#header-commit-btn`:

```html
  <div style="position:relative">
    <button id="export-btn" onclick="toggleExportMenu()" style="
      background:var(--bg-panel);color:var(--text);border:1px solid var(--border);
      border-radius:4px;padding:4px 10px;font-size:12px;cursor:pointer;
      display:flex;align-items:center;gap:5px">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
      Export
    </button>
    <div id="export-menu" style="
      display:none;position:absolute;right:0;top:32px;
      background:var(--bg-panel);border:1px solid var(--border);border-radius:6px;
      min-width:140px;z-index:200;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.4)">
      <div class="export-item" onclick="exportGraph('png')">PNG Screenshot</div>
      <div class="export-item" onclick="exportGraph('json')">JSON Graph</div>
      <div class="export-item" onclick="exportGraph('triples')">Semantic Triples</div>
    </div>
  </div>
```

- [ ] **Step 2: Add export CSS** — inside `<style>`:

```css
    .export-item {
      padding: 8px 14px; font-size: 12px; cursor: pointer; color: var(--text);
    }
    .export-item:hover { background: var(--bg-hover); }
```

- [ ] **Step 3: Add export JS functions** — add to the `<script>` block:

```js
function toggleExportMenu() {
  const menu = document.getElementById('export-menu');
  menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}

// Close export menu on outside click
document.addEventListener('click', function(e) {
  if (!e.target.closest('#export-btn') && !e.target.closest('#export-menu')) {
    const menu = document.getElementById('export-menu');
    if (menu) menu.style.display = 'none';
  }
});

function exportGraph(format) {
  document.getElementById('export-menu').style.display = 'none';
  if (format === 'png') {
    // canvas.js exposes the network; get vis-network's underlying canvas
    const net = window._cortexNetwork;
    if (!net) return;
    const canvas = net.canvas.frame.canvas;
    const link = document.createElement('a');
    link.download = 'cortex-graph.png';
    link.href = canvas.toDataURL('image/png');
    link.click();
  } else if (format === 'json') {
    const blob = new Blob(
      [JSON.stringify({ nodes: _nodes, edges: _edges }, null, 2)],
      { type: 'application/json' }
    );
    _download(blob, 'cortex-graph.json');
  } else if (format === 'triples') {
    const nodeMap = Object.fromEntries(_nodes.map(n => [n.id, n.name || n.id]));
    const lines = _edges.map(e =>
      `(${nodeMap[e.src] || e.src})-[${e.rel}]->(${nodeMap[e.dst] || e.dst})`
    );
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    _download(blob, 'cortex-triples.txt');
  }
}

function _download(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat: add Export button with PNG/JSON/Triples download"
```

---

### Task 5: canvas.js — Pill node SVG images

**Files:**
- Modify: `static/canvas.js`

- [ ] **Step 1: Add `NODE_ICONS` map** — insert after `REL_COLORS` block (after line 37):

```js
  // SVG path data (Lucide icons, 15×15 viewport centered in 15×15 box)
  const NODE_ICONS = {
    File: {
      paths: [
        { d: 'M13 2H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z', fill: 'none' },
        { d: 'M13 2v5h5', fill: 'none' },
      ],
    },
    SystemDesign: {
      paths: [
        { d: 'M11 19H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5', fill: 'none' },
        { d: 'M14 2l4 4-7 7H7v-4z', fill: 'none' },
      ],
    },
    Service: {
      paths: [
        { d: 'M2 3h18a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', fill: 'none' },
        { d: 'M8 21h6', fill: 'none' },
        { d: 'M12 17v4', fill: 'none' },
      ],
    },
    Database: {
      paths: [
        { d: 'M12 2C7.03 2 3 3.79 3 6v2c0 2.21 4.03 4 9 4s9-1.79 9-4V6c0-2.21-4.03-4-9-4z', fill: 'none' },
        { d: 'M3 8v4c0 2.21 4.03 4 9 4s9-1.79 9-4V8', fill: 'none' },
        { d: 'M3 12v4c0 2.21 4.03 4 9 4s9-1.79 9-4v-4', fill: 'none' },
      ],
    },
    Infrastructure: {
      paths: [
        { d: 'M2 2h18a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z', fill: 'none' },
        { d: 'M2 12h18a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2z', fill: 'none' },
        { d: 'M6 6h.01', fill: 'none' },
        { d: 'M6 16h.01', fill: 'none' },
      ],
    },
  };
```

- [ ] **Step 2: Add `buildNodeSVG()` and `buildNodeImage()` functions** — insert after `NODE_ICONS`:

```js
  function svgEsc(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function buildNodeSVG(node) {
    const colors = TYPE_COLORS[node.label] || COLOR_DEFAULT;
    const bg     = colors.background;
    const border = colors.border;
    // dark text for light backgrounds
    const textColor = '#1f2937';
    const name  = truncate(node.name || node.id || '', 28);
    const charW = 7.5;
    const W     = Math.max(130, 44 + name.length * charW + 18);
    const H     = 38;
    const r     = 19;   // pill corner radius
    const cx    = 21;   // circle centre X
    const cy    = 19;   // circle centre Y
    const cr    = 15;   // circle radius

    const iconDefs = NODE_ICONS[node.label];
    let iconPaths = '';
    if (iconDefs) {
      // Scale icon paths from ~24×24 to fit in 15×15, centred at (cx,cy)
      const scale = 0.6;
      const ox = cx - 24 * scale / 2;
      const oy = cy - 24 * scale / 2;
      iconPaths = iconDefs.paths.map(p =>
        `<path d="${svgEsc(p.d)}" transform="translate(${ox.toFixed(1)},${oy.toFixed(1)}) scale(${scale})"
          fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`
      ).join('');
    }

    return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
  <rect x="1" y="1" width="${W-2}" height="${H-2}" rx="${r}" ry="${r}"
    fill="${svgEsc(bg)}" stroke="${svgEsc(border)}" stroke-width="2"/>
  <circle cx="${cx}" cy="${cy}" r="${cr}" fill="${svgEsc(border)}"/>
  ${iconPaths}
  <text x="${cx + cr + 10}" y="${cy + 5}"
    font-family="Cascadia Code, Fira Code, Consolas, monospace"
    font-size="13" font-weight="600" fill="${svgEsc(textColor)}">${svgEsc(name)}</text>
</svg>`;
  }

  function buildNodeImage(node) {
    const svg = buildNodeSVG(node);
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }

  function nodeWidth(node) {
    const name = truncate(node.name || node.id || '', 28);
    return Math.max(130, 44 + name.length * 7.5 + 18);
  }
```

- [ ] **Step 3: Update `toVisNode()` to use image shape** — replace the `toVisNode` function (lines 148–161):

```js
  function toVisNode(node, diffData) {
    const isDashed = diffData && diffData.deleted_nodes && diffData.deleted_nodes.includes(node.id);
    const diffColor = diffData ? resolveDiffColor(node, diffData) : null;

    const visNode = {
      id: node.id,
      shape: 'image',
      image: buildNodeImage(node),
      label: '',
      width: nodeWidth(node),
      height: 38,
      title: buildTooltip(node),
      shapeProperties: { useBorderWithImage: false, borderDashes: isDashed ? [5, 3] : false },
      _raw: node,
    };

    // Diff overlay: tint border around the pill image
    if (diffColor) {
      visNode.color = { border: diffColor.border, background: 'transparent',
                        highlight: { border: diffColor.border, background: 'transparent' } };
      visNode.borderWidth = 3;
      visNode.shapeProperties = { ...visNode.shapeProperties, borderDashes: false };
    }

    return visNode;
  }

  function resolveDiffColor(node, diffData) {
    if (!diffData) return null;
    if (diffData.added_nodes && diffData.added_nodes.includes(node.id))    return DIFF_ADDED;
    if (diffData.deleted_nodes && diffData.deleted_nodes.includes(node.id)) return DIFF_DELETED;
    if (diffData.modified_nodes && diffData.modified_nodes.includes(node.id)) return DIFF_MODIFIED;
    return null;
  }
```

- [ ] **Step 4: Remove old `resolveNodeColor` and `buildNodeLabel`** — delete functions `resolveNodeColor` (lines 194–201) and `buildNodeLabel` (lines 203–208) entirely, since they are replaced by the image approach.

- [ ] **Step 5: Update `VIS_OPTIONS.nodes`** — remove `shape`, `margin`, `font` from global defaults (they don't apply to image nodes):

```js
  const VIS_OPTIONS = {
    nodes: {
      borderWidth: 2,
      shadow: { enabled: true, color: 'rgba(0,0,0,0.15)', size: 6, x: 2, y: 2 },
      chosen: {
        node: function (values) {
          values.borderWidth = 3;
          values.shadowSize = 10;
        },
      },
    },
    edges: { /* unchanged */ },
    interaction: { /* unchanged */ },
    physics: { /* unchanged */ },
    layout: { /* unchanged */ },
  };
```

- [ ] **Step 6: Add new rel colours** — extend `REL_COLORS`:

```js
  const REL_COLORS = {
    CONTAINS:    '#94a3b8',
    MODIFIES:    '#a78bfa',
    DEPENDS_ON:  '#60a5fa',
    QUERIES:     '#34d399',
    TALKS_TO:    '#fb923c',
    HOSTED_ON:   '#9ca3af',
    IMPLEMENTS:  '#c084fc',
    PART_OF:     '#818cf8',
    USES:        '#f97316',
    STORES_IN:   '#10b981',
    RUNS_ON:     '#6b7280',
  };
```

- [ ] **Step 7: Remove canvas-placeholder references** in `bootstrap()` and `render()` and `addNode()` — delete all lines that reference `canvas-placeholder`:

In `bootstrap()` delete:
```js
    const placeholder = document.getElementById('canvas-placeholder');
```
and:
```js
    _network.once('stabilizationIterationsDone', () => {
      if (placeholder) placeholder.style.display = 'none';
    });
```
and the `beforeDrawing` block that hides placeholder.

In `render()` delete:
```js
    const placeholder = document.getElementById('canvas-placeholder');
    if (placeholder && nodes.length > 0) placeholder.style.display = 'none';
```

In `addNode()` delete:
```js
    const placeholder = document.getElementById('canvas-placeholder');
    if (placeholder) placeholder.style.display = 'none';
```

- [ ] **Step 8: Smoke test — start server and verify nodes render as pills**

Start `python -m cortex.web_server` (or `uvicorn cortex.web_server:app`) from the project root, open http://localhost:8000, add a test node via the MCP or seed script, verify the pill shape appears.

- [ ] **Step 9: Commit**

```bash
git add static/canvas.js
git commit -m "feat: pill SVG node images with per-type Lucide icons"
```

---

### Task 6: canvas.js — SystemDesign section group backgrounds

**Files:**
- Modify: `static/canvas.js`

- [ ] **Step 1: Add `drawSectionGroups()` function** — insert before `bootstrap()`:

```js
  function drawSectionGroups(ctx) {
    if (!_visNodes || !_network) return;

    // Group nodes by section field
    const groups = {};
    _visNodes.forEach(visNode => {
      const raw = visNode._raw;
      if (!raw || raw.label !== 'SystemDesign') return;
      const section = raw.section;
      if (!section) return;
      if (!groups[section]) groups[section] = [];
      groups[section].push(visNode.id);
    });

    const positions = _network.getPositions();

    Object.entries(groups).forEach(([section, nodeIds]) => {
      if (nodeIds.length < 1) return;
      const pts = nodeIds.map(id => positions[id]).filter(Boolean);
      if (!pts.length) return;

      const pad = 40;
      const minX = Math.min(...pts.map(p => p.x)) - pad;
      const maxX = Math.max(...pts.map(p => p.x)) + pad + 160; // node width
      const minY = Math.min(...pts.map(p => p.y)) - pad;
      const maxY = Math.max(...pts.map(p => p.y)) + pad + 38;  // node height
      const w = maxX - minX;
      const h = maxY - minY;
      const r = 12;

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(minX + r, minY);
      ctx.arcTo(maxX, minY, maxX, maxY, r);
      ctx.arcTo(maxX, maxY, minX, maxY, r);
      ctx.arcTo(minX, maxY, minX, minY, r);
      ctx.arcTo(minX, minY, maxX, minY, r);
      ctx.closePath();
      ctx.fillStyle = 'rgba(124,58,237,0.06)';
      ctx.fill();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = 'rgba(124,58,237,0.35)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.setLineDash([]);

      // Section label
      ctx.font = '700 10px "Segoe UI", system-ui, sans-serif';
      ctx.fillStyle = 'rgba(167,139,250,0.9)';
      ctx.letterSpacing = '1px';
      ctx.fillText(section.toUpperCase(), minX + 10, minY + 14);
      ctx.restore();
    });
  }
```

- [ ] **Step 2: Hook `drawSectionGroups` into `beforeDrawing`** — add inside `bootstrap()`, after `_network` is created:

```js
    _network.on('beforeDrawing', function(ctx) {
      drawSectionGroups(ctx);
    });
```

- [ ] **Step 3: Verify group boxes appear**

Add two SystemDesign nodes with the same `section` via `write_system_design_node`, open the UI, confirm a purple dashed box surrounds them.

- [ ] **Step 4: Commit**

```bash
git add static/canvas.js
git commit -m "feat: SystemDesign section group background regions on canvas"
```

---

### Task 7: canvas.js + HTML — Minimap

**Files:**
- Modify: `static/index.html`, `static/canvas.js`

- [ ] **Step 1: Add minimap `<canvas>` to `#canvas-wrapper`** — in `index.html`, inside `#canvas-wrapper` after `#graph-canvas`:

```html
      <canvas id="minimap-canvas" style="
        position:absolute; bottom:48px; right:12px;
        width:130px; height:90px;
        background:rgba(26,26,26,0.92); border:1px solid #3c3c3c;
        border-radius:6px; cursor:pointer; z-index:10;
      "></canvas>
```

- [ ] **Step 2: Add `initMinimap()` and `renderMinimap()` functions** — insert in `canvas.js` before `onReady()`:

```js
  let _minimapCanvas = null;

  function initMinimap() {
    _minimapCanvas = document.getElementById('minimap-canvas');
    if (!_minimapCanvas) return;
    // Retina/HiDPI scaling
    const dpr = window.devicePixelRatio || 1;
    _minimapCanvas.width  = 130 * dpr;
    _minimapCanvas.height = 90  * dpr;
    const mctx = _minimapCanvas.getContext('2d');
    mctx.scale(dpr, dpr);

    _minimapCanvas.addEventListener('click', function(e) {
      if (!_network) return;
      const rect = _minimapCanvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) / rect.width;
      const my = (e.clientY - rect.top)  / rect.height;
      const { minX, maxX, minY, maxY } = minimapBounds();
      if (!minX && minX !== 0) return;
      const gx = minX + mx * (maxX - minX);
      const gy = minY + my * (maxY - minY);
      _network.moveTo({ position: { x: gx, y: gy }, animation: { duration: 300, easingFunction: 'easeInOutQuad' } });
    });
  }

  function minimapBounds() {
    const positions = _network ? _network.getPositions() : {};
    const pts = Object.values(positions);
    if (!pts.length) return {};
    const pad = 60;
    return {
      minX: Math.min(...pts.map(p => p.x)) - pad,
      maxX: Math.max(...pts.map(p => p.x)) + pad + 160,
      minY: Math.min(...pts.map(p => p.y)) - pad,
      maxY: Math.max(...pts.map(p => p.y)) + pad + 38,
    };
  }

  function renderMinimap() {
    if (!_minimapCanvas || !_network) return;
    const mW = 130, mH = 90;
    const mctx = _minimapCanvas.getContext('2d');
    mctx.clearRect(0, 0, mW, mH);

    const bounds = minimapBounds();
    if (!bounds.minX && bounds.minX !== 0) return;
    const { minX, maxX, minY, maxY } = bounds;
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;

    const toMX = gx => ((gx - minX) / rangeX) * mW;
    const toMY = gy => ((gy - minY) / rangeY) * mH;

    // Draw nodes as small colour dots
    if (_visNodes) {
      _visNodes.forEach(visNode => {
        const pos = _network.getPosition(visNode.id);
        if (!pos) return;
        const raw = visNode._raw;
        const colors = TYPE_COLORS[(raw && raw.label)] || COLOR_DEFAULT;
        mctx.fillStyle = colors.border;
        mctx.beginPath();
        mctx.roundRect(toMX(pos.x), toMY(pos.y), 8, 5, 2);
        mctx.fill();
      });
    }

    // Draw viewport rectangle
    const vp = _network.getBoundingBox();
    mctx.strokeStyle = 'rgba(255,255,255,0.4)';
    mctx.lineWidth = 1;
    mctx.strokeRect(
      toMX(vp.left), toMY(vp.top),
      toMX(vp.right) - toMX(vp.left),
      toMY(vp.bottom) - toMY(vp.top)
    );
  }
```

- [ ] **Step 3: Hook minimap into `afterDrawing`** — in `bootstrap()`, after `_network` is created:

```js
    _network.on('afterDrawing', renderMinimap);
```

- [ ] **Step 4: Call `initMinimap()` in `onReady()`** — add after `bootstrap()`:

```js
    initMinimap();
```

- [ ] **Step 5: Verify minimap renders** — open the UI with nodes, confirm minimap shows coloured dots and a viewport rect that moves when you pan.

- [ ] **Step 6: Commit**

```bash
git add static/canvas.js static/index.html
git commit -m "feat: minimap overlay with viewport rect and click-to-navigate"
```

---

### Task 8: Node Search

**Files:**
- Modify: `static/index.html`, `static/canvas.js`

- [ ] **Step 1: Add `highlightSearch()` and `clearSearch()` to `canvas.js`** — insert before `onReady()`:

```js
  function highlightSearch(query) {
    if (!_visNodes || !_network) return;
    if (!query) {
      clearSearch();
      return;
    }
    const q = query.toLowerCase();
    const updates = [];
    _visNodes.forEach(visNode => {
      const raw = visNode._raw || {};
      const match = (raw.name || '').toLowerCase().includes(q)
                 || (raw.id  || '').toLowerCase().includes(q);
      updates.push({ id: visNode.id, opacity: match ? 1.0 : 0.12 });
    });
    _visNodes.update(updates);
  }

  function clearSearch() {
    if (!_visNodes) return;
    const updates = [];
    _visNodes.forEach(v => updates.push({ id: v.id, opacity: 1.0 }));
    _visNodes.update(updates);
  }

  // Expose to index.html
  window.CortexGraph = window.CortexGraph || {};
  Object.assign(window.CortexGraph, { highlightSearch, clearSearch });
```

> Note: the `window.CortexGraph` assignment at the bottom of `onReady()` already exports `render`, `addNode`, `fitAll` — append `highlightSearch` and `clearSearch` there too.

Actually, update the `onReady()` export line to:

```js
    window.CortexGraph = { render, addNode, fitAll, highlightSearch, clearSearch };
```

- [ ] **Step 2: Add `onSearchInput()` JS in `index.html`** — add to `<script>` block:

```js
function onSearchInput(q) {
  // Highlight on canvas
  if (window.CortexGraph) {
    if (q) window.CortexGraph.highlightSearch(q);
    else   window.CortexGraph.clearSearch();
  }

  // Populate result list
  const ul = document.getElementById('search-results');
  ul.innerHTML = '';
  if (!q) return;
  const matches = _nodes.filter(n =>
    (n.name || '').toLowerCase().includes(q.toLowerCase()) ||
    (n.id   || '').toLowerCase().includes(q.toLowerCase())
  ).slice(0, 20);

  matches.forEach(n => {
    const li = document.createElement('li');
    li.textContent = (n.name || n.id);
    li.title = n.id;
    li.addEventListener('click', () => {
      if (window._cortexNetwork) {
        window._cortexNetwork.focus(n.id, {
          scale: 1.4, animation: { duration: 400, easingFunction: 'easeInOutQuad' }
        });
        window._cortexNetwork.selectNodes([n.id]);
        onNodeClick(n.id);
      }
    });
    ul.appendChild(li);
  });
}
```

- [ ] **Step 3: Verify search** — switch to Search panel in the dock, type a node name, confirm non-matching nodes fade, matching nodes stay bright, result list appears.

- [ ] **Step 4: Commit**

```bash
git add static/canvas.js static/index.html
git commit -m "feat: node search with canvas fade and result list"
```

---

### Task 9: Edge Type Filter

**Files:**
- Modify: `static/index.html`, `static/canvas.js`

- [ ] **Step 1: Add `filterEdgesByLabel()` to `canvas.js`** — insert before `onReady()`:

```js
  function filterEdgesByLabel(hiddenLabels) {
    if (!_visEdges) return;
    const updates = [];
    _visEdges.forEach(e => {
      updates.push({ id: e.id, hidden: hiddenLabels.has(e.label) });
    });
    _visEdges.update(updates);
  }

  Object.assign(window.CortexGraph || {}, { filterEdgesByLabel });
```

Again, also add `filterEdgesByLabel` to the `window.CortexGraph` assignment in `onReady()`:

```js
    window.CortexGraph = { render, addNode, fitAll, highlightSearch, clearSearch, filterEdgesByLabel };
```

- [ ] **Step 2: Add `buildFilterToggles()` and filter state to `index.html`** — add to `<script>` block:

```js
let _hiddenEdgeLabels = new Set();

function buildFilterToggles() {
  const container = document.getElementById('filter-toggles');
  if (!container) return;

  // Collect unique edge labels from current graph
  const labels = [...new Set(_edges.map(e => e.rel).filter(Boolean))].sort();
  container.innerHTML = '';

  labels.forEach(label => {
    const pill = document.createElement('button');
    pill.className = 'filter-pill' + (_hiddenEdgeLabels.has(label) ? '' : ' active');
    pill.textContent = label;
    pill.addEventListener('click', () => {
      if (_hiddenEdgeLabels.has(label)) {
        _hiddenEdgeLabels.delete(label);
        pill.classList.add('active');
      } else {
        _hiddenEdgeLabels.add(label);
        pill.classList.remove('active');
      }
      if (window.CortexGraph) window.CortexGraph.filterEdgesByLabel(_hiddenEdgeLabels);
    });
    container.appendChild(pill);
  });
}
```

- [ ] **Step 3: Rebuild filter toggles on graph load** — in `handleWSMessage` and `loadGraph`, after graph data is set, add:

```js
  // Rebuild filter panel if it's active
  if (_activePanel === 'filter') buildFilterToggles();
```

Add this at the end of the `if (msg.event === 'init')` block and after `_nodes` / `_edges` are set in `loadGraph()`.

Actually since `_activePanel` was removed in Task 3, track it differently. Re-add this state: `let _activePanel = 'timeline';` and set it in `setActivePanel`. Then `buildFilterToggles()` is called each time the filter panel is opened (already done in the `setActivePanel` rewrite in Task 3 Step 5).

- [ ] **Step 4: Verify edge filter** — switch to Filter panel, confirm toggle pills appear per edge type, toggling one hides those edges on canvas.

- [ ] **Step 5: Commit**

```bash
git add static/canvas.js static/index.html
git commit -m "feat: edge type filter panel with per-label toggle pills"
```

---

### Task 10: Inspector — SystemDesign enhanced fields + legend update

**Files:**
- Modify: `static/index.html`, `static/canvas.js`

- [ ] **Step 1: Update `onNodeClick()` to show section/rationale/status for SystemDesign nodes** — replace the `onNodeClick` function in `index.html`:

```js
function onNodeClick(nodeId) {
  _selectedNodeId = nodeId;
  const node = _nodes.find(n => n.id === nodeId);
  if (!node) return;

  const connectedEdges = _edges.filter(e => e.src === nodeId || e.dst === nodeId);
  const isDesign = node.label === 'SystemDesign';

  const statusColor = { 'done': '#059669', 'in-progress': '#ea580c', 'planned': '#6b7280' };
  const sc = statusColor[node.status] || '#6b7280';

  const container = document.getElementById('inspector-content');
  container.innerHTML = `
    <div class="inspector-field">
      <div class="inspector-label">Type</div>
      <div class="inspector-value"><span class="inspector-badge">${node.label || '?'}</span></div>
    </div>
    ${isDesign && node.section ? `
    <div class="inspector-field">
      <div class="inspector-label">Section</div>
      <div class="inspector-value" style="color:#a78bfa;font-weight:600">${node.section}</div>
    </div>` : ''}
    <div class="inspector-field">
      <div class="inspector-label">Name</div>
      <div class="inspector-value">${node.name || '—'}</div>
    </div>
    ${node.status ? `
    <div class="inspector-field">
      <div class="inspector-label">Status</div>
      <div class="inspector-value">
        <span style="display:inline-block;padding:1px 8px;border-radius:10px;
          font-size:11px;font-weight:600;background:${sc};color:#fff">${node.status}</span>
      </div>
    </div>` : ''}
    <div class="inspector-field">
      <div class="inspector-label">Description</div>
      <div class="inspector-value">${node.description || '—'}</div>
    </div>
    ${isDesign && node.rationale ? `
    <div class="inspector-field">
      <div class="inspector-label">Rationale</div>
      <div class="inspector-value" style="font-style:italic;font-size:11px">${node.rationale}</div>
    </div>` : ''}
    ${node.file_path ? `<div class="inspector-field"><div class="inspector-label">Path</div>
      <div class="inspector-value" style="font-family:monospace;font-size:11px">${node.file_path}</div></div>` : ''}
    <div class="inspector-field">
      <div class="inspector-label">ID</div>
      <div class="inspector-value" style="font-family:monospace;font-size:10px;color:var(--text-muted)">${node.id}</div>
    </div>
    <div class="inspector-field">
      <div class="inspector-label">Connections (${connectedEdges.length})</div>
      <ul class="inspector-connections">
        ${connectedEdges.map(e =>
          `<li>${e.src === nodeId ? '&rarr;' : '&larr;'} [${e.rel}] ${e.src === nodeId ? e.dst : e.src}</li>`
        ).join('') || '<li style="color:var(--text-muted)">No connections</li>'}
      </ul>
    </div>
  `;

  // Switch to timeline panel area to show inspector (it's always below timeline)
  // Inspector panel is always visible — just scroll to it if needed
}
```

- [ ] **Step 2: Update `buildTooltip()` in `canvas.js`** — add `section` and `rationale` rows:

In `buildTooltip()`, after the `status` row, add:

```js
      ${node.section   ? `<div class="tt-row"><span class="tt-label">Section</span><span class="tt-value" style="color:#a78bfa">${esc(node.section)}</span></div>` : ''}
      ${node.rationale ? `<div class="tt-row"><span class="tt-label">Why</span><span class="tt-value" style="font-style:italic">${esc(truncate(node.rationale, 80))}</span></div>` : ''}
```

- [ ] **Step 3: Update legend in `buildLegend()`** — add new rel types to the legend or replace the static legend with a dynamic one. Replace `buildLegend()` body:

```js
  function buildLegend() {
    const legend = document.createElement('div');
    legend.id = 'canvas-legend';
    legend.style.cssText = `
      position: absolute; bottom: 36px; right: 150px;
      background: rgba(30,30,30,0.88); border: 1px solid #3c3c3c;
      border-radius: 6px; padding: 10px 14px; z-index: 10;
      font-size: 11px; color: #ccc; line-height: 1.8;
      pointer-events: none;
    `;

    const typeEntries = Object.entries(TYPE_COLORS).map(([label, c]) =>
      `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${c.border};margin-right:5px;vertical-align:middle"></span>${label}`
    );
    const diffEntries = [
      `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${DIFF_ADDED.background};border:1.5px solid ${DIFF_ADDED.border};margin-right:5px;vertical-align:middle"></span>Added`,
      `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${DIFF_DELETED.background};border:1.5px solid ${DIFF_DELETED.border};margin-right:5px;vertical-align:middle"></span>Deleted`,
      `<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${DIFF_MODIFIED.background};border:1.5px solid ${DIFF_MODIFIED.border};margin-right:5px;vertical-align:middle"></span>Modified`,
    ];

    legend.innerHTML = [
      ...typeEntries,
      '<hr style="border-color:#3c3c3c;margin:4px 0">',
      ...diffEntries,
    ].map(e => `<div>${e}</div>`).join('');
    return legend;
  }
```

(Moved legend left of minimap by setting `right: 150px`.)

- [ ] **Step 4: Final smoke test**

Start the server. Open http://localhost:8000. Verify:
- Nodes render as coloured pills with icons
- Click a node → inspector shows section/status/rationale for SystemDesign nodes
- Legend shows coloured circles (not squares) per type
- Minimap is visible bottom-right
- Legend is to the left of minimap
- Export button in header opens dropdown
- Search dock icon → search panel appears, typing fades non-matching nodes
- Filter dock icon → filter panel shows edge type pills

- [ ] **Step 5: Commit**

```bash
git add static/canvas.js static/index.html
git commit -m "feat: enhanced SystemDesign inspector, updated legend, tooltip rationale field"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Pill nodes with icon circle | Task 5 |
| Remove canvas-placeholder | Tasks 3, 5 |
| Remove broken Search stub | Task 3 |
| Remove Inspector dock button | Task 3 |
| Remove `setActivePanel` dead logic | Task 3 |
| Node Search | Tasks 8 |
| Edge Type Filter | Task 9 |
| Minimap | Task 7 |
| Export PNG/JSON/Triples | Task 4 |
| SystemDesign `section` + `rationale` columns | Task 1 |
| New rel tables (IMPLEMENTS, PART_OF, USES, STORES_IN, RUNS_ON) | Task 1 |
| Updated `write_system_design_node` | Task 2 |
| New `list_design_sections` tool | Task 2 |
| Section group background regions on canvas | Task 6 |
| Inspector shows section/rationale/status | Task 10 |
| Tooltip shows section/rationale | Task 10 |

**Type consistency:**
- `filterEdgesByLabel` accepts a `Set<string>` — consistently used in Task 9 and canvas.js
- `highlightSearch(query: string)` / `clearSearch()` — consistent across Tasks 8 references
- `window.CortexGraph` export updated in Task 5 Step 7 and Task 8 Step 1 — final export in `onReady()` must include all: `{ render, addNode, fitAll, highlightSearch, clearSearch, filterEdgesByLabel }`
- `_activePanel` removed in Task 3 Step 7 but re-needed in Task 9 Step 3 — re-add `let _activePanel = 'timeline';` as noted in Task 9 Step 3

**Placeholder scan:** None found. All steps have explicit code.
