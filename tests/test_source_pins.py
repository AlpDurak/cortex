import pytest
from pathlib import Path
from core.db import DatabaseManager


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    yield m
    m.close()


def test_file_node_has_source_pins(mgr):
    mgr.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'a.py', description: '', "
        "code_block: '', file_path: 'a.py', language: 'python', "
        "source_file: 'a.py', source_line: 10})"
    )
    rows = mgr.query_to_dicts(
        "MATCH (n:File {id: 'f1'}) RETURN n.source_file AS sf, n.source_line AS sl"
    )
    assert rows[0]["sf"] == "a.py"
    assert rows[0]["sl"] == 10


def test_system_design_has_source_pins(mgr):
    mgr.conn.execute(
        "CREATE (n:SystemDesign {id: 'sd1', name: 'A', description: '', "
        "code_block: '', design_type: 'task', status: 'proposed', "
        "section: 'Auth', rationale: '', source_file: 'design.md', source_line: 5})"
    )
    rows = mgr.query_to_dicts(
        "MATCH (n:SystemDesign {id: 'sd1'}) RETURN n.source_file AS sf, n.source_line AS sl"
    )
    assert rows[0]["sf"] == "design.md"
    assert rows[0]["sl"] == 5


def test_service_node_has_source_pins(mgr):
    mgr.conn.execute(
        "CREATE (n:Service {id: 'sv1', name: 'Stripe', description: '', "
        "code_block: '', service_type: 'third_party', endpoint: 'https://api.stripe.com', "
        "source_file: '', source_line: 0})"
    )
    rows = mgr.query_to_dicts(
        "MATCH (n:Service {id: 'sv1'}) RETURN n.source_file AS sf, n.source_line AS sl"
    )
    assert rows[0]["sf"] == ""
    assert rows[0]["sl"] == 0
