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


def _cmd_run(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    import uvicorn
    from cortex.web_server import _build_app

    app = _build_app(root)
    print(f"Cortex  →  http://{args.host}:{args.port}  (project: {root})")
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

    args = parser.parse_args()

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "mcp":
        _cmd_mcp(args)
