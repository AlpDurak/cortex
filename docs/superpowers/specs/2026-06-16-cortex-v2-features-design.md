# Cortex v2 — Feature Expansion Design

**Date:** 2026-06-16
**Status:** Approved
**Scope:** 20 features across 5 phases — schema/data, analysis engine, canvas rewrite, export/integrations, CLI/hooks

---

## Feature Naming Reference

All features use Cortex-specific names. No external tool terminology.

| Feature | Cortex Name |
|---|---|
| Auto-detected node clusters (Leiden) | **Signal Clusters** |
| Manual hyperedge containers | **Groups** |
| Most-connected nodes | **Keystones** |
| Unexpected cross-section edges | **Latent Bridges** |
| Generated markdown project summary | **Cortex Brief** |
| Health + coverage panel | **Vitals** |
| Coverage percentage metric | **Depth Score** |
| Undocumented node list | **Blind Spots** |
| Relevance-ranked graph search | **Pulse Search** |
| LLM feature cost tracker | **Ledger** |
| Per-session MCP tool log | **Session Trail** |
| Git-commit-linked snapshots | **Anchored Commits** |
| Auto-merge graph on git conflict | **Graph Reconciler** |
| Push to Neo4j / FalkorDB | **Graph Relay** |
| SVG / GraphML / Obsidian / wiki export | **Graph Export** |
| Interactive multi-platform installer | **Cortex Connect** |
| File + line number on nodes/edges | **Source Pins** |
| planned→in-progress→done statuses | **Decision Arc** (proposed → building → shipped) |
| Canvas library (vis-network → Cytoscape.js) | Canvas migration |
| Vitals coverage + debt list | Depth Score + Blind Spots |

---

## Architecture Overview

Five independent phases, each building on the previous. No phase introduces UI debt from an unstable API layer below it.

```
Phase 1 — Schema & Data Layer       core/db.py, core/graph_api.py
Phase 2 — Analysis Engine           core/analysis.py  (new)
Phase 3 — Canvas Rewrite + UI       static/canvas.js, static/panels/*  (new)
Phase 4 — Export & Integrations     core/export.py, core/relay.py, core/reconciler.py  (new)
Phase 5 — CLI & Hooks               cortex/main.py extensions
```

---

## File Structure

### Cleanup (before Phase 1 starts)

**Delete:**
- `requirements.txt` — redundant with `pyproject.toml`
- `TODO.md` — superseded by `docs/superpowers/plans/`
- `project.md` — original architecture spec, superseded by this document
- `cortex.json` — stale MCP manifest using `python -m` (wrong command)

**Move:**
- `core/schema_test.py` → `tests/test_schema.py`
- `core/graph_api_test.py` → `tests/test_graph_api.py`
- `cortex/mcp_server_test.py` → `tests/test_mcp_server.py`
- `core/seed_demo.py` → `tests/seed_demo.py`

### Target Layout

```
cortex/
├── core/
│   ├── __init__.py
│   ├── db.py              # DatabaseManager, schema, snapshots
│   ├── graph_api.py       # neighborhood, path, diff
│   ├── analysis.py        # Signal Clusters, Keystones, Latent Bridges, Pulse Search, Ledger
│   ├── export.py          # Graph Export (SVG, GraphML, Obsidian vault, wiki)
│   ├── relay.py           # Graph Relay (Neo4j / FalkorDB)
│   ├── reconciler.py      # Graph Reconciler (git merge driver)
│   └── project_info.py    # project name + favicon detection
├── cortex/
│   ├── __init__.py
│   ├── main.py            # CLI: init / run / mcp / hook / export / relay / connect
│   ├── web_server.py      # FastAPI app + REST + WebSocket
│   └── mcp_server.py      # MCP tools
├── static/
│   ├── index.html
│   ├── canvas.js          # Cytoscape.js canvas (replaces vis-network)
│   └── panels/
│       ├── vitals.js      # Vitals panel (Depth Score + Blind Spots)
│       ├── inspector.js   # Node inspector
│       ├── timeline.js    # Chronicle timeline panel
│       └── search.js      # Pulse Search panel
├── tests/
│   ├── test_schema.py
│   ├── test_graph_api.py
│   ├── test_mcp_server.py
│   ├── test_analysis.py
│   └── seed_demo.py
├── docs/superpowers/specs/
├── docs/superpowers/plans/
├── pyproject.toml
├── CLAUDE.md
├── AGENTS.md
├── SKILL.md
├── README.md
├── LICENSE
├── install.sh
└── install.ps1
```

---

## Phase 1 — Schema & Data Layer

**Files changed:** `core/db.py`, `core/graph_api.py`, `cortex/mcp_server.py`

### Source Pins

Every node table gains two nullable columns: `source_file STRING` and `source_line INT64`. Added via `ALTER TABLE … ADD … DEFAULT ''` / `DEFAULT 0` migrations in `_migrate_schema()` — same pattern already used for `section` and `rationale`. All existing nodes keep working with empty values.

`write_system_design_node` gains two optional parameters: `source_file` and `source_line`. The inspector panel (Phase 3) displays these as a clickable path badge.

Applies to all five node types: File, SystemDesign, Service, Database, Infrastructure.

### Decision Arc

Replaces the free-text `status` field on `SystemDesign` nodes with an enforced three-value vocabulary:

| Old value | New value |
|---|---|
| `planned` | `proposed` |
| `in-progress` | `building` |
| `done` | `shipped` |

A one-time data migration in `_migrate_schema()` updates all existing rows. `write_system_design_node` validates the value and raises a descriptive error if anything outside `{proposed, building, shipped}` is passed.

The inspector and Vitals panel display these with distinct colour badges: proposed=blue, building=amber, shipped=green.

### Groups

New Kùzu node table:
```
CREATE NODE TABLE IF NOT EXISTS Group(
    id STRING,
    name STRING,
    description STRING,
    section STRING,
    PRIMARY KEY (id)
)
```

New rel table connecting any node type to a Group:
```
CREATE REL TABLE IF NOT EXISTS MEMBER_OF(
    FROM File TO Group,
    FROM SystemDesign TO Group,
    FROM Service TO Group,
    FROM Database TO Group,
    FROM Infrastructure TO Group
)
```

New MCP tool `write_group_node(id, name, description, member_ids, section)`:
- Creates or updates the Group node
- Creates `MEMBER_OF` edges from each `member_id` to the group
- Returns a summary of created edges and any missing member IDs
- Auto-snapshots after write (same pattern as `write_system_design_node`)

Groups appear in `GET /api/graph` as regular nodes with `label: "Group"`. The web server transforms `MEMBER_OF` edges into `parent: groupId` on each member node in the graph response — Cytoscape.js requires the parent reference on the child, not a separate edge, to render compound nodes. Raw `MEMBER_OF` edges are still included in the response for the inspector panel to display group membership.

`NODE_TABLES` in `graph_api.py` is extended to include `"Group"`. `REL_TABLES` gains `"MEMBER_OF"`.

### Session Trail

Append-only JSON Lines file at `.cortex/trail.jsonl`. One entry per MCP tool call:

```json
{"ts": "2026-06-16T14:32:00Z", "session_id": "uuid4", "tool": "write_system_design_node", "args_summary": "id=SystemDesign:Auth:OAuth", "node_id": "SystemDesign:Auth:OAuth"}
```

- `session_id` is a UUID4 generated at MCP server startup, held in module-level state
- Written synchronously after every tool call completes
- Never snapshotted — it is a log, not graph state
- New MCP tool `get_session_trail(limit=50)` returns last N entries as formatted text
- REST endpoint `GET /api/trail?limit=50` returns JSON array

### Anchored Commits Reminder

`cortex init` checks `<project_root>/.git/hooks/post-commit` after DB initialisation. If absent:
```
  → Run 'cortex hook install' to sync graph snapshots with every git commit.
```

MCP server tracks a module-level `_hook_reminder_sent = False`. On the first tool call of any session, if `.git/hooks/post-commit` does not exist, the reminder text is prepended to the tool's response and `_hook_reminder_sent` is set to `True`.

---

## Phase 2 — Analysis Engine

**New file:** `core/analysis.py`
**Files changed:** `cortex/mcp_server.py` (new tools), `cortex/web_server.py` (new endpoints)

All functions accept a `kuzu.Connection` and return plain Python dicts. No UI dependencies.

### Signal Clusters

```python
def detect_signal_clusters(conn, project_root, resolution=1.0) -> dict
```

1. Fetches all nodes and edges from the live DB
2. Builds an undirected `igraph.Graph` (packages: `leidenalg`, `igraph`)
3. Runs `leidenalg.find_partition(graph, leidenalg.ModularityVertexPartition, resolution_parameter=resolution)`
4. Assigns each node a `cluster_id` (int) and `cluster_color` (hex, from a fixed 12-colour palette)
5. Writes result to `.cortex/clusters.json` with a `computed_at` unix timestamp
6. Cache invalidation: `GET /api/clusters` reads the latest `unix_ts` from `versions.json` and recomputes if `clusters.json` is older — no import dependency on `db.py` from `analysis.py`

Returns: `{clusters: [{id, label, name, cluster_id, cluster_color}], cluster_count, resolution}`

Signal Clusters and Groups coexist: clusters are topology-derived colourings, Groups are authored containers. A node can belong to both.

MCP tool: `detect_signal_clusters(resolution=1.0)`
REST endpoint: `GET /api/clusters` (reads cache if fresh, recomputes if stale)

### Keystones

```python
def get_keystones(conn, top_n=10) -> list[dict]
```

Counts total edge degree (in + out) per node across all rel tables. Excludes Group nodes. Returns top N sorted by degree descending.

Returns: `[{id, label, name, degree, section}]`

MCP tool: `get_keystones(top_n=10)`
REST endpoint: `GET /api/keystones?top_n=10`

### Latent Bridges

```python
def get_latent_bridges(conn, top_n=20) -> list[dict]
```

Finds edges where `src.section != dst.section` and both sections are non-empty. Computes a surprise score: edges between section pairs with fewer total cross-connections score higher. Returns top N by surprise score.

Returns: `[{src_id, rel, dst_id, src_section, dst_section, surprise_score}]`

MCP tool: `get_latent_bridges(top_n=20)`
REST endpoint: `GET /api/latent-bridges?top_n=20`

### Pulse Search

```python
def pulse_search(conn, query, top_n=20) -> list[dict]
```

Builds a TF-IDF index over `name + description + rationale` for all nodes at query time (no persistent index — graph is small enough for in-memory scoring). Returns nodes ranked by cosine similarity to the query string.

Returns: `[{id, label, name, score, section}]`

REST endpoint: `GET /api/search?q=<query>&top_n=20`
(Not exposed as MCP tool — used by the Pulse Search UI panel only.)

### Ledger

Infrastructure only in Phase 2. No LLM calls yet.

```python
def ledger_write(project_root, feature, model, input_tokens, output_tokens, cost_usd) -> None
```

Appends one JSON line to `.cortex/ledger.jsonl`:
```json
{"ts": "2026-06-16T14:32:00Z", "feature": "cluster_labeling", "model": "claude-sonnet-4-6", "input_tokens": 800, "output_tokens": 120, "cost_usd": 0.0024}
```

REST endpoint: `GET /api/ledger` returns full log as JSON array.

### Cortex Brief

```python
def generate_brief(conn, project_root) -> str
```

Assembles a markdown document from live analysis results — no LLM call:
- Project name + node/edge counts
- Top 5 Keystones with degree
- Top 5 Latent Bridges
- Signal Cluster summary (count + sizes)
- Decision Arc breakdown (proposed/building/shipped counts)
- Blind Spots count
- 3–5 suggested questions derived from graph structure

Written to `.cortex/BRIEF.md` and served at `GET /api/brief`. Regenerated on every call (fast — pure computation).

---

## Phase 3 — Canvas Rewrite + UI

**Files changed:** `static/index.html`, `static/canvas.js` (full rewrite)
**New files:** `static/panels/vitals.js`, `static/panels/inspector.js`, `static/panels/timeline.js`, `static/panels/search.js`

### Canvas Migration (vis-network → Cytoscape.js)

vis-network CDN link removed. Cytoscape.js loaded from CDN:
```html
<script src="https://unpkg.com/cytoscape@3.x/dist/cytoscape.min.js"></script>
<script src="https://unpkg.com/cytoscape-cose-bilkent@4.x/cytoscape-cose-bilkent.js"></script>
```

`cose-bilkent` layout is used — it correctly handles compound nodes (Groups). Fallback to `cose` if Groups are absent.

Node type colours preserved exactly:
- File → `#2563eb` (blue)
- SystemDesign → `#7c3aed` (purple)
- Service → `#d97706` (amber)
- Database → `#16a34a` (green)
- Infrastructure → `#6b7280` (gray)
- Group → transparent fill, coloured border by section

All existing interactions preserved: click → inspector, double-click → fit, zoom/pan, diff overlay colours (green/red/orange for added/deleted/modified).

### Groups as Compound Nodes

Group nodes are registered as Cytoscape parent nodes. Member nodes set `parent: groupId` in their data. Cytoscape renders the Group as a rectangle that physically contains its members.

Group node style:
- Border: 2px solid, colour derived from section (same palette as Signal Cluster colours)
- Fill: semi-transparent section colour at 8% opacity
- Label: top-left corner, `name · section` in small caps
- Collapsed state: single rounded-rectangle node showing `▶ name (N members)`

Collapse/expand: click the Group header toggles `cy.nodes('#groupId').toggleClass('collapsed')`. Collapsed style hides children and shows a summary node.

### Signal Cluster Colouring

When `/api/clusters` returns data, each node gains an additional border ring coloured by `cluster_color`. Implemented as a Cytoscape style overlay (`border-color`, `border-width: 4px`) separate from the Group border. Cluster legend appears in bottom-right alongside the type legend.

### Diff Overlay

Ported directly. On timeline snapshot selection, nodes and edges receive `added`/`deleted`/`modified` Cytoscape classes. Styles:
- `added`: green fill tint + green border
- `deleted`: red fill tint + red dashed border
- `modified`: amber fill tint + amber border

### Chronicle Panel (`static/panels/timeline.js`)

Extracted from `index.html` into its own module. Extended:
- Snapshot entries show git commit message if `git_sha` is present in the versions entry
- `git_sha` displayed as a short monospace badge (7 chars), clicking copies full SHA to clipboard
- `BRIEF` button on each entry: fetches `GET /api/brief` for that snapshot slot (brief is regenerated against the snapshot conn) and displays in a modal

### Vitals Panel (`static/panels/vitals.js`)

New icon in the left dock (pulse/heartbeat icon). Panel content:

**Depth Score** — single large percentage: `(nodes with non-empty description AND non-empty rationale) / total nodes × 100`. Colour: green ≥ 80%, amber 50–79%, red < 50%.

**Decision Arc** — three count badges: proposed (blue) / building (amber) / shipped (green). Small horizontal bar showing proportions.

**Blind Spots** — scrollable list of nodes missing description or rationale. Each entry shows `[type] id — missing: description, rationale`. Clicking focuses the canvas on that node.

**Keystones** — top 5 nodes by degree. Each shows name + degree count. Clicking focuses the canvas.

**Latent Bridges** — top 5 cross-section edges. Each shows `src.section → dst.section via rel`. Clicking highlights both nodes and the edge.

All five sections are always visible (no tabs). The panel scrolls vertically.

### Pulse Search Panel (`static/panels/search.js`)

Replaces the existing text filter. Input box → 300ms debounce → `GET /api/search?q=<query>` → results list ranked by TF-IDF score. Each result shows `[type] name — section`. Clicking focuses and highlights the node on canvas. Escape clears search and removes highlights.

### Inspector Panel (`static/panels/inspector.js`)

Extracted from `index.html`. Extended fields:
- **Source Pins**: `source_file:source_line` shown as monospace badge. Clicking copies path to clipboard.
- **Decision Arc status**: colour-coded badge (proposed/building/shipped)
- **Cluster**: cluster ID + colour swatch if Signal Clusters have been run
- **Groups**: list of Group names this node belongs to (via `MEMBER_OF` edges)

---

## Phase 4 — Export & Integrations

**New files:** `core/export.py`, `core/relay.py`, `core/reconciler.py`
**Files changed:** `cortex/main.py`, `install.sh`, `install.ps1`

### Graph Export (`core/export.py`)

Four format functions, all `(conn: kuzu.Connection, output_path: Path) -> Path`:

**`export_svg(conn, path)`**
Uses `matplotlib` + `networkx`. Nodes plotted as circles coloured by type. Edges as arrows labelled with rel type. Saved as `.svg`. Optional dep: `pip install cortex[svg]`.

**`export_graphml(conn, path)`**
Serialises all nodes and edges to GraphML XML. Node attributes: id, label, name, description, section, status. Edge attributes: rel type. No extra deps.

**`export_obsidian(conn, path)`**
Creates a directory at `path/`:
- One `.md` per node: frontmatter (type, section, status, source_file), body with description + rationale, wikilinks to connected nodes
- `.obsidian/graph.json` with node type → colour mapping

**`export_wiki(conn, path)`**
Creates a directory at `path/`:
- `index.md`: table of all Signal Clusters with node counts and top Keystones per cluster
- One `cluster-N.md` per Signal Cluster: all nodes in that cluster with their descriptions
- Fallback if `clusters.json` does not exist: groups by `section` instead of cluster, one file per section.

CLI: `cortex export <svg|graphml|obsidian|wiki> [--out <dir>] [--root <dir>]`
REST: `POST /api/export {"format": "svg", "out": "relative/path"}`

### Graph Relay (`core/relay.py`)

**`relay_neo4j(conn, bolt_url, user, password, also_write_cypher=True)`**
Generates `MERGE` Cypher for all nodes and rels. Executes against Neo4j via the `neo4j` driver. Also writes `cypher.txt` to `.cortex/relay-neo4j.cypher` for manual import. Optional dep: `pip install cortex[neo4j]`.

**`relay_falkordb(conn, redis_url, also_write_cypher=True)`**
Same pattern via FalkorDB's Redis-compatible Cypher endpoint. Optional dep: `pip install cortex[falkordb]`.

CLI:
```
cortex relay neo4j bolt://localhost:7687 --user neo4j --password secret
cortex relay falkordb falkordb://localhost:6379
cortex relay neo4j --cypher-only   # just writes cypher.txt, no live push
```

### Graph Reconciler (`core/reconciler.py`)

Git merge driver for `.cortex/versions.json`.

`reconcile(base_path, ours_path, theirs_path, output_path)`:
1. Loads all three versions.json files
2. Merges `versions` arrays from ours and theirs
3. Deduplicates by `(slot, unix_ts)` — identical snapshots from both branches are kept once
4. Sorts by `unix_ts` ascending
5. Caps to `MAX_VERSIONS` (5), keeping most recent
6. Writes result to `output_path`

Registered by `cortex hook install` — see Phase 5.

### Cortex Connect Installer

`install.sh` and `install.ps1` both rewritten to present an interactive checkbox menu after venv setup.

**Bash (install.sh) — pure terminal UI:**
```
Select AI tools to configure (SPACE to toggle, ENTER to confirm):

  [x] Claude Code
  [x] Cursor
  [ ] Gemini CLI
  [ ] Codex
  [ ] Windsurf
  [ ] VS Code Copilot Chat
  [ ] Amp
  [ ] Kiro
  [ ] OpenCode
```

Implemented using `tput` / `stty` for raw input — no npm, no Python. Arrows move cursor, Space toggles, Enter confirms.

**PowerShell (install.ps1):**
Same UI using ANSI escape codes and `[Console]::ReadKey()` raw input. Works in Windows Terminal and PowerShell 5.1+.

**MCP config paths per platform:**
| Platform | Config path |
|---|---|
| Claude Code | `~/.claude/settings.json` |
| Cursor | `~/.cursor/mcp.json` |
| Gemini CLI | `~/.gemini/settings.json` |
| Codex | `~/.codex/config.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| VS Code Copilot Chat | `~/.vscode/mcp.json` |
| Amp | `~/.amp/mcp.json` |
| Kiro | `~/.kiro/settings/mcp.json` |
| OpenCode | `~/.config/opencode/config.json` |

All write the same entry: `{"command": "<venv>/bin/cortex", "args": ["mcp"]}`.

**`cortex connect` subcommand** — re-runs the checkbox menu post-install. Reads existing config to pre-tick already-configured platforms.

---

## Phase 5 — CLI & Hooks

**Files changed:** `cortex/main.py`, `cortex/mcp_server.py`
**New test file:** `tests/test_analysis.py`
**Test files moved:** `tests/test_schema.py`, `tests/test_graph_api.py`, `tests/test_mcp_server.py`, `tests/seed_demo.py`

### `cortex hook` Subcommand

**`cortex hook install`** (run inside a project with a `.git/` directory):
1. Writes `.git/hooks/post-commit`:
   ```bash
   #!/bin/sh
   MSG=$(git log -1 --pretty=%s)
   SHA=$(git rev-parse HEAD)
   cortex snapshot --message "$MSG" --sha "$SHA" --root "$(git rev-parse --show-toplevel)"
   ```
2. `chmod +x .git/hooks/post-commit`
3. Appends to `.git/config`:
   ```
   [merge "cortex-reconciler"]
       name = Cortex graph reconciler
       driver = cortex reconcile %O %A %B
   ```
   (`%O` = base, `%A` = ours and output file, `%B` = theirs — standard git merge driver convention)
4. Creates/updates `.gitattributes`:
   ```
   .cortex/versions.json merge=cortex-reconciler
   ```
5. Prints confirmation summary

**`cortex hook uninstall`**: removes the post-commit hook file, removes the `[merge "cortex-reconciler"]` section from `.git/config`, removes the `.gitattributes` line.

**`cortex hook status`**: prints hook presence, last trigger timestamp (from Session Trail), merge driver registration status.

**`cortex snapshot` internal subcommand**: called only by the post-commit hook. Starts the DatabaseManager, calls `commit_snapshot(message, git_sha=sha)`, exits. Not advertised in `cortex --help`.

`commit_snapshot()` in `core/db.py` gains an optional `git_sha: str | None = None` parameter. When provided, the value is stored in the versions entry alongside `slot`, `timestamp`, `unix_ts`, and `message`.

### Anchored Commits — versions.json Extension

The `commit_snapshot()` return dict and stored entry gain an optional `git_sha` field:
```json
{
  "slot": 3,
  "timestamp": "2026-06-16T14:32:00Z",
  "unix_ts": 1750084320.0,
  "message": "Add OAuth flow",
  "git_sha": "a3f7c91d..."
}
```

`git_sha` is `None` when snapshots are taken manually (UI button or MCP tool).

### `pyproject.toml` Optional Extras

```toml
[project.optional-dependencies]
svg      = ["matplotlib", "networkx"]
neo4j    = ["neo4j>=5.0"]
falkordb = ["falkordb>=1.0"]
analysis = ["leidenalg>=0.10", "igraph>=0.11"]
```

### `tests/test_analysis.py`

Unit tests using an in-memory Kùzu DB seeded from `tests/seed_demo.py`:
- `test_keystones_empty_graph()` — returns empty list, no crash
- `test_keystones_returns_top_n()` — seeded graph, checks ordering
- `test_latent_bridges_same_section()` — no bridges when all nodes share a section
- `test_latent_bridges_cross_section()` — verifies surprise score ordering
- `test_pulse_search_ranks_by_relevance()` — query matches name field
- `test_signal_clusters_assigns_all_nodes()` — every node gets a cluster_id
- `test_ledger_write_and_read()` — writes entry, reads back via `GET /api/ledger`
- `test_brief_generates_markdown()` — non-empty string, contains expected sections

### Reminder Prompts

`cortex init` reminder (if hook absent):
```
  Graph database initialized at .cortex/

  → Run 'cortex hook install' to sync graph snapshots with every git commit.
```

MCP server first-tool reminder (once per session, if hook absent):
```
[Cortex] Run 'cortex hook install' in your project root to automatically
         snapshot the graph on every git commit.

<tool response follows>
```

---

## New REST Endpoints Summary

| Method | Path | Phase | Description |
|---|---|---|---|
| GET | `/api/trail` | 1 | Session Trail log |
| GET | `/api/clusters` | 2 | Signal Clusters (cached) |
| GET | `/api/keystones` | 2 | Keystones list |
| GET | `/api/latent-bridges` | 2 | Latent Bridges list |
| GET | `/api/search` | 2 | Pulse Search (TF-IDF) |
| GET | `/api/ledger` | 2 | Ledger cost log |
| GET | `/api/brief` | 2 | Cortex Brief markdown |
| POST | `/api/export` | 4 | Trigger Graph Export |

---

## New MCP Tools Summary

| Tool | Phase | Description |
|---|---|---|
| `write_group_node(id, name, description, member_ids, section)` | 1 | Create/update a Group and wire members |
| `get_session_trail(limit=50)` | 1 | Last N Session Trail entries |
| `detect_signal_clusters(resolution=1.0)` | 2 | Run Leiden clustering, return summary |
| `get_keystones(top_n=10)` | 2 | Most-connected nodes |
| `get_latent_bridges(top_n=20)` | 2 | Unexpected cross-section edges |
| `get_cortex_brief()` | 2 | Generate and return Cortex Brief markdown |

---

## Dependencies Added

| Package | Extra | Used by |
|---|---|---|
| `leidenalg>=0.10` | `analysis` | Signal Clusters |
| `igraph>=0.11` | `analysis` | Signal Clusters |
| `matplotlib` | `svg` | Graph Export SVG |
| `networkx` | `svg` | Graph Export SVG |
| `neo4j>=5.0` | `neo4j` | Graph Relay Neo4j |
| `falkordb>=1.0` | `falkordb` | Graph Relay FalkorDB |

Core install (`pip install cortex`) gains no new required dependencies.
