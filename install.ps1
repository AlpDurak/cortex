#requires -Version 5.1
<#
  Cortex installer — Windows (PowerShell 5.1+)

  Sets up Cortex, then lets you pick (with an interactive checkbox menu) which
  AI CLI tools to install Cortex into — fully: MCP server config, the Cortex
  skill, and agent instructions.

  Usage:
    irm https://raw.githubusercontent.com/AlpDurak/cortex/master/install.ps1 | iex

  Non-interactive:
    & ([scriptblock]::Create((irm <url>))) -Yes
    & ([scriptblock]::Create((irm <url>))) -Tools claude,cursor
#>
param(
    [switch]$Yes,
    [string]$Tools = ""
)

$ErrorActionPreference = "Stop"

$REPO_URL     = "https://github.com/AlpDurak/cortex.git"
$INSTALL_ROOT = Join-Path $env:USERPROFILE ".cortex"
$INSTALL_DIR  = Join-Path $INSTALL_ROOT "cortex"

# ---------------------------------------------------------------------------
# Pretty-UI primitive layer
# ---------------------------------------------------------------------------

$ESC = [char]27

function Enable-Ansi {
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
    try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
    try {
        $sig = @'
using System;
using System.Runtime.InteropServices;
public static class CortexVT {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr GetStdHandle(int nStdHandle);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
}
'@
        Add-Type -TypeDefinition $sig -ErrorAction SilentlyContinue
        $h = [CortexVT]::GetStdHandle(-11)
        $mode = 0
        if ([CortexVT]::GetConsoleMode($h, [ref]$mode)) {
            [CortexVT]::SetConsoleMode($h, $mode -bor 0x0004) | Out-Null
        }
    } catch {}
}

$C = @{
    reset   = "$ESC[0m";  dim    = "$ESC[2m";  bold   = "$ESC[1m"
    red     = "$ESC[31m"; green  = "$ESC[32m"; yellow = "$ESC[33m"
    blue    = "$ESC[34m"; magenta= "$ESC[35m"; cyan   = "$ESC[36m"
    inverse = "$ESC[7m"
}

function Show-Banner {
    $logo = @(
        " ██████╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗",
        "██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝",
        "██║     ██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝ ",
        "██║     ██║   ██║██╔══██╗   ██║   ██╔══╝   ██╔██╗ ",
        "╚██████╗╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗",
        " ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝"
    )
    Write-Host ""
    foreach ($line in $logo) { Write-Host "$($C.cyan)$($C.bold)$line$($C.reset)" }
    Write-Host "$($C.dim)        knowledge-graph memory for your codebase$($C.reset)"
    Write-Host ""
}

$script:StepNo = 0
$script:StepTotal = 6
function Write-Step($label) {
    $script:StepNo++
    $n = "[$($script:StepNo)/$($script:StepTotal)]"
    Write-Host ""
    Write-Host "$($C.magenta)$($C.bold)$n$($C.reset) $($C.bold)$label$($C.reset)"
    Write-Host "$($C.dim)──────────────────────────────────────────────────$($C.reset)"
}

function Write-Ok($msg)   { Write-Host "  $($C.green)✓$($C.reset) $msg" }
function Write-Warn($msg)  { Write-Host "  $($C.yellow)!$($C.reset) $msg" }
function Write-Info($msg)  { Write-Host "  $($C.cyan)→$($C.reset) $msg" }
function Write-Skip($msg)  { Write-Host "  $($C.dim)·  $msg$($C.reset)" }
function Write-Fail($msg)  { Write-Host "  $($C.red)✗$($C.reset) $msg"; exit 1 }

# Run a scriptblock asynchronously while animating a \ | / - spinner.
# The block should `throw` on failure. Returns $true on success.
function Invoke-Spinner {
    param(
        [string]$Label,
        [scriptblock]$Block,
        [hashtable]$Params = @{}
    )
    $ps = [powershell]::Create()
    [void]$ps.AddScript($Block.ToString())
    foreach ($k in $Params.Keys) { [void]$ps.AddParameter($k, $Params[$k]) }
    $async = $ps.BeginInvoke()

    $frames = @('\', '|', '/', '-')
    $i = 0
    while (-not $async.IsCompleted) {
        $f = $frames[$i % $frames.Count]
        Write-Host -NoNewline "`r  $($C.cyan)$f$($C.reset) $Label   "
        Start-Sleep -Milliseconds 90
        $i++
    }

    $errText = ""
    try { $ps.EndInvoke($async) | Out-Null }
    catch { $errText = $_.Exception.Message }
    if ($ps.HadErrors -and -not $errText) {
        $errText = ($ps.Streams.Error | ForEach-Object { $_.ToString() }) -join "`n"
    }
    $ps.Dispose()

    $pad = ' ' * 12
    if ($errText) {
        Write-Host "`r  $($C.red)✗$($C.reset) $Label$pad"
        $indented = ($errText -split "`n" | ForEach-Object { "      $($C.dim)$_$($C.reset)" }) -join "`n"
        Write-Host $indented
        return $false
    }
    Write-Host "`r  $($C.green)✓$($C.reset) $Label$pad"
    return $true
}

# Interactive checkbox menu. $Items is an array of hashtables with keys:
#   Key, Label, Hint, Checked  (Checked is mutated in place)
# Returns nothing; read .Checked off the items afterwards.
function Show-Multiselect {
    param([array]$Items)

    $count = $Items.Count
    $cur = 0

    function Format-Row($item, $isCur) {
        $glyph = if ($item.Checked) { "$($C.green)◈$($C.reset)" } else { "$($C.dim)◇$($C.reset)" }
        $pointer = if ($isCur) { "$($C.cyan)›$($C.reset)" } else { " " }
        $label = if ($isCur) { "$($C.cyan)$($C.bold)$($item.Label)$($C.reset)" } else { $item.Label }
        $hint = if ($item.Hint) { " $($C.dim)$($item.Hint)$($C.reset)" } else { "" }
        return " $pointer $glyph  $label$hint"
    }

    Write-Host ""
    Write-Host "  $($C.dim)↑/↓ move · Space toggle · a all · n none · Enter confirm$($C.reset)"
    foreach ($i in 0..($count - 1)) {
        Write-Host (Format-Row $Items[$i] ($i -eq $cur))
    }

    try { [Console]::CursorVisible = $false } catch {}
    $done = $false
    while (-not $done) {
        $key = [Console]::ReadKey($true)
        switch ($key.Key) {
            'UpArrow'   { $cur = ($cur - 1 + $count) % $count }
            'DownArrow' { $cur = ($cur + 1) % $count }
            'Spacebar'  { $Items[$cur].Checked = -not $Items[$cur].Checked }
            'Enter'     { $done = $true }
            default {
                switch ("$($key.KeyChar)".ToLower()) {
                    'a' { foreach ($it in $Items) { $it.Checked = $true } }
                    'n' { foreach ($it in $Items) { $it.Checked = $false } }
                    ' ' { $Items[$cur].Checked = -not $Items[$cur].Checked }
                }
            }
        }
        # Redraw: move cursor up over the item rows and rewrite each.
        Write-Host -NoNewline "$ESC[${count}A"
        foreach ($i in 0..($count - 1)) {
            Write-Host "$ESC[2K$(Format-Row $Items[$i] ($i -eq $cur))"
        }
    }
    try { [Console]::CursorVisible = $true } catch {}
}

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

function Check-Git {
    try { $v = (git --version) } catch { Write-Fail "git not found. Install from https://git-scm.com and retry." }
    Write-Ok "git ready  $($C.dim)($v)$($C.reset)"
}

function Check-Python {
    foreach ($cmd in @("python", "py")) {
        try {
            $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($ver) {
                $parts = $ver.Trim().Split(".")
                if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 11)) {
                    $script:PYTHON_CMD = $cmd
                    Write-Ok "Python $ver  $($C.dim)($cmd)$($C.reset)"
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
        $ok = Invoke-Spinner "Updating existing repository" {
            param($dir)
            git -C $dir pull --ff-only 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "git pull failed in $dir" }
        } @{ dir = $INSTALL_DIR }
    } else {
        $ok = Invoke-Spinner "Cloning cortex into ~/.cortex/cortex" {
            param($url, $dir)
            git clone --depth 1 $url $dir 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
        } @{ url = $REPO_URL; dir = $INSTALL_DIR }
    }
    if (-not $ok) { Write-Fail "Could not prepare the Cortex repository at $INSTALL_DIR" }
}

# ---------------------------------------------------------------------------
# Venv + install
# ---------------------------------------------------------------------------

function Setup-Venv {
    $script:VENV_PYTHON = Join-Path $INSTALL_DIR ".venv\Scripts\python.exe"
    $script:VENV_CORTEX = Join-Path $INSTALL_DIR ".venv\Scripts\cortex.exe"

    $ok = Invoke-Spinner "Creating virtual environment" {
        param($py, $dir)
        & $py -m venv --without-pip "$dir\.venv" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
        & "$dir\.venv\Scripts\python.exe" -m ensurepip --upgrade --default-pip 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "ensurepip failed" }
    } @{ py = $script:PYTHON_CMD; dir = $INSTALL_DIR }
    if (-not $ok) { Write-Fail "Could not create virtual environment" }

    $ok = Invoke-Spinner "Installing Cortex and dependencies (this can take a minute)" {
        param($py, $dir)
        & $py -m pip install --quiet --upgrade pip 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
        & $py -m pip install --quiet -e "$dir\" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    } @{ py = $script:VENV_PYTHON; dir = $INSTALL_DIR }
    if (-not $ok) { Write-Fail "Could not install Cortex dependencies" }
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
        IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam,
        uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
}
'@
        Add-Type -TypeDefinition $signature -ErrorAction SilentlyContinue
        $result = [UIntPtr]::Zero
        [CortexNativeMethods]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, "Environment", 0x0002, 5000, [ref]$result) | Out-Null
    } catch {
        Write-Warn "PATH was updated, but Windows notification failed. Open a new terminal if needed."
    }
}

function Add-ToPath {
    $venvScripts = Join-Path $INSTALL_DIR ".venv\Scripts"
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if (-not $userPath) { $userPath = "" }

    $userPathItems = $userPath -split ";" | Where-Object { $_ }
    if ($userPathItems -contains $venvScripts) {
        Write-Ok "PATH already contains the cortex CLI"
    } else {
        if ([string]::IsNullOrWhiteSpace($userPath)) {
            $newUserPath = $venvScripts
        } else {
            $newUserPath = "$userPath;$venvScripts"
        }
        [Environment]::SetEnvironmentVariable("PATH", $newUserPath, "User")
        Write-Ok "Added cortex CLI to your user PATH"
        Notify-PathChanged
    }

    $processPathItems = $env:PATH -split ";" | Where-Object { $_ }
    if ($processPathItems -notcontains $venvScripts) {
        $env:PATH = "$venvScripts;$env:PATH"
    }
}

# ---------------------------------------------------------------------------
# Per-tool integration
# ---------------------------------------------------------------------------

# Merge the cortex MCP server entry into a JSON config file (preserving the rest).
function Write-JsonMcpConfig($configFile) {
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
        os.rename(path, path + ".bak")
config.setdefault("mcpServers", {})["cortex"] = {"command": cortex_bin, "args": ["mcp"]}
with open(path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
'@
    $tmpScript = [System.IO.Path]::GetTempFileName() + ".py"
    $pyScript | Out-File -FilePath $tmpScript -Encoding utf8
    try {
        & $script:VENV_PYTHON $tmpScript $configFile $script:VENV_CORTEX 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "writing $configFile failed" }
    } finally {
        Remove-Item $tmpScript -ErrorAction SilentlyContinue
    }
}

# Supported tools. Each: Key, Label, Dir, McpFile, plus install flags.
function Get-ToolRegistry {
    @(
        @{ Key="claude"; Label="Claude Code"; Dir="$env:USERPROFILE\.claude"; McpFile="settings.json"; Skill=$true;  Agents=$false }
        @{ Key="cursor"; Label="Cursor";      Dir="$env:USERPROFILE\.cursor"; McpFile="mcp.json";      Skill=$false; Agents=$true  }
        @{ Key="gemini"; Label="Gemini CLI";  Dir="$env:USERPROFILE\.gemini"; McpFile="settings.json"; Skill=$false; Agents=$true  }
        @{ Key="codex";  Label="Codex CLI";   Dir="$env:USERPROFILE\.codex";  McpFile="config.json";   Skill=$false; Agents=$true  }
    )
}

function Install-Tool($tool) {
    Write-Host ""
    Write-Host "  $($C.bold)$($tool.Label)$($C.reset)"
    New-Item -ItemType Directory -Force -Path $tool.Dir | Out-Null

    $mcpPath = Join-Path $tool.Dir $tool.McpFile
    try {
        Write-JsonMcpConfig $mcpPath
        Write-Ok "MCP server  $($C.dim)$mcpPath$($C.reset)"
    } catch {
        Write-Warn "MCP config failed: $($_.Exception.Message)"
    }

    if ($tool.Skill) {
        $skillDir = Join-Path $tool.Dir "skills\cortex"
        New-Item -ItemType Directory -Force -Path $skillDir | Out-Null
        Copy-Item (Join-Path $INSTALL_DIR "SKILL.md") (Join-Path $skillDir "SKILL.md") -Force
        Write-Ok "Skill       $($C.dim)$skillDir\SKILL.md$($C.reset)"
    }

    if ($tool.Agents) {
        $agentsDst = Join-Path $tool.Dir "AGENTS.md"
        Copy-Item (Join-Path $INSTALL_DIR "AGENTS.md") $agentsDst -Force
        Write-Ok "Instructions $($C.dim)$agentsDst$($C.reset)"
    }

    $script:InstalledTools += $tool.Label
}

# Decide which tools to install: interactive menu, or non-interactive fallback.
function Select-Tools {
    $registry = Get-ToolRegistry
    foreach ($t in $registry) { $t.Detected = Test-Path $t.Dir }

    # Explicit --Tools list wins and skips the menu.
    if ($Tools) {
        $want = $Tools.ToLower().Split(",") | ForEach-Object { $_.Trim() }
        foreach ($t in $registry) { $t.Checked = $want -contains $t.Key }
        return ($registry | Where-Object { $t = $_; $t.Checked })
    }

    $interactive = -not $Yes -and -not [Console]::IsInputRedirected -and [Environment]::UserInteractive
    foreach ($t in $registry) { $t.Checked = [bool]$t.Detected }

    if ($interactive) {
        $items = $registry | ForEach-Object {
            @{ Key=$_.Key; Label=$_.Label; Checked=$_.Checked
               Hint = if ($_.Detected) { "(detected)" } else { "(not found)" } }
        }
        try {
            Show-Multiselect $items
            for ($i = 0; $i -lt $registry.Count; $i++) { $registry[$i].Checked = $items[$i].Checked }
        } catch {
            Write-Warn "Interactive menu unavailable — using detected tools."
        }
    } else {
        Write-Info "Non-interactive: installing into detected tools."
    }

    return ($registry | Where-Object { $_.Checked })
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

function Print-Summary {
    Write-Host ""
    Write-Host "$($C.green)╭────────────────────────────────────────────────╮$($C.reset)"
    Write-Host "$($C.green)│$($C.reset)  $($C.bold)Cortex is installed.$($C.reset)                          $($C.green)│$($C.reset)"
    Write-Host "$($C.green)╰────────────────────────────────────────────────╯$($C.reset)"
    Write-Host ""
    Write-Ok "Location: $($C.dim)$INSTALL_DIR$($C.reset)"
    Write-Host ""

    if ($script:InstalledTools.Count -gt 0) {
        Write-Host "  $($C.bold)Configured tools:$($C.reset)"
        foreach ($t in $script:InstalledTools) { Write-Host "    $($C.green)✓$($C.reset) $t" }
    } else {
        Write-Warn "No AI tools selected. Add this to a tool's MCP config manually:"
        Write-Host "    $($C.dim)`"cortex`": { `"command`": `"$($script:VENV_CORTEX)`", `"args`": [`"mcp`"] }$($C.reset)"
    }

    Write-Host ""
    Write-Host "  $($C.bold)Usage$($C.reset) $($C.dim)(from any project directory)$($C.reset)"
    Write-Host "    $($C.cyan)cortex init$($C.reset)   Initialize the knowledge graph for this project"
    Write-Host "    $($C.cyan)cortex run$($C.reset)    Start the web UI  $($C.dim)→  http://localhost:7842$($C.reset)"
    Write-Host ""
    Write-Host "  $($C.yellow)!$($C.reset) Open a new terminal for $($C.cyan)cortex$($C.reset) to be on your PATH."
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

$script:PYTHON_CMD      = ""
$script:VENV_PYTHON     = ""
$script:VENV_CORTEX     = ""
$script:InstalledTools  = @()

Enable-Ansi
Show-Banner

Write-Step "Checking prerequisites"
Check-Git
Check-Python

Write-Step "Fetching Cortex"
Clone-Repo

Write-Step "Setting up the Python environment"
Setup-Venv

Write-Step "Adding the cortex CLI to PATH"
Add-ToPath

Write-Step "Choose AI tools to install Cortex into"
$selected = @(Select-Tools)

Write-Step "Installing Cortex into your tools"
if ($selected.Count -eq 0) {
    Write-Skip "No tools selected — skipping."
} else {
    foreach ($tool in $selected) { Install-Tool $tool }
}

Print-Summary
