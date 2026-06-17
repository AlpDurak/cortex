import pytest
from pathlib import Path
from core.db import DatabaseManager
from core.export import export_graphml, export_obsidian, export_wiki


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    m.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth.py', description: 'auth module', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    m.conn.execute(
        "CREATE (n:SystemDesign {id: 'sd1', name: 'OAuthFlow', description: 'OAuth impl', "
        "code_block: '', design_type: 'task', status: 'proposed', section: 'Auth', "
        "rationale: 'industry standard', source_file: '', source_line: 0})"
    )
    m.conn.execute(
        "MATCH (d:SystemDesign {id: 'sd1'}), (f:File {id: 'f1'}) CREATE (d)-[:IMPLEMENTS]->(f)"
    )
    yield m
    m.close()


def test_export_graphml_returns_xml(mgr):
    xml = export_graphml(mgr.conn)
    assert xml.startswith('<?xml')
    assert '<graphml' in xml
    assert 'auth.py' in xml or 'f1' in xml


def test_export_graphml_contains_edges(mgr):
    xml = export_graphml(mgr.conn)
    assert '<edge' in xml


def test_export_obsidian_creates_md_files(mgr, tmp_path):
    out_dir = tmp_path / "obsidian_vault"
    export_obsidian(mgr.conn, out_dir)
    md_files = list(out_dir.glob("*.md"))
    assert len(md_files) >= 2


def test_export_obsidian_file_contains_wikilinks(mgr, tmp_path):
    out_dir = tmp_path / "obsidian_vault"
    export_obsidian(mgr.conn, out_dir)
    sd_file = out_dir / "OAuthFlow.md"
    assert sd_file.exists()
    content = sd_file.read_text()
    assert "[[auth.py]]" in content or "[[f1" in content or "IMPLEMENTS" in content


def test_export_wiki_returns_markdown(mgr, tmp_path):
    md = export_wiki(mgr.conn, tmp_path)
    assert "# " in md
    assert "Auth" in md
