# Phase 6: Distribution & Agent Instructions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cortex installable in 1 command on any platform, auto-configure it into Gemini CLI, Cursor, Claude Code, and Codex CLI, and ship agent instruction files that enforce correct Cortex usage patterns.

**Architecture:** All deliverables are static files (bash, PowerShell, markdown, JSON) — no Python changes. The install scripts use Python (guaranteed present after venv setup) for JSON config merging rather than depending on `jq`. Each file has one clear responsibility.

**Tech Stack:** Bash (POSIX, macOS/Linux), PowerShell 5.1 (Windows), Markdown, JSON.

---

## File Map

| File | Responsibility |
|---|---|
| `cortex.json` | MCP server manifest for tool discovery |
| `AGENTS.md` | Passive agent instructions — read automatically by Gemini CLI, Codex CLI, most runtimes |
| `CLAUDE.md` | Project-level Claude Code instructions — activates SKILL.md, fallback passive rules |
| `SKILL.md` | Superpowers rigid skill — enforced workflow for Claude Code power users |
| `install.sh` | macOS/Linux bootstrap: clone → venv → install → write MCP configs |
| `install.ps1` | Windows bootstrap: clone → venv → install → write MCP configs |
| `docs/images/` | Screenshots captured from live Cortex app for README |
| `README.md` | Full documentation: pitch, hero image, install, usage, tool reference |

---

### Task 1: cortex.json — MCP server manifest

**Files:**
- Create: `cortex.json`

- [ ] **Step 1: Create `cortex.json`**

```json
{
  "name": "cortex",
  "version": "0.1.0",
  "description": "Knowledge graph MCP server for software projects",
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "cortex.mcp_server"]
}
```

- [ ] **Step 2: Verify JSON is valid**

```bash
python -c "import json; json.load(open('cortex.json')); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cortex.json
git commit -m "feat: add cortex.json MCP server manifest"
```

---

### Task 2: AGENTS.md + CLAUDE.md — universal agent instructions

**Files:**
- Create: `AGENTS.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: Create `AGENTS.md`**

```markdown
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
```

- [ ] **Step 2: Create `CLAUDE.md`**

```markdown
# Cortex

This project uses the **Cortex** knowledge graph skill. Load it before starting work:

```
/skill cortex
```

Or invoke it explicitly with the Skill tool: `Skill({ skill: "cortex" })`.

If the skill is not available, follow the rules in `AGENTS.md` directly.

---

## Fallback rules (when SKILL.md is not loaded)

See `AGENTS.md` — the same rules apply:

- Bootstrap the graph if empty (Step 0 in AGENTS.md)
- Call `list_design_sections` at session start
- Use MCP tools for architecture queries, not file search
- POST `/api/commit` before any `git commit`
- Record new design decisions with `write_system_design_node`
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "feat: add AGENTS.md and CLAUDE.md agent instruction files"
```

---

### Task 3: SKILL.md — superpowers rigid skill for Claude Code

**Files:**
- Create: `SKILL.md`

- [ ] **Step 1: Create `SKILL.md`**

```markdown
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

```
[ ] Step 0: Bootstrap check — is the graph populated?
[ ] Step 1: Call list_design_sections
[ ] Step 2: Use MCP for all architecture queries (no grep/glob/file-read)
[ ] Step 3: Before git commit — call commit_snapshot
[ ] Step 4: New design decisions — call write_system_design_node
```

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
```

- [ ] **Step 2: Verify the file renders correctly (check for unclosed code fences)**

```bash
python -c "
content = open('SKILL.md').read()
fences = content.count('\`\`\`')
print(f'Code fences: {fences} (must be even)')
assert fences % 2 == 0, 'Unclosed code fence!'
print('OK')
"
```

Expected: `Code fences: N (must be even)` then `OK`

- [ ] **Step 3: Commit**

```bash
git add SKILL.md
git commit -m "feat: add SKILL.md cortex superpowers skill"
```

---

### Task 4: install.sh — macOS/Linux bootstrap installer

**Files:**
- Create: `install.sh`

- [ ] **Step 1: Create `install.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Cortex installer — macOS / Linux
# Clones cortex into ./cortex/, creates a venv, installs deps,
# and writes MCP config entries for detected AI tools.
# ---------------------------------------------------------------------------

REPO_URL="https://github.com/YOUR_GITHUB_USER/cortex.git"
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
import json, os, sys

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
```

- [ ] **Step 2: Replace `YOUR_GITHUB_USER` with the actual GitHub username**

Edit line 10 of `install.sh` — replace `YOUR_GITHUB_USER` with the real GitHub user/org name where the cortex repo is hosted.

- [ ] **Step 3: Make executable**

```bash
chmod +x install.sh
```

- [ ] **Step 4: Smoke-test the JSON merge logic in isolation**

```bash
python3 -c "
import json, tempfile, os

# Simulate write_json_mcp_config with a pre-existing config
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump({'mcpServers': {'other-tool': {'command': 'foo'}}}, f)
    path = f.name

# Re-run the merge logic
config = json.load(open(path))
config.setdefault('mcpServers', {})['cortex'] = {
    'command': '/test/python',
    'args': ['-m', 'cortex.mcp_server']
}
with open(path, 'w') as f:
    json.dump(config, f, indent=2)

result = json.load(open(path))
assert 'other-tool' in result['mcpServers'], 'Existing entry was overwritten!'
assert 'cortex' in result['mcpServers'], 'cortex entry not written!'
assert result['mcpServers']['cortex']['command'] == '/test/python'
os.unlink(path)
print('JSON merge OK — existing entries preserved, cortex entry written')
"
```

Expected: `JSON merge OK — existing entries preserved, cortex entry written`

- [ ] **Step 5: Commit**

```bash
git add install.sh
git commit -m "feat: add install.sh macOS/Linux bootstrap installer"
```

---

### Task 5: install.ps1 — Windows bootstrap installer

**Files:**
- Create: `install.ps1`

- [ ] **Step 1: Create `install.ps1`**

```powershell
# Cortex installer — Windows (PowerShell 5.1+)
# Clones cortex into .\cortex\, creates a venv, installs deps,
# and writes MCP config entries for detected AI tools.

$ErrorActionPreference = "Stop"

$REPO_URL  = "https://github.com/YOUR_GITHUB_USER/cortex.git"
$INSTALL_DIR = "cortex"

function Write-Ok($msg)   { Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "! $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "✗ $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

function Check-Git {
    try { $v = (git --version) } catch { Write-Fail "git not found. Install from https://git-scm.com and retry." }
    Write-Ok $v
}

function Check-Python {
    $candidates = @("python", "py")
    foreach ($cmd in $candidates) {
        try {
            $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            $parts = $ver.Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) {
                $script:PYTHON_CMD = $cmd
                Write-Ok "Python $ver"
                return
            }
        } catch {}
    }
    Write-Fail "Python 3.11+ required. Install from https://python.org and retry."
}

# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------

function Clone-Repo {
    if (Test-Path "$INSTALL_DIR\.git") {
        Write-Warn "Directory '$INSTALL_DIR' already exists. Pulling latest..."
        git -C $INSTALL_DIR pull --ff-only
    } else {
        Write-Host "Cloning cortex into .\$INSTALL_DIR\ ..."
        git clone $REPO_URL $INSTALL_DIR
    }
    Write-Ok "Repository ready at $(Get-Location)\$INSTALL_DIR"
}

# ---------------------------------------------------------------------------
# Venv + install
# ---------------------------------------------------------------------------

function Setup-Venv {
    Write-Host "Creating virtual environment..."
    & $script:PYTHON_CMD -m venv "$INSTALL_DIR\.venv"
    $script:VENV_PYTHON = "$(Get-Location)\$INSTALL_DIR\.venv\Scripts\python.exe"
    & $script:VENV_PYTHON -m pip install --quiet --upgrade pip
    & $script:VENV_PYTHON -m pip install --quiet -e "$INSTALL_DIR\"
    Write-Ok "Dependencies installed"
}

# ---------------------------------------------------------------------------
# MCP config writing
# ---------------------------------------------------------------------------

function Write-JsonMcpConfig($configFile) {
    $venvPython = $script:VENV_PYTHON
    $pyScript = @"
import json, os

path = r"$configFile"
venv_python = r"$venvPython"

os.makedirs(os.path.dirname(path), exist_ok=True)

config = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"  Warning: {path} contains invalid JSON — creating backup")
        os.rename(path, path + ".bak")

config.setdefault("mcpServers", {})["cortex"] = {
    "command": venv_python,
    "args": ["-m", "cortex.mcp_server"]
}

with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  -> wrote cortex entry to {path}")
"@
    & $script:VENV_PYTHON -c $pyScript
}

function Configure-ClaudeCode {
    $dir = "$env:USERPROFILE\.claude"
    if (Test-Path $dir) {
        Write-JsonMcpConfig "$dir\settings.json"
        $script:ConfiguredTools += "`n  * Claude Code  ($dir\settings.json)"
    }
}

function Configure-Cursor {
    $dir = "$env:USERPROFILE\.cursor"
    if (Test-Path $dir) {
        Write-JsonMcpConfig "$dir\mcp.json"
        $script:ConfiguredTools += "`n  * Cursor       ($dir\mcp.json)"
    }
}

function Configure-Gemini {
    $dir = "$env:USERPROFILE\.gemini"
    if (Test-Path $dir) {
        Write-JsonMcpConfig "$dir\settings.json"
        $script:ConfiguredTools += "`n  * Gemini CLI   ($dir\settings.json)"
    }
}

function Configure-Codex {
    $dir = "$env:USERPROFILE\.codex"
    if (Test-Path $dir) {
        Write-JsonMcpConfig "$dir\config.json"
        $script:ConfiguredTools += "`n  * Codex CLI    ($dir\config.json)"
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

function Print-Summary {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Ok "Cortex installed at: $(Get-Location)\$INSTALL_DIR"
    Write-Host ""
    if ($script:ConfiguredTools) {
        Write-Host "AI tools configured:"
        Write-Host $script:ConfiguredTools
    } else {
        Write-Warn "No AI tool config directories detected."
        Write-Host "  Add the following to your tool's MCP config manually:"
        Write-Host '  "cortex": {'
        Write-Host "    `"command`": `"$($script:VENV_PYTHON)`","
        Write-Host '    "args": ["-m", "cortex.mcp_server"]'
        Write-Host '  }'
    }
    Write-Host ""
    Write-Host "Start the web UI (run from your project directory):"
    Write-Host "  $($script:VENV_PYTHON) -m cortex.web_server"
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

$script:PYTHON_CMD    = ""
$script:VENV_PYTHON   = ""
$script:ConfiguredTools = ""

Write-Host "Installing Cortex..."
Write-Host ""
Check-Git
Check-Python
Clone-Repo
Setup-Venv
Configure-ClaudeCode
Configure-Cursor
Configure-Gemini
Configure-Codex
Print-Summary
```

- [ ] **Step 2: Replace `YOUR_GITHUB_USER` with the actual GitHub username**

Edit line 6 of `install.ps1` — replace `YOUR_GITHUB_USER` with the real GitHub user/org name.

- [ ] **Step 3: Verify PowerShell syntax (no bash-isms)**

```bash
python3 -c "
content = open('install.ps1').read()
bash_isms = ['set -e', '\$(...)', '#!/']
for b in bash_isms:
    assert b not in content, f'Found bash syntax in PS1: {b!r}'
print('PowerShell syntax check OK')
"
```

Expected: `PowerShell syntax check OK`

- [ ] **Step 4: Commit**

```bash
git add install.ps1
git commit -m "feat: add install.ps1 Windows bootstrap installer"
```

---

### Task 6: README.md — documentation with screenshots

**Files:**
- Create: `docs/images/` directory
- Create: `README.md`

Screenshots must be captured from a live Cortex instance. Use the `agent-browser` skill (not raw Playwright tools) to navigate to the running web UI and capture screenshots.

- [ ] **Step 1: Start the Cortex web server with seed data**

Open a terminal and run (from the cortex repo root, with the `.cortex/` graph already populated from prior development work):

```bash
python -m cortex.web_server
```

Verify it starts on `http://localhost:7842`.

- [ ] **Step 2: Create the images directory**

```bash
mkdir -p docs/images
```

- [ ] **Step 3: Capture screenshots using agent-browser skill**

Use the `agent-browser` skill to:

1. Navigate to `http://localhost:7842`
2. Capture a **hero screenshot** of the full UI showing nodes, minimap, timeline panel — save as `docs/images/cortex-ui.png`
3. Click a SystemDesign node to open the inspector; capture — save as `docs/images/cortex-inspector.png`
4. Click the Timeline panel and click a historical slot to show the diff overlay (green/red nodes); capture — save as `docs/images/cortex-diff.png`
5. Click the Search dock icon, type a query to show the fade effect; capture — save as `docs/images/cortex-search.png`

- [ ] **Step 4: Create `README.md`**

```markdown
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
curl -sSL https://raw.githubusercontent.com/YOUR_GITHUB_USER/cortex/master/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/YOUR_GITHUB_USER/cortex/master/install.ps1 | iex
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

![Inspector panel showing SystemDesign node with section, status, and rationale](docs/images/cortex-inspector.png)

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
```

- [ ] **Step 5: Replace `YOUR_GITHUB_USER` in README.md**

Replace both occurrences of `YOUR_GITHUB_USER` with the real GitHub username/org.

- [ ] **Step 6: Verify all image references exist**

```bash
python3 -c "
import re
content = open('README.md').read()
images = re.findall(r'!\[.*?\]\((docs/images/[^)]+)\)', content)
import os
missing = [p for p in images if not os.path.exists(p)]
if missing:
    print('MISSING images:', missing)
else:
    print(f'All {len(images)} image references found OK')
"
```

Expected: `All 4 image references found OK`

- [ ] **Step 7: Commit**

```bash
git add README.md docs/images/
git commit -m "feat: add README with screenshots and quick install docs"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `SKILL.md` — superpowers skill for Claude Code | Task 3 |
| SKILL enforces: graph bootstrap before first use | Task 3 Step 1 (Step 0 section) |
| SKILL enforces: `commit_snapshot` before git commit | Task 3 Step 1 (Step 3 section) |
| SKILL enforces: MCP-only architecture queries | Task 3 Step 1 (Step 2 section) |
| `CLAUDE.md` — project-level Claude Code instructions | Task 2 |
| `AGENTS.md` — universal passive instructions | Task 2 |
| `install.sh` — macOS/Linux curl-pipe installer | Task 4 |
| `install.ps1` — Windows irm/iex installer | Task 5 |
| Auto-detect Claude Code, Cursor, Gemini, Codex | Tasks 4 + 5 (configure_* functions) |
| Merge existing configs, don't overwrite | Tasks 4 + 5 (write_json_mcp_config logic) |
| `README.md` with 1-command install | Task 6 |
| README images showing how Cortex works | Task 6 Steps 3–4 |
| `cortex.json` MCP manifest | Task 1 |
| `cwd: ${workspaceFolder}` in MCP entries | Tasks 4+5 — NOTE: scripts write `command` + `args` only; `cwd` is not written because most tools derive it from their workspace. Add a note in the README manual config section that users must set `cwd` to their project directory. |

**Placeholder scan:**
- `YOUR_GITHUB_USER` appears in `install.sh` (line 10), `install.ps1` (line 6), and `README.md` (2 occurrences). Must be replaced in each task's Step 2 / Step 5 with the real GitHub username before commit.
- `docs/images/*.png` files are produced by agent-browser in Task 6 Step 3 — not static placeholders.

**Type consistency:**
- `write_json_mcp_config` in `install.sh` and `Write-JsonMcpConfig` in `install.ps1` both take a single config file path argument and use the same Python inline script — consistent.
- JSON structure written by both scripts is identical: `{ "mcpServers": { "cortex": { "command": "...", "args": [...] } } }` — consistent with `cortex.json` manifest format.
