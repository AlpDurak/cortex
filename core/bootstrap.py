"""Project scanner used by `cortex bootstrap` / `cortex scan`."""

from __future__ import annotations

import os
from pathlib import Path

from core.db import DatabaseManager


IGNORE_DIRS = {
    ".git",
    ".cortex",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    ".next",
}

SIGNIFICANT_FILENAMES = {
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}

SIGNIFICANT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".cs",
    ".php",
    ".rb",
    ".sql",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
}


def _language_for(path: Path) -> str:
    suffix_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".cs": "csharp",
        ".php": "php",
        ".rb": "ruby",
        ".sql": "sql",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".md": "markdown",
    }
    if path.name == "Dockerfile":
        return "dockerfile"
    return suffix_map.get(path.suffix.lower(), "text")


def _description_for(path: Path, rel: str) -> str:
    if path.name in {"README.md", "AGENTS.md", "CLAUDE.md"}:
        return f"Project documentation and agent guidance at {rel}."
    if path.name in {"pyproject.toml", "package.json", "go.mod", "Cargo.toml"}:
        return f"Project manifest and dependency configuration at {rel}."
    if path.name.startswith("docker-compose") or path.name == "Dockerfile":
        return f"Container or deployment configuration at {rel}."
    return f"{_language_for(path).title()} source/configuration file at {rel}."


def _iter_significant_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        base = Path(current)
        for name in sorted(names):
            path = base / name
            if name in SIGNIFICANT_FILENAMES or path.suffix.lower() in SIGNIFICANT_SUFFIXES:
                files.append(path)
                if len(files) >= max_files:
                    return files
    return files


def _count(mgr: DatabaseManager, label: str, node_id: str) -> int:
    rows = mgr.query_to_dicts(
        f"MATCH (n:{label} {{id: $id}}) RETURN count(*) AS c",
        {"id": node_id},
    )
    return int(rows[0]["c"]) if rows else 0


def _write_file_node(mgr: DatabaseManager, path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    node_id = f"File:{rel}"
    params = {
        "id": node_id,
        "name": path.name,
        "description": _description_for(path, rel),
        "file_path": rel,
        "language": _language_for(path),
        "source_file": rel,
        "source_line": 1,
    }
    if not _count(mgr, "File", node_id):
        mgr.conn.execute(
            "CREATE (n:File {id: $id, name: $name, description: $description, "
            "code_block: '', file_path: $file_path, language: $language, "
            "source_file: $source_file, source_line: $source_line})",
            params,
        )
    else:
        for prop in ("name", "description", "file_path", "language", "source_file"):
            mgr.conn.execute(
                f"MATCH (n:File {{id: $id}}) SET n.{prop} = ${prop}",
                params,
            )
        mgr.conn.execute(
            "MATCH (n:File {id: $id}) SET n.source_line = $source_line",
            params,
        )
    return node_id


def _write_design_node(
    mgr: DatabaseManager,
    node_id: str,
    name: str,
    section: str,
    description: str,
    rationale: str,
) -> None:
    params = {
        "id": node_id,
        "name": name,
        "section": section,
        "description": description,
        "rationale": rationale,
    }
    if not _count(mgr, "SystemDesign", node_id):
        mgr.conn.execute(
            "CREATE (n:SystemDesign {id: $id, name: $name, description: $description, "
            "code_block: '', design_type: 'baseline', status: 'shipped', "
            "section: $section, rationale: $rationale, source_file: '', source_line: 0})",
            params,
        )
    else:
        for prop in ("name", "section", "description", "rationale"):
            mgr.conn.execute(
                f"MATCH (n:SystemDesign {{id: $id}}) SET n.{prop} = ${prop}",
                params,
            )
        mgr.conn.execute(
            "MATCH (n:SystemDesign {id: $id}) SET n.status = 'shipped'",
            params,
        )


def _edge_exists(mgr: DatabaseManager, src: str, rel: str, dst: str) -> bool:
    rows = mgr.query_to_dicts(
        f"MATCH (a:SystemDesign {{id: $src}})-[r:{rel}]->(b:File {{id: $dst}}) "
        "RETURN count(*) AS c",
        {"src": src, "dst": dst},
    )
    return bool(rows and rows[0]["c"])


def _write_implements_edge(mgr: DatabaseManager, src: str, dst: str) -> bool:
    if _edge_exists(mgr, src, "IMPLEMENTS", dst):
        return False
    mgr.conn.execute(
        "MATCH (a:SystemDesign {id: $src}), (b:File {id: $dst}) "
        "CREATE (a)-[:IMPLEMENTS]->(b)",
        {"src": src, "dst": dst},
    )
    return True


def bootstrap_project_graph(
    root: Path,
    message: str = "Initial graph bootstrap",
    max_files: int = 250,
) -> dict:
    """Scan a project and seed a baseline Cortex graph."""
    root = root.resolve()
    mgr = DatabaseManager(root)
    mgr.init()
    try:
        files = _iter_significant_files(root, max_files=max_files)
        file_ids = [_write_file_node(mgr, path, root) for path in files]

        design_id = "SystemDesign:Overview:ProjectStructure"
        _write_design_node(
            mgr,
            design_id,
            "Project Structure",
            "Overview",
            "Generated baseline map of significant source, documentation, and configuration files.",
            "Created by `cortex bootstrap` so agents have an initial graph before adding detailed architecture decisions.",
        )

        edge_count = 0
        for file_id in file_ids[:100]:
            if _write_implements_edge(mgr, design_id, file_id):
                edge_count += 1

        snapshot = mgr.commit_snapshot(message)
        return {
            "files": len(file_ids),
            "system_design": 1,
            "edges": edge_count,
            "snapshot": snapshot,
        }
    finally:
        mgr.close()
