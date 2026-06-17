"""
Graph Relay — pushes the Kùzu graph to external graph databases.

Functions:
  relay_neo4j(conn, uri, user, password, database, cypher_only) -> list[str]
  relay_falkordb(conn, host, port, password, graph_name, cypher_only) -> list[str]
"""
from __future__ import annotations

from typing import Any

import kuzu


def _rows(result: Any) -> list[dict]:
    rows = []
    cols = result.get_column_names()
    while result.has_next():
        rows.append(dict(zip(cols, result.get_next())))
    return rows


def _build_cypher_statements(conn: kuzu.Connection) -> list[str]:
    from core.graph_api import NODE_TABLES, REL_TABLES

    def _esc(v: Any) -> str:
        if isinstance(v, str):
            return "'" + v.replace("\\", "\\\\").replace("'", "\\'") + "'"
        if v is None:
            return "null"
        return str(v)

    statements: list[str] = []

    for table in NODE_TABLES:
        try:
            r = conn.execute(f"MATCH (n:{table}) RETURN n.*")
            for row in _rows(r):
                flat = {k[2:] if k.startswith("n.") else k: v for k, v in row.items()}
                nid = flat.get("id", "")
                props = ", ".join(f"{k}: {_esc(v)}" for k, v in flat.items())
                statements.append(
                    f"MERGE (n:{table} {{id: {_esc(nid)}}}) SET n += {{{props}}};"
                )
        except Exception:
            pass

    for rel in REL_TABLES:
        try:
            r = conn.execute(f"MATCH (a)-[:{rel}]->(b) RETURN a.id AS src, b.id AS dst")
            for row in _rows(r):
                src, dst = row.get("src"), row.get("dst")
                if src and dst:
                    statements.append(
                        f"MATCH (a {{id: {_esc(src)}}}), (b {{id: {_esc(dst)}}}) "
                        f"MERGE (a)-[:{rel}]->(b);"
                    )
        except Exception:
            pass

    return statements


def relay_neo4j(
    conn: kuzu.Connection,
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "",
    database: str = "neo4j",
    cypher_only: bool = False,
) -> list[str]:
    statements = _build_cypher_statements(conn)
    if cypher_only:
        return statements

    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise ImportError(
            "neo4j driver not installed. Run: pip install cortex[neo4j]\n"
            "Or use --cypher-only to export Cypher without connecting."
        )

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session(database=database) as session:
        for stmt in statements:
            session.run(stmt.rstrip(";"))
    driver.close()
    return statements


def relay_falkordb(
    conn: kuzu.Connection,
    host: str = "localhost",
    port: int = 6379,
    password: str = "",
    graph_name: str = "cortex",
    cypher_only: bool = False,
) -> list[str]:
    statements = _build_cypher_statements(conn)
    if cypher_only:
        return statements

    try:
        import falkordb
    except ImportError:
        raise ImportError(
            "falkordb driver not installed. Run: pip install cortex[falkordb]\n"
            "Or use --cypher-only to export Cypher without connecting."
        )

    client = falkordb.FalkorDB(host=host, port=port, password=password or None)
    graph = client.select_graph(graph_name)
    for stmt in statements:
        graph.query(stmt.rstrip(";"))
    return statements
