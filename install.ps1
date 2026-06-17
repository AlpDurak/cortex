# Cortex installer — Windows (PowerShell 5.1+)
# Clones cortex into .\cortex\, creates a venv, installs deps,
# adds the cortex CLI to the user PATH, and writes MCP config entries
# for detected AI tools.
#
# Usage:
#   irm https://raw.githubusercontent.com/AlpDurak/cortex/master/install.ps1 | iex

$ErrorActionPreference = "Stop"

$REPO_URL    = "https://github.com/AlpDurak/cortex.git"
$INSTALL_DIR = "cortex"

function Write-Ok($msg)   { Write-Host "OK $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "!  $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "X  $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

function Check-Git {
    try { $v = (git --version) } catch { Write-Fail "git not found. Install from https://git-scm.com and retry." }
    Write-Ok $v
}

function Check-Python {
    foreach ($cmd in @("python", "py")) {
        try {
            $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver) {
                $parts = $ver.Trim().Split(".")
                if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11)) {
                    $script:PYTHON_CMD = $cmd
                    Write-Ok "Python $ver"
                    return
                }
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
    $script:VENV_CORTEX = "$(Get-Location)\$INSTALL_DIR\.venv\Scripts\cortex.exe"
    & $script:VENV_PYTHON -m pip install --quiet --upgrade pip
    & $script:VENV_PYTHON -m pip install --quiet -e "$INSTALL_DIR\"
    Write-Ok "Dependencies installed"
}

# ---------------------------------------------------------------------------
# Add venv Scripts to user PATH so `cortex` works from any terminal
# ---------------------------------------------------------------------------

function Add-ToPath {
    $venvScripts = "$(Get-Location)\$INSTALL_DIR\.venv\Scripts"
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -like "*$venvScripts*") {
        Write-Ok "PATH already contains venv Scripts"
    } else {
        [Environment]::SetEnvironmentVariable("PATH", "$userPath;$venvScripts", "User")
        Write-Ok "Added to user PATH: $venvScripts"
        Write-Host "  Restart your terminal (or open a new one) for 'cortex' to be available." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# MCP config writing — uses `cortex mcp` as the server command
# ---------------------------------------------------------------------------

function Write-JsonMcpConfig($configFile) {
    $venvCortex = $script:VENV_CORTEX
    $pyScript = @'
import json, os, sys

path = sys.argv[1]
cortex_bin = sys.argv[2]

os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

config = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"  Warning: {path} has invalid JSON -- backing up")
        os.rename(path, path + ".bak")

config.setdefault("mcpServers", {})["cortex"] = {
    "command": cortex_bin,
    "args": ["mcp"]
}

with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  -> {path}")
'@
    $tmpScript = [System.IO.Path]::GetTempFileName() + ".py"
    $pyScript | Out-File -FilePath $tmpScript -Encoding utf8
    try {
        & $script:VENV_PYTHON $tmpScript $configFile $venvCortex
    } finally {
        Remove-Item $tmpScript -ErrorAction SilentlyContinue
    }
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
        Write-Host "    `"command`": `"$($script:VENV_CORTEX)`","
        Write-Host '    "args": ["mcp"]'
        Write-Host '  }'
    }

    Write-Host ""
    Write-Host "Usage (run from any project directory):"
    Write-Host "  cortex init        Initialize the knowledge graph for this project"
    Write-Host "  cortex run         Start the web UI  ->  http://localhost:7842"
    Write-Host "  cortex run --port 8000  (custom port)"
    Write-Host ""
    Write-Host "Note: open a new terminal for 'cortex' to be available on PATH." -ForegroundColor Yellow
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

$script:PYTHON_CMD     = ""
$script:VENV_PYTHON    = ""
$script:VENV_CORTEX    = ""
$script:ConfiguredTools = ""

Write-Host "Installing Cortex..."
Write-Host ""
Check-Git
Check-Python
Clone-Repo
Setup-Venv
Add-ToPath
Configure-ClaudeCode
Configure-Cursor
Configure-Gemini
Configure-Codex
Print-Summary
