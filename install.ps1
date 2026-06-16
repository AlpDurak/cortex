# Cortex installer — Windows (PowerShell 5.1+)
# Clones cortex into .\cortex\, creates a venv, installs deps,
# and writes MCP config entries for detected AI tools.
#
# Usage:
#   irm https://raw.githubusercontent.com/AlpDurak/cortex/master/install.ps1 | iex

$ErrorActionPreference = "Stop"

$REPO_URL   = "https://github.com/AlpDurak/cortex.git"
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
    $candidates = @("python", "py")
    foreach ($cmd in $candidates) {
        try {
            $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver) {
                $parts = $ver.Trim().Split(".")
                if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) {
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
    & $script:VENV_PYTHON -m pip install --quiet --upgrade pip
    & $script:VENV_PYTHON -m pip install --quiet -e "$INSTALL_DIR\"
    Write-Ok "Dependencies installed"
}

# ---------------------------------------------------------------------------
# MCP config writing
# ---------------------------------------------------------------------------

function Write-JsonMcpConfig($configFile) {
    $venvPython = $script:VENV_PYTHON
    $pyScript = @'
import json, os, sys

path = sys.argv[1]
venv_python = sys.argv[2]

os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

config = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"  Warning: {path} contains invalid JSON -- creating backup")
        os.rename(path, path + ".bak")

config.setdefault("mcpServers", {})["cortex"] = {
    "command": venv_python,
    "args": ["-m", "cortex.mcp_server"]
}

with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  -> wrote cortex entry to {path}")
'@
    $tmpScript = [System.IO.Path]::GetTempFileName() + ".py"
    $pyScript | Out-File -FilePath $tmpScript -Encoding utf8
    try {
        & $venvPython $tmpScript $configFile $venvPython
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

$script:PYTHON_CMD     = ""
$script:VENV_PYTHON    = ""
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
