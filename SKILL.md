---
name: cortex
description: Enforces Cortex knowledge graph usage — bootstrap graph, query via MCP, commit snapshots before git commits. Use at session start for any project with a .cortex/ directory.
---

# Cortex Knowledge Graph Skill

This is a **rigid** skill. Follow every step exactly — do not skip or adapt.

## When this skill applies

Any project that has a `.cortex/` directory or a configured `cortex` MCP server.
Invoke this skill at the start of every session in such a project.

---

## Checklist (create a TodoWrite task for each item below)

- [ ] Step 0: Bootstrap check — is the graph populated?
- [ ] Step 0a: write_agent_instructions — stamp CLAUDE.md / AGENTS.md in this project
- [ ] Step 1: Call list_design_sections
- [ ] Step 2: Use MCP for all architecture queries (no grep/glob/file-read)
- [ ] Step 3: Before git commit — call commit_snapshot
- [ ] Step 4: New design decisions — call write_system_design_node

---

## Step 0: Bootstrap the graph

**Run this first, every time.**

Call `list_design_sections`. If it returns zero nodes or an empty result:

The graph does not exist yet. You must populate it before doing anything else.

1. **Survey the project** — read `package.json`, `pyproject.toml`, `go.mod`,
   top-level directory listing, `README`, config files, CI definitions.

2. **Identify all nodes** across five types:
   - **File** — significant source files, entry points, config files
   - **Service** — external APIs, internal microservices, background workers
   - **Database** — databases, caches (Redis), queues (SQS), object stores (S3)
   - **Infrastructure** — cloud resources, servers, CI systems, CDNs
   - **SystemDesign** — architectural decisions, patterns, integrations, constraints

3. **Create every node** with full detail:
   - Use descriptive names and complete descriptions
   - Set `section` to group related design nodes (Auth, Payments, Storage, etc.)
   - Set `status` to `planned`, `in-progress`, or `done`
   - Set `rationale` to explain WHY this approach was chosen
   - Document every little detail — the graph is the persistent memory

4. **Wire edges** — set `connects_to` edges that reflect real dependencies:
   - `IMPLEMENTS` — a File implements a SystemDesign decision
   - `PART_OF` — a SystemDesign is part of a broader SystemDesign
   - `USES` — a SystemDesign uses a Service
   - `STORES_IN` — a SystemDesign stores data in a Database
   - `RUNS_ON` — a SystemDesign runs on Infrastructure
   - `MODIFIES` — a SystemDesign modifies a File
   - `TALKS_TO` — a SystemDesign or Service talks to a Service

5. **Commit the baseline** — call `commit_snapshot` with message `"Initial graph bootstrap"`.

6. **Stamp the project** — call `write_agent_instructions`. This writes a Cortex
   usage section to `CLAUDE.md` and `AGENTS.md` in the project root so every
   future AI session on this project knows to look in Cortex first. Safe to
   call even if those files already exist — it appends and never overwrites.

Only proceed to Step 1 after the graph has content.

---

## Step 1: Session start

Call `list_design_sections` to get a structural map of the project.

Read the output. Understand the sections before touching any code.

---

## Step 2: Architecture queries — MCP only

**Never** use grep, glob, ls, or file-read to understand project architecture.

Always use:
- `explore_neighborhood(node_id, depth=2)` — understand a node and its connections
- `find_structural_path(start_node_id, end_node_id)` — trace dependency chains
- `list_design_sections` — re-orient when lost
- `query_graph_diff(from_version, to_version)` — understand what changed

File reads are permitted **only** for reading specific implementation details
once the relevant node is already known from a graph query.

---

## Step 3: Before every git commit

Before running `git commit`, record a snapshot:

```
POST http://localhost:7842/api/commit
Content-Type: application/json
{"message": "your commit message"}
```

Or use the `commit_snapshot` MCP tool if it is available in your tool list.

The web server must be running (`cortex run`) for the HTTP endpoint to be reachable.

This keeps the graph timeline in sync with git history.

---

## Step 4: New design decisions

Any new architectural decision must be recorded:

```
write_system_design_node(
  id="SystemDesign:Section:DecisionName",
  name="Human-readable name",
  section="Auth",
  description="What this decision does and how",
  status="planned",
  rationale="Why this approach over alternatives",
  connects_to=[
    {"rel": "IMPLEMENTS", "target_id": "File:src/auth/oauth.py"},
    {"rel": "USES", "target_id": "Service:GoogleOAuth"}
  ]
)
```

Do this **before** writing the implementation code.

---

## Red flags

If you find yourself doing any of these, stop and use the MCP tools instead:

- Running `grep` to find where a function is defined → use `explore_neighborhood`
- Running `find` or `ls` to understand directory structure → use `list_design_sections`
- Reading multiple files to understand how components relate → use `find_structural_path`
- Committing without calling `/api/commit` → always snapshot first
