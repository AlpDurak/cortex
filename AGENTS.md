# Cortex — Agent Instructions

This project uses **Cortex**, a local knowledge graph MCP server that maps the
entire codebase into a queryable graph. The MCP server name is `cortex`.
All architecture queries go through it — never use grep, glob, or file search
to understand project structure.

---

## Step 0: Bootstrap the graph (run this on first use)

Call `list_design_sections` to check if the graph exists and has content.

If it returns empty or zero nodes:

1. Survey the project: read `package.json` / `pyproject.toml` / `go.mod`,
   scan the directory layout, read `README`, inspect config files.
2. Create nodes for **every** significant file, service, database,
   infrastructure component, and architectural decision you find.
   - File nodes: significant source files and directories
   - Service nodes: external APIs, internal microservices
   - Database nodes: databases, caches, queues, object stores
   - Infrastructure nodes: cloud resources, servers, CI systems
   - SystemDesign nodes: architectural decisions, patterns, integrations
3. Wire them together: set `connects_to` edges that reflect real dependencies
   (e.g. a File node IMPLEMENTS a SystemDesign node, a Service TALKS_TO another).
4. Call `commit_snapshot` once the initial graph is complete.
5. Call `write_agent_instructions`. This writes a Cortex usage section to
   `CLAUDE.md` and `AGENTS.md` in the project root so every future AI session
   knows to look in Cortex first. Safe to call even if those files already exist.

Document every little detail — the graph is the persistent memory of this project.

---

## Every session

1. Call `list_design_sections` before reading any files.
2. Use `explore_neighborhood(node_id)` and `find_structural_path(src, dst)`
   for all architecture questions.
3. Do **not** use grep, glob, or file read to understand project structure.
   File reads are only permitted for specific implementation details once
   the relevant node is already known from a graph query.

---

## Before every git commit

POST a snapshot so the graph timeline stays in sync with git history:

```
POST http://localhost:7842/api/commit
Content-Type: application/json
{"message": "describe what changed"}
```

Or call the `commit_snapshot` MCP tool directly if available.

The web server must be running (`cortex run`) for the HTTP endpoint to be reachable.

---

## New design decisions

Any new service integration, database, pattern, or architectural decision must
be recorded immediately:

```
write_system_design_node(
  id="SystemDesign:Section:Name",
  name="Human-readable name",
  section="Auth | Payments | Storage | ...",
  description="What this decision does",
  status="planned | in-progress | done",
  rationale="Why this approach was chosen",
  connects_to=[{"rel": "IMPLEMENTS", "target_id": "File:path/to/file.py"}]
)
```

---

## MCP tools reference

| Tool | When to use |
|---|---|
| `list_design_sections` | Session start, re-orientation |
| `explore_neighborhood(node_id, depth)` | Understand a node and its connections |
| `find_structural_path(src_id, dst_id)` | Trace dependency chains |
| `get_graph_timeline()` | See snapshot history |
| `query_graph_diff(from_version, to_version)` | What changed between snapshots |
| `write_system_design_node(...)` | Document architectural decisions |
