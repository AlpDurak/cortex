import pytest
from pathlib import Path
from core.db import DatabaseManager
import cortex.mcp_server as srv


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    yield m
    m.close()


def test_proposed_accepted(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:B", name="B", section="A", description="desc", status="proposed"
    )
    assert "Error" not in result
    srv._mgr = None


def test_building_accepted(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:C", name="C", section="A", description="desc", status="building"
    )
    assert "Error" not in result
    srv._mgr = None


def test_shipped_accepted(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:D", name="D", section="A", description="desc", status="shipped"
    )
    assert "Error" not in result
    srv._mgr = None


def test_planned_rejected(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:E", name="E", section="A", description="desc", status="planned"
    )
    assert "Error" in result
    srv._mgr = None


def test_migrate_renames_old_statuses(mgr):
    for old in ("planned", "in-progress", "done", "in_progress"):
        mgr.conn.execute(
            f"CREATE (n:SystemDesign {{id: 'sd:{old}', name: '{old}', description: '', "
            f"code_block: '', design_type: 'task', status: '{old}', section: '', "
            f"rationale: '', source_file: '', source_line: 0}})"
        )
    mgr.migrate_decision_arc_status()
    rows = mgr.query_to_dicts(
        "MATCH (n:SystemDesign) RETURN n.id AS id, n.status AS status"
    )
    by_id = {r["id"]: r["status"] for r in rows}
    assert by_id["sd:planned"] == "proposed"
    assert by_id["sd:in-progress"] == "building"
    assert by_id["sd:done"] == "shipped"
    assert by_id["sd:in_progress"] == "building"
