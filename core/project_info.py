"""
Scans the project root to extract:
  - Project name  (package.json → pyproject.toml → directory name)
  - Favicon path  (favicon.ico/png/svg in root, public/, assets/, static/)
"""

from __future__ import annotations

import json
from pathlib import Path


_FAVICON_CANDIDATES = [
    "favicon.ico", "favicon.png", "favicon.svg",
    "logo.svg", "logo.png", "icon.png",
]
_FAVICON_DIRS = ["", "public", "assets", "static", "src/assets"]


def get_project_name(root: Path) -> str:
    # 1. package.json
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            name = data.get("name", "").strip()
            if name:
                return name
        except Exception:
            pass

    # 2. pyproject.toml
    ppt = root / "pyproject.toml"
    if ppt.exists():
        for line in ppt.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("name") and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val

    # 3. Directory name
    return root.name


def find_favicon(root: Path) -> Path | None:
    for d in _FAVICON_DIRS:
        base = root / d if d else root
        for name in _FAVICON_CANDIDATES:
            candidate = base / name
            if candidate.exists():
                return candidate
    return None
