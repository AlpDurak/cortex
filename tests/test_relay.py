import pytest
from pathlib import Path
from core.db import DatabaseManager


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    m.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth.py', description: 'auth', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    yield m
    m.close()


def test_relay_neo4j_returns_cypher_only(mgr):
    from core.relay import relay_neo4j
    cypher_lines = relay_neo4j(mgr.conn, uri="bolt://localhost:7687", cypher_only=True)
    assert isinstance(cypher_lines, list)
    assert len(cypher_lines) >= 1
    assert any("MERGE" in line for line in cypher_lines)


def test_relay_falkordb_returns_cypher_only(mgr):
    from core.relay import relay_falkordb
    cypher_lines = relay_falkordb(mgr.conn, host="localhost", port=6379, cypher_only=True)
    assert isinstance(cypher_lines, list)
    assert any("MERGE" in line for line in cypher_lines)
