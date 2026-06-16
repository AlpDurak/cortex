"""
Cortex Web Server — FastAPI app that:
  - Serves the static VS Code-style UI
  - Exposes REST endpoints the frontend uses to load graph data
  - Maintains a WebSocket hub for live graph push from write_system_design_node
  - Injects the WebSocket broadcast hook into the MCP server module

Run:
    python -m cortex.web_server [--root /path/to/project] [--port 7842]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent          # cortex/
_REPO = _HERE.parent                   # project root (cortex repo)
_STATIC = _REPO / "static"


def _build_app(project_root: Path) -> FastAPI:
    from core.db import DatabaseManager
    from core.graph_api import get_neighborhood, find_path, compute_diff
    from core.project_info import get_project_name, find_favicon
    import cortex.mcp_server as mcp_mod

    project_name = get_project_name(project_root)
    favicon_path = find_favicon(project_root)

    mgr = DatabaseManager(project_root)
    mgr.init()

    # Wire WebSocket broadcast into the MCP server
    mcp_mod.PROJECT_ROOT = project_root
    mcp_mod._mgr = mgr

    # ---------------------------------------------------------------------------
    # WebSocket hub
    # ---------------------------------------------------------------------------

    class _Hub:
        def __init__(self):
            self._clients: list[WebSocket] = []

        async def connect(self, ws: WebSocket):
            await ws.accept()
            self._clients.append(ws)

        def disconnect(self, ws: WebSocket):
            self._clients = [c for c in self._clients if c is not ws]

        async def broadcast(self, message: str):
            dead = []
            for client in self._clients:
                try:
                    await client.send_text(message)
                except Exception:
                    dead.append(client)
            for d in dead:
                self._clients.remove(d)

    hub = _Hub()
    mcp_mod.set_ws_broadcast(hub.broadcast)

    # ---------------------------------------------------------------------------
    # FastAPI app
    # ---------------------------------------------------------------------------

    app = FastAPI(title="Cortex", docs_url=None, redoc_url=None)

    # Serve static files (JS, CSS, etc.)
    if _STATIC.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    # ------------------------------------------------------------------
    # Favicon
    # ------------------------------------------------------------------

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        if favicon_path and favicon_path.exists():
            media = "image/x-icon"
            if favicon_path.suffix == ".png":
                media = "image/png"
            elif favicon_path.suffix == ".svg":
                media = "image/svg+xml"
            return FileResponse(str(favicon_path), media_type=media)
        return Response(status_code=204)

    # ------------------------------------------------------------------
    # REST: meta
    # ------------------------------------------------------------------

    @app.get("/api/meta")
    async def api_meta():
        favicon_b64 = None
        favicon_mime = None
        if favicon_path and favicon_path.exists():
            raw = favicon_path.read_bytes()
            favicon_b64 = base64.b64encode(raw).decode()
            ext = favicon_path.suffix.lower()
            favicon_mime = {
                ".ico": "image/x-icon",
                ".png": "image/png",
                ".svg": "image/svg+xml",
            }.get(ext, "image/png")
        return JSONResponse({
            "project_name": project_name,
            "favicon_b64": favicon_b64,
            "favicon_mime": favicon_mime,
        })

    # ------------------------------------------------------------------
    # REST: timeline
    # ------------------------------------------------------------------

    @app.get("/api/timeline")
    async def api_timeline():
        return JSONResponse(mgr.get_timeline())

    # ------------------------------------------------------------------
    # REST: graph (all nodes + edges for a given slot)
    # ------------------------------------------------------------------

    @app.get("/api/graph")
    async def api_graph(slot: int = 0):
        """
        Return all nodes and edges for a snapshot slot.
        slot=0 (default) means the live database.
        """
        from core.graph_api import NODE_TABLES, REL_TABLES, _rows, _get_all_nodes, _get_all_edges

        if slot == 0:
            conn = mgr.conn
        else:
            conn = mgr.open_version_conn(slot)

        nodes = list(_get_all_nodes(conn).values())
        raw_edges = _get_all_edges(conn)
        edges = [
            {"src": k[0], "rel": k[1], "dst": k[2], **v}
            for k, v in raw_edges.items()
        ]
        return JSONResponse({"nodes": nodes, "edges": edges})

    # ------------------------------------------------------------------
    # REST: diff between two slots
    # ------------------------------------------------------------------

    @app.get("/api/diff")
    async def api_diff(from_slot: int, to_slot: int):
        try:
            diff = compute_diff(mgr, from_slot, to_slot)
        except FileNotFoundError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse(diff)

    # ------------------------------------------------------------------
    # REST: neighborhood
    # ------------------------------------------------------------------

    @app.get("/api/neighborhood")
    async def api_neighborhood(node_id: str, depth: int = 1):
        result = get_neighborhood(mgr.conn, node_id, depth=depth)
        return JSONResponse(result)

    # ------------------------------------------------------------------
    # REST: path
    # ------------------------------------------------------------------

    @app.get("/api/path")
    async def api_path(start: str, end: str):
        result = find_path(mgr.conn, start, end)
        return JSONResponse(result)

    # ------------------------------------------------------------------
    # REST: commit snapshot
    # ------------------------------------------------------------------

    @app.post("/api/commit")
    async def api_commit(body: dict[str, Any] = {}):
        message = body.get("message", "Manual commit from UI")
        entry = mgr.commit_snapshot(message)
        await hub.broadcast(json.dumps({"event": "snapshot", "entry": entry}))
        return JSONResponse(entry)

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await hub.connect(ws)
        try:
            # Send current graph immediately on connect
            from core.graph_api import _get_all_nodes, _get_all_edges
            nodes = list(_get_all_nodes(mgr.conn).values())
            raw_edges = _get_all_edges(mgr.conn)
            edges = [
                {"src": k[0], "rel": k[1], "dst": k[2]}
                for k in raw_edges
            ]
            await ws.send_text(json.dumps({
                "event": "init",
                "nodes": nodes,
                "edges": edges,
                "timeline": mgr.get_timeline(),
            }))
            while True:
                await ws.receive_text()   # keep alive; client can send pings
        except WebSocketDisconnect:
            hub.disconnect(ws)

    # ------------------------------------------------------------------
    # Main UI (served last so all API routes take priority)
    # ------------------------------------------------------------------

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_ui(full_path: str):
        index = _STATIC / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse("<h1>Cortex UI not found — run Phase 5 build.</h1>")

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cortex web server")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--port", type=int, default=7842, help="HTTP port")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    args = parser.parse_args()

    project_root = Path(args.root).resolve()
    app = _build_app(project_root)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
