#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Cortex installer — macOS / Linux
# Clones cortex into ./cortex/, creates a venv, installs deps,
# and writes MCP config entries for detected AI tools.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/AlpDurak/cortex/master/install.sh | bash
# ---------------------------------------------------------------------------

REPO_URL="https://github.com/AlpDurak/cortex.git"
INSTALL_DIR="cortex"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

check_git() {
  command -v git >/dev/null 2>&1 || fail "git not found. Install git and retry."
  ok "git $(git --version | awk '{print $3}')"
}

check_python() {
  local py=""
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      local ver
      ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      local major minor
      major=$(echo "$ver" | cut -d. -f1)
      minor=$(echo "$ver" | cut -d. -f2)
      if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
        PYTHON_CMD="$cmd"
        ok "Python $ver"
        return
      fi
    fi
  done
  fail "Python 3.11+ required. Install from https://python.org and retry."
}

# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

clone_repo() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Directory '$INSTALL_DIR' already exists. Pulling latest..."
    git -C "$INSTALL_DIR" pull --ff-only
  else
    echo "Cloning cortex into ./$INSTALL_DIR/ ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
  fi
  ok "Repository ready at $(pwd)/$INSTALL_DIR"
}

# ---------------------------------------------------------------------------
# Venv + install
# ---------------------------------------------------------------------------

setup_venv() {
  echo "Creating virtual environment..."
  "$PYTHON_CMD" -m venv "$INSTALL_DIR/.venv"
  VENV_PYTHON="$(pwd)/$INSTALL_DIR/.venv/bin/python"
  "$VENV_PYTHON" -m pip install --quiet --upgrade pip
  "$VENV_PYTHON" -m pip install --quiet -e "$INSTALL_DIR/"
  ok "Dependencies installed"
}

# ---------------------------------------------------------------------------
# MCP config writing (uses the venv Python for JSON merging)
# ---------------------------------------------------------------------------

write_json_mcp_config() {
  local config_file="$1"
  "$VENV_PYTHON" - <<PYEOF
import json, os

path = "$config_file"
venv_python = "$VENV_PYTHON"

os.makedirs(os.path.dirname(path), exist_ok=True)

config = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"  Warning: {path} contains invalid JSON — creating backup and overwriting")
        os.rename(path, path + ".bak")

config.setdefault("mcpServers", {})["cortex"] = {
    "command": venv_python,
    "args": ["-m", "cortex.mcp_server"]
}

with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  → wrote cortex entry to {path}")
PYEOF
}

configure_claude_code() {
  if [ -d "$HOME/.claude" ]; then
    write_json_mcp_config "$HOME/.claude/settings.json"
    CONFIGURED_TOOLS="$CONFIGURED_TOOLS\n  • Claude Code  ($HOME/.claude/settings.json)"
  fi
}

configure_cursor() {
  if [ -d "$HOME/.cursor" ]; then
    write_json_mcp_config "$HOME/.cursor/mcp.json"
    CONFIGURED_TOOLS="$CONFIGURED_TOOLS\n  • Cursor       ($HOME/.cursor/mcp.json)"
  fi
}

configure_gemini() {
  if [ -d "$HOME/.gemini" ]; then
    write_json_mcp_config "$HOME/.gemini/settings.json"
    CONFIGURED_TOOLS="$CONFIGURED_TOOLS\n  • Gemini CLI   ($HOME/.gemini/settings.json)"
  fi
}

configure_codex() {
  if [ -d "$HOME/.codex" ]; then
    write_json_mcp_config "$HOME/.codex/config.json"
    CONFIGURED_TOOLS="$CONFIGURED_TOOLS\n  • Codex CLI    ($HOME/.codex/config.json)"
  fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_summary() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ok "Cortex installed at: $(pwd)/$INSTALL_DIR"
  echo ""
  if [ -n "$CONFIGURED_TOOLS" ]; then
    echo "AI tools configured:"
    echo -e "$CONFIGURED_TOOLS"
  else
    warn "No AI tool config directories detected."
    echo "  Add the following entry manually to your tool's MCP config:"
    echo '  "cortex": {'
    echo "    \"command\": \"$VENV_PYTHON\","
    echo '    "args": ["-m", "cortex.mcp_server"]'
    echo '  }'
  fi
  echo ""
  echo "Start the web UI (run from your project directory):"
  echo "  $VENV_PYTHON -m cortex.web_server"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PYTHON_CMD=""
VENV_PYTHON=""
CONFIGURED_TOOLS=""

echo "Installing Cortex..."
echo ""
check_git
check_python
clone_repo
setup_venv
configure_claude_code
configure_cursor
configure_gemini
configure_codex
print_summary
