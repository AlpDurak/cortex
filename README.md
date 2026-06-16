# Cortex

A local knowledge graph that keeps AI agents oriented in your codebase.

![Cortex UI showing pill nodes, minimap, and timeline panel](docs/images/cortex-ui.png)

Cortex maps your project into a queryable graph — files, services, databases,
infrastructure, and architectural decisions — and exposes it to AI agents via
MCP so they never need to grep or glob to understand your codebase. The web UI
lets you explore the graph and review what the AI documented over time.

---

## Quick Install

**macOS / Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/AlpDurak/cortex/master/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/AlpDurak/cortex/master/install.ps1 | iex
```

The installer clones Cortex into `./cortex/`, creates a Python venv, installs
dependencies, and auto-configures any of these AI tools it finds on your machine:

- Claude Code (`~/.claude/settings.json`)
- Cursor (`~/.cursor/mcp.json`)
- Gemini CLI (`~/.gemini/settings.json`)
- Codex CLI (`~/.codex/config.json`)

---

## Usage

**Start the web UI** (run from your project directory):

```bash
/path/to/cortex/.venv/bin/python -m cortex.web_server
# Windows:
# C:\path\to\cortex\.venv\Scripts\python.exe -m cortex.web_server
```

Open `http://localhost:7842` to explore the graph, browse snapshots, and
watch the AI update the knowledge graph in real time.

The MCP server starts automatically when your AI tool calls a Cortex tool.
The AI agent reads `AGENTS.md` (or `SKILL.md` for Claude Code) for usage rules.

---

## How the graph works

Cortex stores the graph in a `.cortex/` directory inside your project. It keeps
5 rolling snapshots so you can browse history and diff any two versions.

![Timeline panel with diff overlay showing added and modified nodes](docs/images/cortex-diff.png)

Use the Timeline panel in the web UI to navigate between snapshots. Click any
historical slot to mount it as an overlay — added nodes appear green, deleted
nodes appear red/dashed, modified nodes appear orange.

---

## Node inspector

Click any node to open the inspector panel. SystemDesign nodes show section,
status badge, and architectural rationale.

![Inspector panel showing a File node with type, description, path, and connections](docs/images/cortex-inspector.png)

---

## Node search

Use the Search panel (magnifying glass icon) to find nodes by name or ID.
Non-matching nodes fade to 12% opacity so matching nodes stand out.

![Search panel showing fade effect with matching nodes highlighted](docs/images/cortex-search.png)

---

## MCP tools reference

| Tool | Description | When to use |
|---|---|---|
| `list_design_sections` | All SystemDesign nodes grouped by section | Session start, re-orientation |
| `explore_neighborhood(node_id, depth)` | Node + its connections up to N hops | Understand a component |
| `find_structural_path(src_id, dst_id)` | Shortest path between two nodes | Trace dependencies |
| `get_graph_timeline()` | Snapshot history with timestamps | See what changed when |
| `query_graph_diff(from_version, to_version)` | Added/deleted/modified nodes and edges | Understand a change |
| `write_system_design_node(...)` | Create or update a SystemDesign node | Document architecture |

---

## Manual MCP configuration

If the installer didn't configure your tool, add this entry to your tool's MCP config:

```json
"cortex": {
  "command": "/absolute/path/to/cortex/.venv/bin/python",
  "args": ["-m", "cortex.mcp_server"]
}
```

Set `cwd` to your project directory (or `${workspaceFolder}` if your tool supports it).
The server resolves the project root from its working directory at startup.

---

## Requirements

- Python 3.11+
- git

---

## License

MIT
