# Cortex installer — Windows (PowerShell 5.1+)
# Clones cortex into ~/.cortex/cortex, creates a venv, installs deps,
# adds the cortex CLI to the user PATH, and writes MCP config entries
# for detected AI tools.
#
# Usage:
#   irm https://raw.githubusercontent.com/AlpDurak/cortex/master/install.ps1 | iex

$ErrorActionPreference = "Stop"

$REPO_URL     = "https://github.com/AlpDurak/cortex.git"
$INSTALL_ROOT = Join-Path $env:USERPROFILE ".cortex"
$INSTALL_DIR  = Join-Path $INSTALL_ROOT "cortex"

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
    New-Item -ItemType Directory -Force -Path $INSTALL_ROOT | Out-Null
    if (Test-Path "$INSTALL_DIR\.git") {
        Write-Warn "Directory '$INSTALL_DIR' already exists. Pulling latest..."
        git -C "$INSTALL_DIR" pull --ff-only
        if ($LASTEXITCODE -ne 0) { Write-Fail "Could not update existing Cortex repository at $INSTALL_DIR" }
    } else {
        Write-Host "Cloning cortex into $INSTALL_DIR ..."
        git clone $REPO_URL "$INSTALL_DIR"
        if ($LASTEXITCODE -ne 0) { Write-Fail "Could not clone Cortex into $INSTALL_DIR" }
    }
    Write-Ok "Repository ready at $INSTALL_DIR"
}

# ---------------------------------------------------------------------------
# Venv + install
# ---------------------------------------------------------------------------

function Setup-Venv {
    Write-Host "Creating virtual environment..."
    & $script:PYTHON_CMD -m venv --without-pip "$INSTALL_DIR\.venv"
    if ($LASTEXITCODE -ne 0) { Write-Fail "Could not create virtual environment at $INSTALL_DIR\.venv" }

    $script:VENV_PYTHON = Join-Path $INSTALL_DIR ".venv\Scripts\python.exe"
    $script:VENV_CORTEX = Join-Path $INSTALL_DIR ".venv\Scripts\cortex.exe"

    & $script:VENV_PYTHON -m ensurepip --upgrade --default-pip
    if ($LASTEXITCODE -ne 0) { Write-Fail "Could not bootstrap pip in $INSTALL_DIR\.venv" }

    & $script:VENV_PYTHON -m pip install --quiet --upgrade pip
    if ($LASTEXITCODE -ne 0) { Write-Fail "Could not upgrade pip in $INSTALL_DIR\.venv" }

    & $script:VENV_PYTHON -m pip install --quiet -e "$INSTALL_DIR\"
    if ($LASTEXITCODE -ne 0) { Write-Fail "Could not install Cortex dependencies" }

    Write-Ok "Dependencies installed"
}

# ---------------------------------------------------------------------------
# Add venv Scripts to PATH so `cortex` works from any terminal
# ---------------------------------------------------------------------------

function Notify-PathChanged {
    try {
        $signature = @'
using System;
using System.Runtime.InteropServices;

public static class CortexNativeMethods {
    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern IntPtr SendMessageTimeout(
        IntPtr hWnd,
        uint Msg,
        UIntPtr wParam,
        string lParam,
        uint fuFlags,
        uint uTimeout,
        out UIntPtr lpdwResult);
}
'@
        Add-Type -TypeDefinition $signature -ErrorAction SilentlyContinue
        $result = [UIntPtr]::Zero
        [CortexNativeMethods]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, "Environment", 0x0002, 5000, [ref]$result) | Out-Null
    } catch {
        Write-Warn "PATH was updated, but Windows environment notification failed. Open a new terminal if needed."
    }
}

function Add-ToPath {
    $venvScripts = Join-Path $INSTALL_DIR ".venv\Scripts"
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if (-not $userPath) { $userPath = "" }

    $userPathItems = $userPath -split ";" | Where-Object { $_ }
    if ($userPathItems -contains $venvScripts) {
        Write-Ok "PATH already contains venv Scripts"
    } else {
        if ([string]::IsNullOrWhiteSpace($userPath)) {
            $newUserPath = $venvScripts
        } else {
            $newUserPath = "$userPath;$venvScripts"
        }
        [Environment]::SetEnvironmentVariable("PATH", $newUserPath, "User")
        Write-Ok "Added to user PATH: $venvScripts"
        Notify-PathChanged
    }

    $processPathItems = $env:PATH -split ";" | Where-Object { $_ }
    if ($processPathItems -notcontains $venvScripts) {
        $env:PATH = "$venvScripts;$env:PATH"
        Write-Ok "Added to current PowerShell PATH"
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
    Write-Ok "Cortex installed at: $INSTALL_DIR"
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
