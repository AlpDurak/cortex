import json
import sys
import pytest
from pathlib import Path
import cortex.mcp_server as srv


def _reset(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    srv._session_id = None
    srv._hook_reminder_shown = False


def test_trail_file_created_after_tool_call(tmp_path):
    _reset(tmp_path)
    srv.get_graph_timeline()
    trail_path = tmp_path / ".cortex" / "trail.jsonl"
    assert trail_path.exists()
    entries = [json.loads(l) for l in trail_path.read_text().splitlines() if l.strip()]
    assert entries[0]["tool"] == "get_graph_timeline"
    assert "ts" in entries[0]
    assert "session" in entries[0]
    _reset(tmp_path)


def test_trail_accumulates(tmp_path):
    _reset(tmp_path)
    srv.get_graph_timeline()
    srv.list_design_sections()
    trail_path = tmp_path / ".cortex" / "trail.jsonl"
    entries = [json.loads(l) for l in trail_path.read_text().splitlines() if l.strip()]
    tools = [e["tool"] for e in entries]
    assert "get_graph_timeline" in tools
    assert "list_design_sections" in tools
    _reset(tmp_path)


def test_get_session_trail_tool(tmp_path):
    _reset(tmp_path)
    srv.get_graph_timeline()
    result = srv.get_session_trail()
    assert "get_graph_timeline" in result
    _reset(tmp_path)


def test_hook_reminder_on_first_call(tmp_path, capsys):
    _reset(tmp_path)
    srv.get_graph_timeline()
    captured = capsys.readouterr()
    assert "cortex hook install" in captured.err
    _reset(tmp_path)


def test_hook_reminder_only_once(tmp_path, capsys):
    _reset(tmp_path)
    srv.get_graph_timeline()
    capsys.readouterr()
    srv.list_design_sections()
    captured = capsys.readouterr()
    assert "cortex hook install" not in captured.err
    _reset(tmp_path)
