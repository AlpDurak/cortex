"""
Phase 3 smoke-test: calls each MCP tool function directly.
Run with: python -m cortex.mcp_server_test
"""

import json
from pathlib import Path

# Point the server at a temp project root
import cortex.mcp_server as srv
srv.PROJECT_ROOT = Path(__file__).parent.parent

# Reset the manager so it picks up the new root
srv._mgr = None


def seed():
    mgr = srv._get_mgr()
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
    mgr.commit_snapshot("Seed data")


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def main():
    seed()

    separator("get_graph_timeline()")
    print(srv.get_graph_timeline())

    separator("explore_neighborhood(depth=1)")
    print(srv.explore_neighborhood("@File:main.py:abc01", depth=1))

    separator("explore_neighborhood(depth=2)")
    print(srv.explore_neighborhood("@File:main.py:abc01", depth=2))

    separator("find_structural_path()")
    print(srv.find_structural_path("@File:main.py:abc01", "@Infrastructure:AWS:inf001"))

    separator("write_system_design_node()")
    connections = json.dumps([
        {"rel": "MODIFIES", "target_id": "@File:main.py:abc01"}
    ])
    print(srv.write_system_design_node(
        id="@SystemDesign:AddOAuth:sd001",
        title="Add OAuth Login",
        type="task",
        description="Implement OAuth2 login flow via Stripe identity",
        connections=connections,
    ))

    # Now diff the two snapshots
    timeline = srv._get_mgr().get_timeline()
    slots = [v["slot"] for v in reversed(timeline)]
    if len(slots) >= 2:
        separator(f"query_graph_diff(slot {slots[-2]} → slot {slots[-1]})")
        print(srv.query_graph_diff(slots[-2], slots[-1]))

    separator("explore_neighborhood() — new SystemDesign node")
    print(srv.explore_neighborhood("@SystemDesign:AddOAuth:sd001", depth=1))

    print("\n\nPhase 3 smoke-test PASSED.")


if __name__ == "__main__":
    main()
