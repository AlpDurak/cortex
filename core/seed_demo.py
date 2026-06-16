"""Seed a demo graph for visual testing. Run: python -m core.seed_demo"""
from pathlib import Path
from core.db import DatabaseManager


def main():
    mgr = DatabaseManager(Path(__file__).parent.parent)
    mgr.init()
    c = mgr.conn

    c.execute("CREATE (n:File {id: '@File:main.py:f001', name: 'main.py', description: 'App entry point', code_block: '', file_path: 'src/main.py', language: 'python'})")
    c.execute("CREATE (n:File {id: '@File:auth.py:f002', name: 'auth.py', description: 'OAuth2 handler', code_block: '', file_path: 'src/auth.py', language: 'python'})")
    c.execute("CREATE (n:File {id: '@File:models.py:f003', name: 'models.py', description: 'DB ORM models', code_block: '', file_path: 'src/models.py', language: 'python'})")
    c.execute("CREATE (n:SystemDesign {id: '@SystemDesign:AddOAuth:sd001', name: 'Add OAuth', description: 'Implement OAuth2 login flow', code_block: '', design_type: 'task', status: 'active'})")
    c.execute("CREATE (n:Service {id: '@Service:Stripe:sv001', name: 'Stripe', description: 'Payment gateway', code_block: '', service_type: 'third_party', endpoint: 'https://api.stripe.com'})")
    c.execute("CREATE (n:Database {id: '@Database:Postgres:db001', name: 'Postgres', description: 'Primary relational DB', code_block: '', db_type: 'relational', connection_string: 'postgresql://localhost/app'})")
    c.execute("CREATE (n:Infrastructure {id: '@Infrastructure:AWS:inf001', name: 'AWS EC2', description: 'Production compute', code_block: '', provider: 'AWS', region: 'us-east-1'})")

    c.execute("MATCH (a:File {id: '@File:main.py:f001'}), (b:File {id: '@File:auth.py:f002'}) CREATE (a)-[:DEPENDS_ON {weight: 1.0}]->(b)")
    c.execute("MATCH (a:File {id: '@File:auth.py:f002'}), (b:File {id: '@File:models.py:f003'}) CREATE (a)-[:DEPENDS_ON {weight: 1.0}]->(b)")
    c.execute("MATCH (a:File {id: '@File:main.py:f001'}), (b:Service {id: '@Service:Stripe:sv001'}) CREATE (a)-[:TALKS_TO {protocol: 'HTTPS'}]->(b)")
    c.execute("MATCH (a:File {id: '@File:models.py:f003'}), (b:Database {id: '@Database:Postgres:db001'}) CREATE (a)-[:QUERIES {query_type: 'READ_WRITE'}]->(b)")
    c.execute("MATCH (a:Service {id: '@Service:Stripe:sv001'}), (b:Infrastructure {id: '@Infrastructure:AWS:inf001'}) CREATE (a)-[:HOSTED_ON]->(b)")
    c.execute("MATCH (a:Database {id: '@Database:Postgres:db001'}), (b:Infrastructure {id: '@Infrastructure:AWS:inf001'}) CREATE (a)-[:HOSTED_ON]->(b)")
    c.execute("MATCH (a:SystemDesign {id: '@SystemDesign:AddOAuth:sd001'}), (b:File {id: '@File:auth.py:f002'}) CREATE (a)-[:MODIFIES]->(b)")

    mgr.commit_snapshot("Seed: full demo graph")
    print("Demo graph seeded — 7 nodes, 7 edges, 2 snapshots.")
    mgr.close()


if __name__ == "__main__":
    main()
