# Cortex v2 — Phase 5: CLI & Hooks (Anchored Commits)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `cortex hook install/uninstall/status` subcommand that installs a git post-commit hook. The hook calls `cortex snapshot` (a new internal subcommand) to create an Anchored Commit — a graph snapshot tagged with the git commit message and SHA.

**Architecture:** `cortex hook install` writes `.git/hooks/post-commit` (a POSIX sh script that works cross-platform via Git Bash on Windows). `cortex snapshot` is an internal subcommand added to `cortex/main.py` — not shown in `--help`. `commit_snapshot` in `core/db.py` gains an optional `git_sha` parameter so the SHA appears in the snapshot message.

**Tech Stack:** Python 3.11+ stdlib, POSIX sh (git hook script). No new dependencies.

**Prerequisites:** Phase 1 complete (trail.jsonl reminder already shown). Phase 2/3/4 complete (all analysis/export commands in place).

---

## Task 1: cortex hook subcommand

**Files:**
- Modify: `cortex/main.py` — add `hook` subcommand with `install`, `uninstall`, `status` sub-subcommands
- Create: `tests/test_hooks.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hooks.py`:

```python
import pytest
import subprocess
import sys
from pathlib import Path


@pytest.fixture
def fake_git_repo(tmp_path):
    """Create a minimal git repo in tmp_path."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hooks").mkdir()
    return tmp_path


def _run(args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "cortex.main"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_hook_install_creates_post_commit(fake_git_repo):
    result = _run(["hook", "install", "--root", str(fake_git_repo)])
    assert result.returncode == 0
    hook_path = fake_git_repo / ".git" / "hooks" / "post-commit"
    assert hook_path.exists()
    content = hook_path.read_text()
    assert "cortex snapshot" in content


def test_hook_install_is_executable(fake_git_repo):
    _run(["hook", "install", "--root", str(fake_git_repo)])
    hook_path = fake_git_repo / ".git" / "hooks" / "post-commit"
    import stat
    mode = hook_path.stat().st_mode
    assert mode & stat.S_IXUSR  # owner execute bit


def test_hook_status_shows_installed(fake_git_repo):
    _run(["hook", "install", "--root", str(fake_git_repo)])
    result = _run(["hook", "status", "--root", str(fake_git_repo)])
    assert result.returncode == 0
    assert "installed" in result.stdout.lower()


def test_hook_status_shows_not_installed(fake_git_repo):
    result = _run(["hook", "status", "--root", str(fake_git_repo)])
    assert "not installed" in result.stdout.lower()


def test_hook_uninstall_removes_hook(fake_git_repo):
    _run(["hook", "install", "--root", str(fake_git_repo)])
    result = _run(["hook", "uninstall", "--root", str(fake_git_repo)])
    assert result.returncode == 0
    hook_path = fake_git_repo / ".git" / "hooks" / "post-commit"
    assert not hook_path.exists()


def test_hook_uninstall_no_op_when_not_installed(fake_git_repo):
    result = _run(["hook", "uninstall", "--root", str(fake_git_repo)])
    assert result.returncode == 0
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_hooks.py -v
```
Expected: FAIL — `cortex.main` doesn't have a `hook` subcommand yet.

- [ ] **Step 3: Add hook subcommand to cortex/main.py**

Add the hook parser to `main()`:

```python
    # ── hook ─────────────────────────────────────────────────────────────────
    p_hook = sub.add_parser("hook", help="Manage the Cortex git post-commit hook")
    hook_sub = p_hook.add_subparsers(dest="hook_action", metavar="<action>")
    hook_sub.required = True

    p_hook_install = hook_sub.add_parser("install", help="Install the post-commit hook")
    p_hook_install.add_argument("--root", default=".", metavar="DIR")

    p_hook_uninstall = hook_sub.add_parser("uninstall", help="Remove the post-commit hook")
    p_hook_uninstall.add_argument("--root", default=".", metavar="DIR")

    p_hook_status = hook_sub.add_parser("status", help="Show hook installation status")
    p_hook_status.add_argument("--root", default=".", metavar="DIR")
```

Add dispatch:
```python
    elif args.command == "hook":
        _cmd_hook(args)
```

Add `_HOOK_MARKER`:
```python
_HOOK_MARKER = "# cortex-hook"

_HOOK_SCRIPT = """\
#!/bin/sh
# cortex-hook — managed by 'cortex hook install'. Do not edit this line.
CORTEX_ROOT="$(git rev-parse --show-toplevel)"
MSG="$(git log -1 --pretty=%s 2>/dev/null || echo 'git commit')"
SHA="$(git log -1 --pretty=%H 2>/dev/null || echo '')"
cortex snapshot --message "$MSG" --sha "$SHA" --root "$CORTEX_ROOT" 2>/dev/null || true
"""
```

Add `_cmd_hook`:
```python
def _cmd_hook(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    git_dir = root / ".git"

    if not git_dir.is_dir():
        # Try to find .git by walking up
        candidate = root
        while candidate != candidate.parent:
            candidate = candidate.parent
            if (candidate / ".git").is_dir():
                git_dir = candidate / ".git"
                break
        else:
            print("error: not a git repository", file=sys.stderr)
            sys.exit(1)

    hooks_dir = git_dir / "hooks"
    hook_path = hooks_dir / "post-commit"

    if args.hook_action == "install":
        hooks_dir.mkdir(exist_ok=True)
        hook_path.write_text(_HOOK_SCRIPT, encoding="utf-8")
        import stat
        current = hook_path.stat().st_mode
        hook_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"[Cortex] Hook installed at {hook_path}")
        print("  Every git commit will now auto-snapshot the graph.")

    elif args.hook_action == "uninstall":
        if hook_path.exists() and _HOOK_MARKER in hook_path.read_text():
            hook_path.unlink()
            print(f"[Cortex] Hook removed from {hook_path}")
        elif hook_path.exists():
            print(f"[Cortex] Hook at {hook_path} was not installed by Cortex — leaving it alone.")
        else:
            print("[Cortex] No Cortex hook found — nothing to remove.")

    elif args.hook_action == "status":
        if hook_path.exists() and _HOOK_MARKER in hook_path.read_text():
            print(f"[Cortex] Hook status: installed at {hook_path}")
        elif hook_path.exists():
            print(f"[Cortex] Hook status: {hook_path} exists but was not installed by Cortex.")
        else:
            print("[Cortex] Hook status: not installed. Run 'cortex hook install' to enable.")
```

- [ ] **Step 4: Run hook tests**

```bash
pytest tests/test_hooks.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add cortex/main.py tests/test_hooks.py
git commit -m "feat(cli): cortex hook install/uninstall/status — Anchored Commits git hook"
```

---

## Task 2: cortex snapshot internal subcommand

**Files:**
- Modify: `cortex/main.py` — add `snapshot` subcommand (not shown in `--help`)
- Modify: `core/db.py` — extend `commit_snapshot` with optional `git_sha` parameter
- Modify: `tests/test_hooks.py` — add snapshot tests

The `cortex snapshot` subcommand is called by the post-commit hook. It creates a graph snapshot with the commit message and optionally tags it with the git SHA.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hooks.py`:

```python
def test_snapshot_subcommand_creates_snapshot(tmp_path):
    """cortex snapshot should write a graph snapshot."""
    from core.db import DatabaseManager
    mgr = DatabaseManager(tmp_path)
    mgr.init()
    mgr.close()

    result = _run(
        ["snapshot", "--message", "test commit", "--sha", "abc1234", "--root", str(tmp_path)]
    )
    assert result.returncode == 0
    assert "Snapshot" in result.stdout

    mgr2 = DatabaseManager(tmp_path)
    mgr2.init()
    timeline = mgr2.get_timeline()
    mgr2.close()

    messages = [v["message"] for v in timeline]
    assert any("test commit" in m for m in messages)


def test_snapshot_message_includes_sha(tmp_path):
    from core.db import DatabaseManager
    mgr = DatabaseManager(tmp_path)
    mgr.init()
    mgr.close()

    _run(["snapshot", "--message", "feat: add auth", "--sha", "deadbeef", "--root", str(tmp_path)])

    mgr2 = DatabaseManager(tmp_path)
    mgr2.init()
    timeline = mgr2.get_timeline()
    mgr2.close()

    messages = [v["message"] for v in timeline]
    assert any("deadbeef" in m for m in messages)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_hooks.py::test_snapshot_subcommand_creates_snapshot -v
```
Expected: FAIL — `cortex.main` has no `snapshot` subcommand.

- [ ] **Step 3: Add snapshot subcommand to cortex/main.py**

Add after the `hook` parser (note: `add_help=False` hides it from `cortex --help`):

```python
    # ── snapshot (internal — called by git hook) ─────────────────────────────
    p_snap = sub.add_parser("snapshot", add_help=False)
    p_snap.add_argument("--message", default="Git commit snapshot")
    p_snap.add_argument("--sha", default="")
    p_snap.add_argument("--root", default=".")
```

Add dispatch:
```python
    elif args.command == "snapshot":
        _cmd_snapshot(args)
```

Add function:
```python
def _cmd_snapshot(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    from core.db import DatabaseManager
    mgr = DatabaseManager(root)
    mgr.init()
    message = args.message or "Git commit snapshot"
    if args.sha:
        message = f"{message} ({args.sha[:7]})"
    entry = mgr.commit_snapshot(message)
    mgr.close()
    print(f"[Cortex] Snapshot: slot={entry['slot']} ts={entry['timestamp']}")
```

- [ ] **Step 4: Run snapshot tests**

```bash
pytest tests/test_hooks.py -v
```
Expected: All 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add cortex/main.py tests/test_hooks.py
git commit -m "feat(cli): cortex snapshot internal subcommand for Anchored Commits git hook"
```

---

## Task 3: End-to-End Hook Test

**Files:**
- Modify: `tests/test_hooks.py` — add integration test with real git commit

This test initialises a real git repo, installs the hook, makes a commit, and verifies the snapshot appears in the timeline.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hooks.py`:

```python
def test_hook_fires_on_git_commit(tmp_path):
    """Integration: install hook, make a commit, verify snapshot was created."""
    import subprocess

    # Init git repo and cortex
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=tmp_path, check=True, capture_output=True)

    result = _run(["init", "--root", str(tmp_path)])
    assert result.returncode == 0

    result = _run(["hook", "install", "--root", str(tmp_path)])
    assert result.returncode == 0

    # Make a commit
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "test: integration commit"],
                   cwd=tmp_path, check=True, capture_output=True)

    # Check that a snapshot was created beyond the genesis one
    from core.db import DatabaseManager
    mgr = DatabaseManager(tmp_path)
    mgr.init()
    timeline = mgr.get_timeline()
    mgr.close()

    assert len(timeline) >= 2  # genesis + hook snapshot
    messages = [v["message"] for v in timeline]
    assert any("integration commit" in m for m in messages)
```

- [ ] **Step 2: Run — this test requires git on PATH**

```bash
pytest tests/test_hooks.py::test_hook_fires_on_git_commit -v -s
```
Expected: PASS if `git` is on PATH and `cortex` binary is available. If `cortex` binary isn't on PATH during the test (e.g., dev environment), the hook runs `cortex` which may fail silently — `|| true` in the hook script ensures the git commit still succeeds.

If the test fails because `cortex` is not on PATH in the test subprocess, mark it as integration-only:
```python
@pytest.mark.skipif(
    not __import__("shutil").which("cortex"),
    reason="cortex binary not on PATH"
)
def test_hook_fires_on_git_commit(tmp_path):
    ...
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: All tests PASS (or the integration test is skipped if cortex not on PATH).

- [ ] **Step 4: Commit**

```bash
git add tests/test_hooks.py
git commit -m "test(hooks): end-to-end Anchored Commits hook integration test"
```

---

## Task 4: Update README with v2 Commands

**Files:**
- Modify: `README.md` — add new commands and features overview

- [ ] **Step 1: Update README.md usage section**

Find the existing usage section in `README.md` and expand it:

```markdown
## Usage

### Initialize a project
```bash
cortex init
```

### Start the web UI
```bash
cortex run              # http://localhost:7842
cortex run --port 8000  # custom port
```

### MCP server (for AI tools)
```bash
cortex mcp              # stdio transport (used by AI tool configs)
cortex mcp --sse        # SSE transport (for debugging)
```

### Install Cortex into AI tool MCP configs
```bash
cortex connect          # interactive checkbox installer
```

### Enable automatic git snapshots
```bash
cortex hook install     # installs post-commit hook
cortex hook status      # check if hook is active
cortex hook uninstall   # remove the hook
```

### Push graph to an external graph database
```bash
cortex relay neo4j --cypher-only          # preview Cypher
cortex relay neo4j --uri bolt://localhost:7687 --password secret
cortex relay falkordb --host localhost --port 6379
```

### Export the graph
```bash
# Via the web UI: click Export → choose format
# Via REST API:
curl -s -X POST http://localhost:7842/api/export \
  -H 'Content-Type: application/json' \
  -d '{"format": "graphml"}' > graph.xml
```

### Analysis extras (Signal Clusters require leidenalg)
```bash
pip install cortex[analysis]   # Leiden algorithm
pip install cortex[neo4j]      # Neo4j relay
pip install cortex[falkordb]   # FalkorDB relay
```
```

- [ ] **Step 2: Commit README**

```bash
git add README.md
git commit -m "docs: update README with v2 CLI commands (hook, connect, relay, snapshot)"
```

---

## Task 5: Final Integration Smoke Test

- [ ] **Step 1: Run the full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tee test-results.txt
```

Verify:
- All unit tests pass
- Integration test (`test_hook_fires_on_git_commit`) passes or is appropriately skipped
- No import errors

- [ ] **Step 2: Start the web server and verify key endpoints**

```bash
cortex init --root .
cortex run &
sleep 2

curl -s http://localhost:7842/api/graph | python -m json.tool | head -5
curl -s http://localhost:7842/api/keystones | python -m json.tool
curl -s http://localhost:7842/api/brief | python -m json.tool
curl -s -X POST http://localhost:7842/api/export -H 'Content-Type: application/json' \
  -d '{"format": "graphml"}' | head -5

kill %1
```
Expected: each returns valid data without server errors.

- [ ] **Step 3: Verify MCP tools load correctly**

```bash
python -c "
import cortex.mcp_server as srv
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory() as d:
    srv.PROJECT_ROOT = Path(d)
    srv._mgr = None
    tools = [t.name for t in srv.mcp._tool_manager._tools.values()]
    expected = [
        'get_graph_timeline', 'query_graph_diff', 'explore_neighborhood',
        'find_structural_path', 'write_system_design_node', 'write_agent_instructions',
        'list_design_sections', 'write_group_node', 'get_session_trail',
        'detect_signal_clusters_tool', 'get_keystones_tool',
        'get_latent_bridges_tool', 'get_cortex_brief',
    ]
    for t in expected:
        assert t in tools, f'Missing tool: {t}'
    print(f'All {len(expected)} MCP tools registered.')
"
```
Expected: prints "All 13 MCP tools registered."

- [ ] **Step 4: Create final release commit**

```bash
git add -u
git status  # verify nothing unexpected
git commit -m "feat: Cortex v2 complete — all 5 phases implemented and tested"
```

---

## Summary of All New CLI Commands

| Command | Description |
|---------|-------------|
| `cortex init` | Initialize graph DB + migrate Decision Arc status |
| `cortex run` | Start web UI |
| `cortex mcp` | Start MCP server (stdio/SSE) |
| `cortex hook install` | Install post-commit hook |
| `cortex hook uninstall` | Remove post-commit hook |
| `cortex hook status` | Show hook status |
| `cortex connect` | Interactive MCP config installer |
| `cortex relay neo4j` | Push graph to Neo4j |
| `cortex relay falkordb` | Push graph to FalkorDB |
| `cortex snapshot` | (internal) Create graph snapshot from git hook |

## Summary of All New MCP Tools

| Tool | Description |
|------|-------------|
| `write_group_node` | Create/update a Group with members |
| `get_session_trail` | Show recent tool invocations |
| `detect_signal_clusters_tool` | Run community detection |
| `get_keystones_tool` | Top nodes by degree |
| `get_latent_bridges_tool` | Cross-cluster edges |
| `get_cortex_brief` | Markdown project summary |

Phase 5 complete. Cortex v2 is fully implemented.
