import json
import pytest
from pathlib import Path
from core.db import DatabaseManager


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    yield m
    m.close()


def _seed(mgr):
    mgr.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth_handler', description: 'handles authentication tokens', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "CREATE (n:File {id: 'f2', name: 'payment_processor', description: 'processes stripe payments', "
        "code_block: '', file_path: 'pay.py', language: 'python', source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "CREATE (n:File {id: 'f3', name: 'auth_middleware', description: 'authentication middleware layer', "
        "code_block: '', file_path: 'mid.py', language: 'python', source_file: '', source_line: 0})"
    )


def _seed_with_edges(mgr):
    """Seed 3 nodes; f1 has 2 edges (highest degree), f2 has 1, f3 has 0."""
    _seed(mgr)
    mgr.conn.execute(
        "CREATE (n:Service {id: 'sv1', name: 'Stripe', description: 'Payments', "
        "code_block: '', service_type: 'third_party', endpoint: 'https://api.stripe.com', "
        "source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "MATCH (f:File {id: 'f1'}), (s:Service {id: 'sv1'}) CREATE (f)-[:TALKS_TO {protocol: 'HTTPS'}]->(s)"
    )
    mgr.conn.execute(
        "MATCH (f:File {id: 'f2'}), (s:Service {id: 'sv1'}) CREATE (f)-[:TALKS_TO {protocol: 'HTTPS'}]->(s)"
    )


# ============================================================
# Pulse Search tests
# ============================================================

def test_pulse_search_returns_matching_nodes(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "authentication")
    ids = [r["id"] for r in results]
    assert "f1" in ids
    assert "f3" in ids


def test_pulse_search_ranks_by_score(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "authentication")
    assert len(results) >= 2
    assert results[0]["score"] >= results[1]["score"]


def test_pulse_search_excludes_no_match(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "authentication")
    ids = [r["id"] for r in results]
    assert "f2" not in ids


def test_pulse_search_empty_query(mgr):
    from core.analysis import pulse_search
    _seed(mgr)
    results = pulse_search(mgr.conn, "")
    assert results == []


# ============================================================
# Keystones tests
# ============================================================

def test_keystones_returns_top_n(mgr):
    from core.analysis import get_keystones
    _seed_with_edges(mgr)
    results = get_keystones(mgr.conn, top_n=3)
    assert len(results) <= 3


def test_keystones_ranked_by_degree(mgr):
    from core.analysis import get_keystones
    _seed_with_edges(mgr)
    results = get_keystones(mgr.conn, top_n=10)
    # sv1 has 2 incoming edges — highest degree
    assert results[0]["id"] == "sv1"
    assert results[0]["degree"] >= 2


def test_keystones_includes_degree_field(mgr):
    from core.analysis import get_keystones
    _seed_with_edges(mgr)
    results = get_keystones(mgr.conn, top_n=5)
    for r in results:
        assert "degree" in r
        assert "id" in r
        assert "name" in r
        assert "label" in r


# ============================================================
# Signal Clusters tests
# ============================================================

def test_signal_clusters_returns_list(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    _seed_with_edges(mgr)
    clusters = detect_signal_clusters(mgr.conn, tmp_path)
    assert isinstance(clusters, list)
    assert len(clusters) >= 1


def test_signal_clusters_each_has_required_fields(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    _seed_with_edges(mgr)
    clusters = detect_signal_clusters(mgr.conn, tmp_path)
    for c in clusters:
        assert "id" in c
        assert "label" in c
        assert "color" in c
        assert "members" in c
        assert isinstance(c["members"], list)


def test_signal_clusters_writes_cache_file(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    _seed_with_edges(mgr)
    detect_signal_clusters(mgr.conn, tmp_path)
    cache = tmp_path / ".cortex" / "clusters.json"
    assert cache.exists()
    data = json.loads(cache.read_text())
    assert "generated_at" in data
    assert "clusters" in data


def test_signal_clusters_uses_cache_when_fresh(mgr, tmp_path):
    from core.analysis import detect_signal_clusters
    import time
    _seed_with_edges(mgr)
    # First call writes the cache
    detect_signal_clusters(mgr.conn, tmp_path)
    cache = tmp_path / ".cortex" / "clusters.json"
    mtime_before = cache.stat().st_mtime
    time.sleep(0.05)
    # Second call should return cached data without re-running
    detect_signal_clusters(mgr.conn, tmp_path)
    mtime_after = cache.stat().st_mtime
    assert mtime_after == mtime_before


# ============================================================
# Latent Bridges, Ledger, Brief tests
# ============================================================

def test_latent_bridges_returns_empty_without_clusters(mgr, tmp_path):
    from core.analysis import get_latent_bridges
    results = get_latent_bridges(mgr.conn, tmp_path)
    assert results == []


def test_latent_bridges_finds_cross_cluster_edges(mgr, tmp_path):
    from core.analysis import detect_signal_clusters, get_latent_bridges
    _seed_with_edges(mgr)
    detect_signal_clusters(mgr.conn, tmp_path)
    results = get_latent_bridges(mgr.conn, tmp_path)
    assert isinstance(results, list)
    for r in results:
        assert "src" in r
        assert "dst" in r
        assert "rel" in r
        assert r["src_cluster"] != r["dst_cluster"]


def test_ledger_write_appends_to_file(tmp_path):
    from core.analysis import ledger_write
    cortex_dir = tmp_path / ".cortex"
    cortex_dir.mkdir()
    ledger_write(tmp_path, "signal-clusters", "claude-sonnet-4-6", 1000, 500, 0.003)
    ledger_path = cortex_dir / "ledger.jsonl"
    assert ledger_path.exists()
    entry = json.loads(ledger_path.read_text().strip())
    assert entry["feature"] == "signal-clusters"
    assert entry["model"] == "claude-sonnet-4-6"
    assert entry["input_tokens"] == 1000
    assert entry["cost_usd"] == 0.003
    assert "ts" in entry


def test_ledger_write_accumulates(tmp_path):
    from core.analysis import ledger_write
    (tmp_path / ".cortex").mkdir()
    ledger_write(tmp_path, "feat-a", "m1", 100, 50, 0.001)
    ledger_write(tmp_path, "feat-b", "m2", 200, 100, 0.002)
    lines = (tmp_path / ".cortex" / "ledger.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_generate_brief_contains_sections(mgr, tmp_path):
    from core.analysis import generate_brief
    mgr.conn.execute(
        "CREATE (n:SystemDesign {id: 'sd1', name: 'OAuthFlow', description: 'OAuth', "
        "code_block: '', design_type: 'task', status: 'proposed', section: 'Auth', "
        "rationale: '', source_file: '', source_line: 0})"
    )
    brief = generate_brief(mgr.conn, tmp_path)
    assert "Auth" in brief
    assert "OAuthFlow" in brief
    assert "Node Counts" in brief
