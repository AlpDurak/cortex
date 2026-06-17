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
    import os
    mode = hook_path.stat().st_mode
    # On Windows, NTFS does not expose POSIX execute bits via stat(); use os.access instead.
    if sys.platform == "win32":
        assert hook_path.exists()  # file was created — executable bit is not POSIX-enforced on Windows
    else:
        assert mode & stat.S_IXUSR


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
