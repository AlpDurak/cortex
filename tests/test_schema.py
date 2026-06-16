"""
Quick smoke-test: initializes the DB, inserts one node of each type,
and prints the timeline. Run with: python -m core.schema_test
"""

from pathlib import Path
from core.db import DatabaseManager


def main():
    project_root = Path(__file__).parent.parent
    mgr = DatabaseManager(project_root)
    mgr.init()

    conn = mgr.conn

    # Insert one node of each type to verify schema
    conn.execute(
        "CREATE (n:File {id: '@File:main.py:abc01', name: 'main.py', "
        "description: 'Entry point', code_block: '', file_path: 'src/main.py', language: 'python'})"
    )
    conn.execute(
        "CREATE (n:SystemDesign {id: '@SystemDesign:AuthFlow:sd001', name: 'AuthFlow', "
        "description: 'Implement OAuth', code_block: '', design_type: 'epic', status: 'in_progress'})"
    )
    conn.execute(
        "CREATE (n:Service {id: '@Service:Stripe:sv001', name: 'Stripe', "
        "description: 'Payment gateway', code_block: '', service_type: 'third_party', endpoint: 'https://api.stripe.com'})"
    )
    conn.execute(
        "CREATE (n:Database {id: '@Database:Postgres:db001', name: 'Postgres', "
        "description: 'Primary relational DB', code_block: '', db_type: 'relational', connection_string: 'postgresql://localhost/app'})"
    )
    conn.execute(
        "CREATE (n:Infrastructure {id: '@Infrastructure:AWS_EC2:inf001', name: 'AWS_EC2', "
        "description: 'Primary compute', code_block: '', provider: 'AWS', region: 'us-east-1'})"
    )

    print("Nodes inserted successfully.")

    # Insert a relationship
    conn.execute(
        "MATCH (f:File {id: '@File:main.py:abc01'}), (s:Service {id: '@Service:Stripe:sv001'}) "
        "CREATE (f)-[:TALKS_TO {protocol: 'HTTPS'}]->(s)"
    )
    print("Relationship TALKS_TO created.")

    # Snapshot
    entry = mgr.commit_snapshot("Initial schema test commit")
    print(f"Snapshot created: {entry}")

    # Timeline
    timeline = mgr.get_timeline()
    print("\nTimeline:")
    for v in timeline:
        print(f"  [{v['label']}] slot={v['slot']} ts={v['timestamp']} msg={v['message']}")

    mgr.close()
    print("\nPhase 1 smoke-test PASSED.")


if __name__ == "__main__":
    main()
