"""
Cortex Connect — interactive MCP config installer.

Displays a checkbox list of AI tool platforms. User toggles with SPACE,
confirms with ENTER. Writes the Cortex MCP config to selected platform
config files.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


PLATFORMS = [
    {
        "name": "Claude Code",
        "key": "claude-code",
        "config_path": "~/.claude/settings.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Cursor",
        "key": "cursor",
        "config_path": "~/.cursor/mcp.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Gemini CLI",
        "key": "gemini",
        "config_path": "~/.gemini/settings.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Codex CLI",
        "key": "codex",
        "config_path": "~/.codex/config.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Windsurf",
        "key": "windsurf",
        "config_path": "~/.codeium/windsurf/mcp_config.json",
        "config_key": "mcpServers",
    },
    {
        "name": "VS Code Copilot Chat",
        "key": "vscode",
        "config_path": "~/.vscode/mcp.json",
        "config_key": "servers",
    },
    {
        "name": "Amp",
        "key": "amp",
        "config_path": "~/.amp/mcp.json",
        "config_key": "mcpServers",
    },
    {
        "name": "Kiro",
        "key": "kiro",
        "config_path": "~/.kiro/settings/mcp.json",
        "config_key": "mcpServers",
    },
    {
        "name": "OpenCode",
        "key": "opencode",
        "config_path": "~/.config/opencode/config.json",
        "config_key": "mcp.servers",
    },
]


def _mcp_entry(cortex_bin: str, project_root: str) -> dict:
    return {
        "command": cortex_bin,
        "args": ["mcp", "--root", project_root],
    }


def _write_config(platform: dict, entry: dict) -> tuple[bool, str]:
    """Write or update the MCP server entry for a platform. Returns (success, message)."""
    config_path = Path(platform["config_path"]).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    key = platform["config_key"]

    # Handle nested keys like "mcp.servers"
    if "." in key:
        parts = key.split(".", 1)
        if parts[0] not in existing:
            existing[parts[0]] = {}
        existing[parts[0]][parts[1]] = existing.get(parts[0], {}).get(parts[1], {})
        existing[parts[0]][parts[1]]["cortex"] = entry
    else:
        if key not in existing:
            existing[key] = {}
        existing[key]["cortex"] = entry

    try:
        config_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return True, f"Written to {config_path}"
    except Exception as exc:
        return False, f"Failed: {exc}"


def _find_cortex_bin() -> str:
    """Find the cortex binary path (sys.executable's sibling or PATH)."""
    import shutil
    which = shutil.which("cortex")
    if which:
        return which
    scripts_dir = Path(sys.executable).parent
    for name in ("cortex", "cortex.exe"):
        candidate = scripts_dir / name
        if candidate.exists():
            return str(candidate)
    return "cortex"


def _checkbox_ui(platforms: list[dict]) -> list[str]:
    """
    Interactive checkbox UI (pure terminal, no npm).
    Returns list of selected platform keys.

    Controls:
      UP/DOWN arrows — move cursor
      SPACE — toggle selection
      ENTER — confirm
      q — quit without installing
    """
    import tty
    import termios

    selected = set()
    cursor = 0
    N = len(platforms)

    def _render():
        sys.stdout.write(f"\033[{N + 3}A")
        sys.stdout.write("\033[0J")
        sys.stdout.write("\r\n")
        sys.stdout.write("  Cortex Connect — select AI tools to install MCP config\r\n")
        sys.stdout.write("  SPACE=toggle  ENTER=install  q=quit\r\n\r\n")
        for i, p in enumerate(platforms):
            check = "●" if p["key"] in selected else "○"
            arrow = ">" if i == cursor else " "
            sys.stdout.write(f"  {arrow} [{check}] {p['name']}\r\n")
        sys.stdout.flush()

    for _ in range(N + 3):
        sys.stdout.write("\r\n")
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            _render()
            ch = sys.stdin.read(1)
            if ch == "\r" or ch == "\n":
                break
            elif ch in ("q", "Q"):
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                sys.stdout.write("\r\n[Cortex Connect] Aborted.\r\n")
                sys.stdout.flush()
                return []
            elif ch == " ":
                key = platforms[cursor]["key"]
                if key in selected:
                    selected.discard(key)
                else:
                    selected.add(key)
            elif ch == "\x1b":
                seq = sys.stdin.read(2)
                if seq == "[A":
                    cursor = max(0, cursor - 1)
                elif seq == "[B":
                    cursor = min(N - 1, cursor + 1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    sys.stdout.write("\r\n")
    sys.stdout.flush()
    return list(selected)


def _checkbox_ui_windows(platforms: list[dict]) -> list[str]:
    """Fallback checkbox UI for Windows (no tty/termios)."""
    print("\nCortex Connect — select AI tools to install MCP config")
    print("Enter numbers separated by spaces (e.g. 1 3 5), or 'all', or 'q' to quit:\n")
    for i, p in enumerate(platforms, 1):
        print(f"  {i}. {p['name']}")
    print()
    choice = input("Your selection: ").strip()
    if not choice or choice.lower() == "q":
        return []
    if choice.lower() == "all":
        return [p["key"] for p in platforms]
    selected = []
    for part in choice.split():
        try:
            idx = int(part) - 1
            if 0 <= idx < len(platforms):
                selected.append(platforms[idx]["key"])
        except ValueError:
            pass
    return selected


def _ask_yes_no(prompt: str) -> bool:
    """Prompt the user for Y/N. Returns True for yes."""
    while True:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False


def _install_git_hook(project_root: Path) -> None:
    """Install the Cortex post-commit hook into the nearest .git/hooks/ directory."""
    import stat

    # Import constants from main — they may be defined there
    try:
        from cortex.main import _HOOK_MARKER, _HOOK_SCRIPT
    except ImportError:
        _HOOK_MARKER = "# cortex-hook"
        _HOOK_SCRIPT = """\
#!/bin/sh
# cortex-hook — managed by 'cortex hook install'. Do not edit this line.
CORTEX_ROOT="$(git rev-parse --show-toplevel)"
MSG="$(git log -1 --pretty=%s 2>/dev/null || echo 'git commit')"
SHA="$(git log -1 --pretty=%H 2>/dev/null || echo '')"
cortex snapshot --message "$MSG" --sha "$SHA" --root "$CORTEX_ROOT" 2>/dev/null || true
"""

    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        candidate = project_root
        while candidate != candidate.parent:
            candidate = candidate.parent
            if (candidate / ".git").is_dir():
                git_dir = candidate / ".git"
                break
        else:
            print("  ✗ Git Ledger: .git directory not found — skipping.")
            return

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "post-commit"
    hook_path.write_text(_HOOK_SCRIPT, encoding="utf-8")
    current = hook_path.stat().st_mode
    hook_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"  ✓ Git Ledger: hook installed at {hook_path}")
    print("    Every git commit will now auto-snapshot the Cortex graph.")


def run_connect(
    project_root: Path,
    preselect: list[str] | None = None,
    git_ledger: bool | None = None,
) -> None:
    """
    Run the interactive Cortex Connect installer.

    After platform selection, asks whether to enable Git Ledger
    (the Anchored Commits git post-commit hook for auto graph snapshots).
    """
    cortex_bin = _find_cortex_bin()
    root_str = str(project_root)

    if preselect is not None:
        selected_keys = preselect
    elif sys.platform == "win32":
        selected_keys = _checkbox_ui_windows(PLATFORMS)
    else:
        try:
            selected_keys = _checkbox_ui(PLATFORMS)
        except Exception:
            selected_keys = _checkbox_ui_windows(PLATFORMS)

    if not selected_keys:
        print("[Cortex Connect] No platforms selected.")
    else:
        entry = _mcp_entry(cortex_bin, root_str)
        print(f"\n[Cortex Connect] Installing for: {', '.join(selected_keys)}\n")

        for platform in PLATFORMS:
            if platform["key"] not in selected_keys:
                continue
            ok, msg = _write_config(platform, entry)
            icon = "✓" if ok else "✗"
            print(f"  {icon} {platform['name']}: {msg}")

    # Git Ledger prompt — always shown regardless of platform selection
    print()
    if git_ledger is None:
        git_ledger = _ask_yes_no(
            "[Cortex Connect] Enable Git Ledger? (auto-snapshot graph on every git commit)"
        )

    if git_ledger:
        _install_git_hook(project_root)
    else:
        print("  Git Ledger skipped. Enable later with: cortex hook install")

    print(f"\n[Cortex Connect] Done. MCP binary: {cortex_bin}")
    if selected_keys:
        print("  Start the MCP server with: cortex mcp --root <project-root>")
