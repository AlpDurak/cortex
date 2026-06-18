#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Cortex installer — macOS / Linux
#
# Sets up Cortex, then lets you pick (with an interactive checkbox menu) which
# AI CLI tools to install Cortex into — fully: MCP server config, the Cortex
# skill, and agent instructions.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/AlpDurak/cortex/master/install.sh | bash
#
# Non-interactive:
#   curl -sSL <url> | bash -s -- --yes
#   curl -sSL <url> | bash -s -- --tools claude,cursor
# ---------------------------------------------------------------------------

REPO_URL="https://github.com/AlpDurak/cortex.git"
INSTALL_ROOT="$HOME/.cortex"
INSTALL_DIR="$INSTALL_ROOT/cortex"

ASSUME_YES=0
TOOLS_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes) ASSUME_YES=1; shift ;;
    --tools)  TOOLS_ARG="${2:-}"; shift 2 ;;
    --tools=*) TOOLS_ARG="${1#*=}"; shift ;;
    *) shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Pretty-UI primitive layer
# ---------------------------------------------------------------------------

if [ -t 1 ] || [ -e /dev/tty ]; then
  ESC=$'\033'
  NC="${ESC}[0m"; DIM="${ESC}[2m"; BOLD="${ESC}[1m"
  RED="${ESC}[31m"; GREEN="${ESC}[32m"; YELLOW="${ESC}[33m"
  BLUE="${ESC}[34m"; MAGENTA="${ESC}[35m"; CYAN="${ESC}[36m"
  ORANGE="${ESC}[38;2;249;115;22m"
else
  ESC=""; NC=""; DIM=""; BOLD=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; MAGENTA=""; CYAN=""; ORANGE=""
fi

ok()   { printf "  ${GREEN}✓${NC} %b\n" "$*"; }
warn() { printf "  ${YELLOW}!${NC} %b\n" "$*"; }
info() { printf "  ${ORANGE}→${NC} %b\n" "$*"; }
skip() { printf "  ${DIM}·  %b${NC}\n" "$*"; }
fail() { printf "  ${RED}✗${NC} %b\n" "$*"; exit 1; }

show_banner() {
  printf "\n"
  printf "${ORANGE}${BOLD}%s${NC}\n" " ██████╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗"
  printf "${ORANGE}${BOLD}%s${NC}\n" "██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝"
  printf "${ORANGE}${BOLD}%s${NC}\n" "██║     ██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝ "
  printf "${ORANGE}${BOLD}%s${NC}\n" "██║     ██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗ "
  printf "${ORANGE}${BOLD}%s${NC}\n" "╚██████╗╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗"
  printf "${ORANGE}${BOLD}%s${NC}\n" " ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝"
  printf "${DIM}%s${NC}\n\n" "        knowledge-graph memory for your codebase"
}

STEP_NO=0
STEP_TOTAL=6
step() {
  STEP_NO=$((STEP_NO + 1))
  printf "\n${ORANGE}${BOLD}[%d/%d]${NC} ${BOLD}%s${NC}\n" "$STEP_NO" "$STEP_TOTAL" "$1"
  printf "${DIM}──────────────────────────────────────────────────${NC}\n"
}

# spin "label" cmd args...   — runs the command while animating \ | / -
spin() {
  local label="$1"; shift
  local log; log=$(mktemp)
  ( "$@" >"$log" 2>&1 ) &
  local pid=$!
  local frames='\|/-' i=0
  printf "${ESC}[?25l" 2>/dev/null || true
  while kill -0 "$pid" 2>/dev/null; do
    printf "\r  ${ORANGE}%s${NC} %s   " "${frames:i++%4:1}" "$label"
    sleep 0.1
  done
  local status=0
  wait "$pid" || status=$?
  printf "${ESC}[?25h" 2>/dev/null || true
  if [ "$status" -ne 0 ]; then
    printf "\r  ${RED}✗${NC} %s            \n" "$label"
    sed 's/^/      '"${DIM}"'/; s/$/'"${NC}"'/' "$log" || cat "$log"
    rm -f "$log"
    return 1
  fi
  printf "\r  ${GREEN}✓${NC} %s            \n" "$label"
  rm -f "$log"
}

# Interactive checkbox menu over the parallel arrays MS_LABELS / MS_HINTS /
# MS_CHECKED (0|1). Mutates MS_CHECKED in place.
MS_LABELS=(); MS_HINTS=(); MS_CHECKED=()
multiselect() {
  local count=${#MS_LABELS[@]} cur=0 key rest

  _ms_row() {
    local idx=$1 glyph pointer label
    if [ "${MS_CHECKED[$idx]}" -eq 1 ]; then glyph="${GREEN}◈${NC}"; else glyph="${DIM}◇${NC}"; fi
    if [ "$idx" -eq "$cur" ]; then
      pointer="${ORANGE}›${NC}"; label="${ORANGE}${BOLD}${MS_LABELS[$idx]}${NC}"
    else
      pointer=" "; label="${MS_LABELS[$idx]}"
    fi
    printf " %b %b  %b ${DIM}%s${NC}" "$pointer" "$glyph" "$label" "${MS_HINTS[$idx]}"
  }

  printf "\n  ${DIM}↑/↓ move · Space toggle · a all · n none · Enter confirm${NC}\n"
  local i
  for ((i = 0; i < count; i++)); do _ms_row "$i"; printf "\n"; done

  printf "${ESC}[?25l" 2>/dev/null || true
  while true; do
    IFS= read -rsn1 key </dev/tty
    if [ "$key" = "$ESC" ]; then
      read -rsn2 -t 0.001 rest </dev/tty || true
      key+="$rest"
    fi
    case "$key" in
      "${ESC}[A") cur=$(((cur - 1 + count) % count)) ;;
      "${ESC}[B") cur=$(((cur + 1) % count)) ;;
      " ")        MS_CHECKED[$cur]=$((1 - MS_CHECKED[$cur])) ;;
      "")         break ;;
      a|A)        for ((i = 0; i < count; i++)); do MS_CHECKED[$i]=1; done ;;
      n|N)        for ((i = 0; i < count; i++)); do MS_CHECKED[$i]=0; done ;;
    esac
    printf "${ESC}[%dA" "$count"
    for ((i = 0; i < count; i++)); do printf "${ESC}[2K"; _ms_row "$i"; printf "\n"; done
  done
  printf "${ESC}[?25h" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

PYTHON_CMD=""
check_git() {
  command -v git >/dev/null 2>&1 || fail "git not found. Install git and retry."
  ok "git ready  ${DIM}($(git --version | awk '{print $3}'))${NC}"
}

check_python() {
  local cmd ver major minor
  for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      major=$(echo "$ver" | cut -d. -f1)
      minor=$(echo "$ver" | cut -d. -f2)
      if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; }; then
        PYTHON_CMD="$cmd"
        ok "Python $ver  ${DIM}($cmd)${NC}"
        return
      fi
    fi
  done
  fail "Python 3.11+ required. Install from https://python.org and retry."
}

# ---------------------------------------------------------------------------
# Clone + venv
# ---------------------------------------------------------------------------

_do_clone() {
  mkdir -p "$INSTALL_ROOT"
  if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only
  else
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
}

VENV_PYTHON=""
VENV_CORTEX=""
_do_venv() {
  "$PYTHON_CMD" -m venv --without-pip "$INSTALL_DIR/.venv"
  "$INSTALL_DIR/.venv/bin/python" -m ensurepip --upgrade --default-pip
}
_do_pip() {
  "$VENV_PYTHON" -m pip install --quiet --upgrade pip
  "$VENV_PYTHON" -m pip install --quiet -e "$INSTALL_DIR/"
}

clone_repo() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    spin "Updating existing repository" _do_clone || fail "Could not update the Cortex repository"
  else
    spin "Cloning cortex into ~/.cortex/cortex" _do_clone || fail "Could not clone Cortex"
  fi
}

setup_venv() {
  VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"
  VENV_CORTEX="$INSTALL_DIR/.venv/bin/cortex"
  spin "Creating virtual environment" _do_venv || fail "Could not create virtual environment"
  spin "Installing Cortex and dependencies (this can take a minute)" _do_pip || fail "Could not install Cortex dependencies"
}

# ---------------------------------------------------------------------------
# Link the cortex CLI onto PATH
# ---------------------------------------------------------------------------

ensure_path_file() {
  local file="$1"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  grep -Fq "CORTEX PATH" "$file" && return
  grep -Fq "$HOME/.local/bin" "$file" && return
  cat >>"$file" <<'EOF'

# >>> CORTEX PATH >>>
export PATH="$HOME/.local/bin:$PATH"
# <<< CORTEX PATH <<<
EOF
}

ensure_shell_path() {
  export PATH="$HOME/.local/bin:$PATH"
  ensure_path_file "$HOME/.profile"
  ensure_path_file "$HOME/.bashrc"
  ensure_path_file "$HOME/.bash_profile"
  ensure_path_file "$HOME/.zshrc"
  ensure_path_file "$HOME/.zprofile"
}

link_cli() {
  mkdir -p "$HOME/.local/bin"
  ln -sf "$VENV_CORTEX" "$HOME/.local/bin/cortex"
  ok "cortex linked → ${DIM}~/.local/bin/cortex${NC}"
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) ensure_shell_path; ok "Added ~/.local/bin to your shell startup files" ;;
  esac
}

# ---------------------------------------------------------------------------
# Per-tool integration
# ---------------------------------------------------------------------------

write_json_mcp_config() {
  local config_file="$1"
  "$VENV_PYTHON" - "$config_file" "$VENV_CORTEX" <<'PYEOF'
import json, os, sys
path, cortex_bin = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
config = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        os.rename(path, path + ".bak")
config.setdefault("mcpServers", {})["cortex"] = {"type": "stdio", "command": cortex_bin, "args": ["mcp"]}
with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PYEOF
}

ALL_TOOLS="claude cursor gemini codex"
tool_label()   { case "$1" in claude) echo "Claude Code";; cursor) echo "Cursor";; gemini) echo "Gemini CLI";; codex) echo "Codex CLI";; esac; }
tool_dir()     { case "$1" in claude) echo "$HOME/.claude";; cursor) echo "$HOME/.cursor";; gemini) echo "$HOME/.gemini";; codex) echo "$HOME/.codex";; esac; }
tool_mcpfile() { case "$1" in claude) echo "settings.json";; cursor) echo "mcp.json";; gemini) echo "settings.json";; codex) echo "config.json";; esac; }
tool_skill()   { [ "$1" = "claude" ]; }
tool_agents()  { [ "$1" != "claude" ]; }

# Claude Code loads user-scoped MCP servers from ~/.claude.json (NOT
# ~/.claude/settings.json), so it needs its own configuration path.
configure_claude_mcp() {
  local claude_json="$HOME/.claude.json"
  if command -v claude >/dev/null 2>&1; then
    claude mcp remove cortex --scope user >/dev/null 2>&1 || true
    if claude mcp add cortex --scope user -- "$VENV_CORTEX" mcp >/dev/null 2>&1; then
      ok "MCP server   ${DIM}${claude_json} (claude mcp add)${NC}"
      return
    fi
  fi
  # Fallback: merge directly into ~/.claude.json.
  if write_json_mcp_config "$claude_json" >/dev/null 2>&1; then
    ok "MCP server   ${DIM}${claude_json}${NC}"
  else
    warn "MCP config failed for ${claude_json}"
  fi
}

INSTALLED_TOOLS=()
install_tool() {
  local key="$1" dir mcp
  dir="$(tool_dir "$key")"
  printf "\n  ${BOLD}%s${NC}\n" "$(tool_label "$key")"
  mkdir -p "$dir"

  if [ "$key" = "claude" ]; then
    configure_claude_mcp
  else
    mcp="$dir/$(tool_mcpfile "$key")"
    if write_json_mcp_config "$mcp" >/dev/null 2>&1; then
      ok "MCP server   ${DIM}${mcp}${NC}"
    else
      warn "MCP config failed for ${mcp}"
    fi
  fi

  if tool_skill "$key"; then
    mkdir -p "$dir/skills/cortex"
    cp -f "$INSTALL_DIR/SKILL.md" "$dir/skills/cortex/SKILL.md"
    ok "Skill        ${DIM}${dir}/skills/cortex/SKILL.md${NC}"
  fi

  if tool_agents "$key"; then
    cp -f "$INSTALL_DIR/AGENTS.md" "$dir/AGENTS.md"
    ok "Instructions ${DIM}${dir}/AGENTS.md${NC}"
  fi

  INSTALLED_TOOLS+=("$(tool_label "$key")")
}

SELECTED=()
select_tools() {
  local key idx=0
  MS_LABELS=(); MS_HINTS=(); MS_CHECKED=()
  local keys=()
  for key in $ALL_TOOLS; do
    keys+=("$key")
    MS_LABELS+=("$(tool_label "$key")")
    if [ -d "$(tool_dir "$key")" ]; then
      MS_HINTS+=("(detected)"); MS_CHECKED+=(1)
    else
      MS_HINTS+=("(not found)"); MS_CHECKED+=(0)
    fi
  done

  # Explicit --tools wins and skips the menu.
  if [ -n "$TOOLS_ARG" ]; then
    for ((idx = 0; idx < ${#keys[@]}; idx++)); do
      case ",$TOOLS_ARG," in *",${keys[$idx]},"*) MS_CHECKED[$idx]=1 ;; *) MS_CHECKED[$idx]=0 ;; esac
    done
  elif [ "$ASSUME_YES" -eq 0 ] && [ -r /dev/tty ]; then
    multiselect
  else
    info "Non-interactive: installing into detected tools."
  fi

  for ((idx = 0; idx < ${#keys[@]}; idx++)); do
    [ "${MS_CHECKED[$idx]}" -eq 1 ] && SELECTED+=("${keys[$idx]}")
  done
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_summary() {
  printf "\n"
  printf "${GREEN}╭────────────────────────────────────────────────╮${NC}\n"
  printf "${GREEN}│${NC}  ${BOLD}Cortex is installed.${NC}                          ${GREEN}│${NC}\n"
  printf "${GREEN}╰────────────────────────────────────────────────╯${NC}\n\n"
  ok "Location: ${DIM}${INSTALL_DIR}${NC}"
  printf "\n"

  if [ "${#INSTALLED_TOOLS[@]}" -gt 0 ]; then
    printf "  ${BOLD}Configured tools:${NC}\n"
    local t
    for t in "${INSTALLED_TOOLS[@]}"; do printf "    ${GREEN}✓${NC} %s\n" "$t"; done
  else
    warn "No AI tools selected. Add this to a tool's MCP config manually:"
    printf "    ${DIM}\"cortex\": { \"command\": \"%s\", \"args\": [\"mcp\"] }${NC}\n" "$VENV_CORTEX"
  fi

  printf "\n  ${BOLD}Usage${NC} ${DIM}(from any project directory)${NC}\n"
  printf "    ${ORANGE}cortex init${NC}   Initialize the knowledge graph for this project\n"
  printf "    ${ORANGE}cortex run${NC}    Start the web UI  ${DIM}→  http://localhost:7842${NC}\n"
  printf "\n  ${YELLOW}!${NC} Open a new terminal for ${ORANGE}cortex${NC} to be available on PATH.\n\n"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

show_banner

step "Checking prerequisites"
check_git
check_python

step "Fetching Cortex"
clone_repo

step "Setting up the Python environment"
setup_venv

step "Adding the cortex CLI to PATH"
link_cli

step "Choose AI tools to install Cortex into"
select_tools

step "Installing Cortex into your tools"
if [ "${#SELECTED[@]}" -eq 0 ]; then
  skip "No tools selected — skipping."
else
  for key in "${SELECTED[@]}"; do install_tool "$key"; done
fi

print_summary
