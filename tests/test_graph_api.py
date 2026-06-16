"""
Phase 2 smoke-test: exercises neighborhood, path finding, and diff.
Run with: python -m core.graph_api_test
"""

from pathlib import Path
from core.db import DatabaseManager
from core.graph_api import get_neighborhood, find_path, compute_diff


def seed(mgr: DatabaseManager) -> None:
    conn = mgr.conn
    conn.execute(
        "CREATE (n:File {id: '@File:main.py:abc01', name: 'main.py', "
        "description: 'Entry point', code_block: '', file_path: 'src/main.py', language: 'python'})"
    )
    conn.execute(
        "CREATE (n:Service {id: '@Service:Stripe:sv001', name: 'Stripe', "
        "description: 'Payments', code_block: '', service_type: 'third_party', endpoint: 'https://api.stripe.com'})"
    )
    conn.execute(
        "CREATE (n:Database {id: '@Database:Postgres:db001', name: 'Postgres', "
        "description: 'Primary DB', code_block: '', db_type: 'relational', connection_string: 'postgresql://localhost/app'})"
    )
    conn.execute(
        "CREATE (n:Infrastructure {id: '@Infrastructure:AWS:inf001', name: 'AWS', "
        "description: 'Cloud', code_block: '', provider: 'AWS', region: 'us-east-1'})"
    )
    conn.execute(
        "MATCH (f:File {id: '@File:main.py:abc01'}), (s:Service {id: '@Service:Stripe:sv001'}) "
        "CREATE (f)-[:TALKS_TO {protocol: 'HTTPS'}]->(s)"
    )
    conn.execute(
        "MATCH (s:Service {id: '@Service:Stripe:sv001'}), (i:Infrastructure {id: '@Infrastructure:AWS:inf001'}) "
        "CREATE (s)-[:HOSTED_ON]->(i)"
    )
    conn.execute(
        "MATCH (f:File {id: '@File:main.py:abc01'}), (d:Database {id: '@Database:Postgres:db001'}) "
        "CREATE (f)-[:QUERIES {query_type: 'READ'}]->(d)"
    )


def main():
    project_root = Path(__file__).parent.parent
    mgr = DatabaseManager(project_root)
    mgr.init()
    seed(mgr)

    print("\n=== Neighborhood (depth=1) ===")
    result = get_neighborhood(mgr.conn, "@File:main.py:abc01", depth=1)
    print(f"  Center: {result['center']}")
    print(f"  Nodes:  {[n['id'] for n in result['nodes'] if 'id' in n]}")
    print(f"  Triples:")
    for t in result["triples"]:
        print(f"    {t}")

    print("\n=== Neighborhood (depth=2) ===")
    result2 = get_neighborhood(mgr.conn, "@File:main.py:abc01", depth=2)
    print(f"  Nodes found: {len(result2['nodes'])}")
    print(f"  Triples:")
    for t in result2["triples"]:
        print(f"    {t}")

    print("\n=== Structural Path ===")
    path = find_path(mgr.conn, "@File:main.py:abc01", "@Infrastructure:AWS:inf001")
    print(f"  Path length: {path['path_length']}")
    print(f"  Triples:")
    for t in path["triples"]:
        print(f"    {t}")

    # Snapshot current state as v2, then mutate and diff
    slot1_entry = mgr.commit_snapshot("Pre-mutation snapshot")
    slot1 = slot1_entry["slot"]
    print(f"\nSnapshot v{slot1} created.")

    # Mutate: add a new node and modify an existing one
    mgr.conn.execute(
        "CREATE (n:SystemDesign {id: '@SystemDesign:AuthFlow:sd001', name: 'AuthFlow', "
        "description: 'OAuth implementation', code_block: '', design_type: 'epic', status: 'todo'})"
    )
    mgr.conn.execute(
        "MATCH (f:File {id: '@File:main.py:abc01'}) SET f.description = 'Entry point (updated)'"
    )

    slot2_entry = mgr.commit_snapshot("Post-mutation snapshot")
    slot2 = slot2_entry["slot"]
    print(f"Snapshot v{slot2} created.\n")

    print("=== Graph Diff ===")
    diff = compute_diff(mgr, slot1, slot2)
    print(f"  Added nodes:    {diff['added_nodes']}")
    print(f"  Deleted nodes:  {diff['deleted_nodes']}")
    print(f"  Modified nodes: {diff['modified_nodes']}")
    print(f"  Summary triples:")
    for t in diff["summary_triples"]:
        print(f"    {t}")

    mgr.close()
    print("\nPhase 2 smoke-test PASSED.")


if __name__ == "__main__":
    main()
