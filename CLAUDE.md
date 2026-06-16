# Cortex

This project uses the **Cortex** knowledge graph skill. Load it before starting work:

```
/skill cortex
```

Or invoke it explicitly: `Skill({ skill: "cortex" })`.

If the skill is not available, follow the rules in `AGENTS.md` directly.

---

## Fallback rules (when SKILL.md is not loaded)

See `AGENTS.md` — the same rules apply:

- Bootstrap the graph if empty (Step 0 in AGENTS.md)
- Call `list_design_sections` at session start
- Use MCP tools for architecture queries, not file search
- POST `/api/commit` before any `git commit`
- Record new design decisions with `write_system_design_node`
