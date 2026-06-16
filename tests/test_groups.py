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


def test_group_node_table_exists(mgr):
    mgr.conn.execute(
        "CREATE (g:NodeGroup {id: 'g1', name: 'AuthCluster', description: 'Auth subsystem', section: 'Auth'})"
    )
    rows = mgr.query_to_dicts("MATCH (g:NodeGroup {id: 'g1'}) RETURN g.name AS name")
    assert rows[0]["name"] == "AuthCluster"


def test_member_of_relationship(mgr):
    mgr.conn.execute(
        "CREATE (g:NodeGroup {id: 'g1', name: 'AuthCluster', description: '', section: 'Auth'})"
    )
    mgr.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth.py', description: '', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "MATCH (f:File {id: 'f1'}), (g:NodeGroup {id: 'g1'}) CREATE (f)-[:MEMBER_OF]->(g)"
    )
    rows = mgr.query_to_dicts(
        "MATCH (f:File)-[:MEMBER_OF]->(g:NodeGroup {id: 'g1'}) RETURN f.id AS fid"
    )
    assert rows[0]["fid"] == "f1"


def test_write_group_node_creates_group(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_group_node(
        id="Group:Auth",
        name="Auth",
        description="Authentication subsystem",
        section="Auth",
        member_ids="[]",
    )
    assert "Group:Auth" in result
    assert "Error" not in result
    srv._mgr = None


def test_write_group_node_warns_on_missing_member(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_group_node(
        id="Group:Auth2",
        name="Auth2",
        description="",
        section="Auth",
        member_ids='["nonexistent:node"]',
    )
    assert "not found" in result.lower() or "Warning" in result
    srv._mgr = None
