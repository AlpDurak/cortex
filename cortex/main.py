"""
Cortex CLI

Usage:
    cortex init              Initialize the knowledge graph for the current project
    cortex run               Start the web UI (http://localhost:7842)
    cortex run --port 8000   Custom port
    cortex run --host 0.0.0.0
    cortex run --root /path/to/project
    cortex mcp               Start the MCP server (stdio — for AI tool configs)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


_HOOK_MARKER = "# cortex-hook"

_HOOK_SCRIPT = """\
#!/bin/sh
# cortex-hook — managed by 'cortex hook install'. Do not edit this line.
CORTEX_ROOT="$(git rev-parse --show-toplevel)"
MSG="$(git log -1 --pretty=%s 2>/dev/null || echo 'git commit')"
SHA="$(git log -1 --pretty=%H 2>/dev/null || echo '')"
cortex snapshot --message "$MSG" --sha "$SHA" --root "$CORTEX_ROOT" 2>/dev/null || true
"""


def _cmd_hook(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    git_dir = root / ".git"

    if not git_dir.is_dir():
        candidate = root
        while candidate != candidate.parent:
            candidate = candidate.parent
            if (candidate / ".git").is_dir():
                git_dir = candidate / ".git"
                break
        else:
            print("error: not a git repository", file=sys.stderr)
            sys.exit(1)

    hooks_dir = git_dir / "hooks"
    hook_path = hooks_dir / "post-commit"

    if args.hook_action == "install":
        hooks_dir.mkdir(exist_ok=True)
        hook_path.write_text(_HOOK_SCRIPT, encoding="utf-8")
        import stat
        current = hook_path.stat().st_mode
        hook_path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"[Cortex] Hook installed at {hook_path}")
        print("  Every git commit will now auto-snapshot the graph.")

    elif args.hook_action == "uninstall":
        if hook_path.exists() and _HOOK_MARKER in hook_path.read_text():
            hook_path.unlink()
            print(f"[Cortex] Hook removed from {hook_path}")
        elif hook_path.exists():
            print(f"[Cortex] Hook at {hook_path} was not installed by Cortex — leaving it alone.")
        else:
            print("[Cortex] No Cortex hook found — nothing to remove.")

    elif args.hook_action == "status":
        if hook_path.exists() and _HOOK_MARKER in hook_path.read_text():
            print(f"[Cortex] Hook status: installed at {hook_path}")
        elif hook_path.exists():
            print(f"[Cortex] Hook status: {hook_path} exists but was not installed by Cortex.")
        else:
            print("[Cortex] Hook status: not installed. Run 'cortex hook install' to enable.")


def _cmd_snapshot(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    from core.db import DatabaseManager
    mgr = DatabaseManager(root)
    mgr.init()
    message = args.message or "Git commit snapshot"
    if args.sha:
        short = args.sha[:8] if len(args.sha) > 8 else args.sha
        message = f"{message} ({short})"
    entry = mgr.commit_snapshot(message)
    mgr.close()
    print(f"[Cortex] Snapshot: slot={entry['slot']} ts={entry['timestamp']}")


def _cmd_connect(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    from cortex.connect import run_connect
    run_connect(root, preselect=args.select, git_ledger=args.git_ledger)


def _cmd_relay(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    from core.db import DatabaseManager
    from core.relay import relay_neo4j, relay_falkordb

    mgr = DatabaseManager(root)
    mgr.init()

    if args.target == "neo4j":
        stmts = relay_neo4j(
            mgr.conn,
            uri=args.uri,
            user=args.user,
            password=args.password,
            database=args.database,
            cypher_only=args.cypher_only,
        )
    else:
        stmts = relay_falkordb(
            mgr.conn,
            host=args.host,
            port=args.port,
            password=args.password,
            graph_name=args.graph,
            cypher_only=args.cypher_only,
        )

    mgr.close()

    if args.cypher_only:
        for stmt in stmts:
            print(stmt)
    else:
        print(f"[Cortex] Relayed {len(stmts)} statements to {args.target}.")


def _cmd_init(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    from core.db import DatabaseManager

    print(f"Initializing Cortex in {root} ...")
    mgr = DatabaseManager(root)
    mgr.init()
    updated = mgr.migrate_decision_arc_status()
    if updated:
        print(f"  Migrated {updated} design node(s) to Decision Arc status vocabulary.")
    mgr.close()
    print(f"Done — graph database ready at {root / '.cortex'}")
    print()
    print("Tip: run 'cortex hook install' to enable automatic git commit snapshots.")
    print()
    print("Optional: to enable the Graph Reconciler merge driver, add to your project:")
    print("  echo '.cortex/versions.json merge=cortex-versions' >> .gitattributes")
    print("  git config merge.cortex-versions.driver 'cortex reconcile %O %A %B'")


def _cmd_run(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    import uvicorn
    from cortex.web_server import _build_app

    app = _build_app(root)
    print(f"Cortex  ->  http://{args.host}:{args.port}  (project: {root})")
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_mcp(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    import cortex.mcp_server as mcp_mod

    mcp_mod.PROJECT_ROOT = root
    transport = "sse" if args.sse else "stdio"
    mcp_mod.mcp.run(transport=transport)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="cortex",
        description="Cortex — local knowledge graph for software projects",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ── init ────────────────────────────────────────────────────────────────
    p_init = sub.add_parser("init", help="Initialize the knowledge graph for a project")
    p_init.add_argument(
        "--root", default=".", metavar="DIR",
        help="Project root (default: current directory)",
    )

    # ── run ─────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Start the Cortex web UI")
    p_run.add_argument(
        "--root", default=".", metavar="DIR",
        help="Project root (default: current directory)",
    )
    p_run.add_argument("--port", type=int, default=7842, help="HTTP port (default: 7842)")
    p_run.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")

    # ── mcp ─────────────────────────────────────────────────────────────────
    p_mcp = sub.add_parser("mcp", help="Start the MCP server (stdio transport)")
    p_mcp.add_argument(
        "--root", default=".", metavar="DIR",
        help="Project root (default: current directory)",
    )
    p_mcp.add_argument(
        "--sse", action="store_true",
        help="Use SSE transport instead of stdio (for web debugging)",
    )

    # ── relay ────────────────────────────────────────────────────────────────
    p_relay = sub.add_parser("relay", help="Push graph to Neo4j or FalkorDB")
    p_relay.add_argument("target", choices=["neo4j", "falkordb"], help="Target graph DB")
    p_relay.add_argument("--root", default=".", metavar="DIR")
    p_relay.add_argument("--uri", default="bolt://localhost:7687", help="Neo4j bolt URI")
    p_relay.add_argument("--host", default="localhost", help="FalkorDB host")
    p_relay.add_argument("--port", type=int, default=6379, help="FalkorDB port")
    p_relay.add_argument("--user", default="neo4j", help="Neo4j username")
    p_relay.add_argument("--password", default="", help="Database password")
    p_relay.add_argument("--database", default="neo4j", help="Neo4j database name")
    p_relay.add_argument("--graph", default="cortex", help="FalkorDB graph name")
    p_relay.add_argument("--cypher-only", action="store_true",
                         help="Print Cypher statements without connecting")

    # ── connect ──────────────────────────────────────────────────────────────
    p_connect = sub.add_parser("connect", help="Install Cortex MCP config into AI tool configs")
    p_connect.add_argument("--root", default=".", metavar="DIR",
                           help="Project root (default: current directory)")
    p_connect.add_argument("--select", nargs="*", metavar="PLATFORM",
                           help="Non-interactive: pre-select platforms by key")
    p_connect.add_argument("--git-ledger", action="store_true", default=None,
                           help="Non-interactive: enable Git Ledger hook without prompting")
    p_connect.add_argument("--no-git-ledger", dest="git_ledger", action="store_false",
                           help="Non-interactive: skip Git Ledger hook without prompting")

    # ── reconcile (git merge driver) ─────────────────────────────────────────
    p_rec = sub.add_parser("reconcile", add_help=False)
    p_rec.add_argument("base")
    p_rec.add_argument("ours")
    p_rec.add_argument("theirs")

    # ── hook ─────────────────────────────────────────────────────────────────
    p_hook = sub.add_parser("hook", help="Manage the Cortex git post-commit hook")
    hook_sub = p_hook.add_subparsers(dest="hook_action", metavar="<action>")
    hook_sub.required = True

    p_hook_install = hook_sub.add_parser("install", help="Install the post-commit hook")
    p_hook_install.add_argument("--root", default=".", metavar="DIR")

    p_hook_uninstall = hook_sub.add_parser("uninstall", help="Remove the post-commit hook")
    p_hook_uninstall.add_argument("--root", default=".", metavar="DIR")

    p_hook_status = hook_sub.add_parser("status", help="Show hook installation status")
    p_hook_status.add_argument("--root", default=".", metavar="DIR")

    # ── snapshot (internal — called by git hook) ─────────────────────────────
    p_snap = sub.add_parser("snapshot", add_help=False)
    p_snap.add_argument("--message", default="Git commit snapshot")
    p_snap.add_argument("--sha", default="")
    p_snap.add_argument("--root", default=".")

    args = parser.parse_args()

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "mcp":
        _cmd_mcp(args)
    elif args.command == "relay":
        _cmd_relay(args)
    elif args.command == "connect":
        _cmd_connect(args)
    elif args.command == "reconcile":
        from core.reconciler import reconcile_files
        sys.exit(reconcile_files(args.base, args.ours, args.theirs))
    elif args.command == "hook":
        _cmd_hook(args)
    elif args.command == "snapshot":
        _cmd_snapshot(args)


if __name__ == "__main__":
    main()
