"""Shared helper for stamping Cortex usage rules into a project's agent files.

`cortex init` and the `write_agent_instructions` MCP tool both call
:func:`write_agent_instructions` so the on-disk instructions stay identical no
matter which entry point creates them.
"""

from __future__ import annotations

from pathlib import Path

# Heading used to detect an already-stamped file (keeps the operation idempotent).
CORTEX_MARKER = "## Cortex Knowledge Graph"

# The section appended to CLAUDE.md / AGENTS.md.
CORTEX_SECTION = """
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

AGENT_FILES = ("CLAUDE.md", "AGENTS.md")


def write_agent_instructions(project_root: Path) -> dict[str, list[str]]:
    """Find or create CLAUDE.md and AGENTS.md and ensure they carry the Cortex rules.

    - If a file already exists and lacks the Cortex section, the section is
      appended at the bottom (existing content is preserved).
    - If a file already has the section, it is left untouched.
    - If a file does not exist, it is created with the section.

    Returns ``{"written": [...], "skipped": [...]}`` listing the file names that
    were created/appended and those that already had the section.
    """
    project_root = Path(project_root)
    written: list[str] = []
    skipped: list[str] = []

    for filename in AGENT_FILES:
        target = project_root / filename
        if target.exists():
            content = target.read_text(encoding="utf-8")
            if CORTEX_MARKER in content:
                skipped.append(filename)
                continue
            target.write_text(content.rstrip("\n") + "\n" + CORTEX_SECTION, encoding="utf-8")
        else:
            target.write_text(CORTEX_SECTION.lstrip("\n"), encoding="utf-8")
        written.append(filename)

    return {"written": written, "skipped": skipped}
