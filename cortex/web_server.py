"""
Cortex Web Server - multi-project FastAPI app.

Each project is held in a Registry as a ProjectState (its own DatabaseManager +
WebSocket Hub). Routes select a project via the `?project=<id>` query param,
defaulting to the primary project the server booted with.

Run:
    cortex run [--root /path/to/project] [--port 7842]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from cortex.registry import Registry, ProjectState

_HERE = Path(__file__).parent
_REPO = _HERE.parent
_STATIC = _REPO / "static"


def _build_app(project_root: Path) -> FastAPI:
    import cortex.mcp_server as mcp_mod

    registry = Registry()
    primary = registry.register(project_root)

    # Wire the MCP module + WebSocket broadcast to the PRIMARY project only.
    mcp_mod.PROJECT_ROOT = primary.root
    mcp_mod._mgr = primary.mgr
    mcp_mod.set_ws_broadcast(primary.hub.broadcast)

    app = FastAPI(title="Cortex", docs_url=None, redoc_url=None)

    if _STATIC.exists():
        from starlette.middleware.base import BaseHTTPMiddleware

        class _NoCacheStatic(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                if request.url.path.startswith("/static/"):
                    response.headers["Cache-Control"] = "no-store"
                    response.headers.pop("ETag", None)
                    response.headers.pop("Last-Modified", None)
                return response

        app.add_middleware(_NoCacheStatic)
        app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

    def _resolve(project: str | None) -> ProjectState:
        if project:
            st = registry.get(project)
            if st is None:
                raise HTTPException(status_code=404, detail=f"Unknown project: {project}")
            return st
        st = registry.primary
        if st is None:
            raise HTTPException(status_code=404, detail="No projects registered")
        return st

    async def _broadcast_projects():
        msg = json.dumps({"event": "projects"})
        for st in registry.list():
            await st.hub.broadcast(msg)

    # ---- project management ----

    @app.get("/api/health")
    async def api_health():
        return JSONResponse({
            "status": "ok",
            "pid": os.getpid(),
            "projects": [{"id": s.id, "name": s.name} for s in registry.list()],
        })

    @app.get("/api/projects")
    async def api_projects():
        return JSONResponse([
            {"id": s.id, "name": s.name, "root": str(s.root)} for s in registry.list()
        ])

    @app.post("/api/projects/register")
    async def api_projects_register(body: dict[str, Any]):
        root = body.get("root")
        if not root:
            raise HTTPException(status_code=400, detail="Missing 'root'")
        path = Path(root).resolve()
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")
        st = registry.register(path)
        await _broadcast_projects()
        return JSONResponse({"id": st.id, "name": st.name})

    @app.delete("/api/projects/{pid}")
    async def api_projects_delete(pid: str):
        if registry.get(pid) is None:
            raise HTTPException(status_code=404, detail=f"Unknown project: {pid}")
        if not registry.remove(pid):
            raise HTTPException(status_code=409, detail="Cannot remove the last project")
        await _broadcast_projects()
        return JSONResponse({"ok": True})

    # ---- favicon ----

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon(project: str | None = None):
        st = _resolve(project)
        fp = st.favicon_path
        if fp and fp.exists():
            media = "image/x-icon"
            if fp.suffix == ".png":
                media = "image/png"
            elif fp.suffix == ".svg":
                media = "image/svg+xml"
            return FileResponse(str(fp), media_type=media)
        return Response(status_code=204)

    # ---- meta ----

    @app.get("/api/meta")
    async def api_meta(project: str | None = None):
        st = _resolve(project)
        favicon_b64 = None
        favicon_mime = None
        if st.favicon_path and st.favicon_path.exists():
            raw = st.favicon_path.read_bytes()
            favicon_b64 = base64.b64encode(raw).decode()
            ext = st.favicon_path.suffix.lower()
            favicon_mime = {
                ".ico": "image/x-icon",
                ".png": "image/png",
                ".svg": "image/svg+xml",
            }.get(ext, "image/png")
        return JSONResponse({
            "project_id": st.id,
            "project_name": st.name,
            "favicon_b64": favicon_b64,
            "favicon_mime": favicon_mime,
        })

    @app.get("/api/timeline")
    async def api_timeline(project: str | None = None):
        return JSONResponse(_resolve(project).mgr.get_timeline())

    @app.get("/api/graph")
    async def api_graph(slot: int = 0, project: str | None = None):
        from core.graph_api import _get_all_nodes, _get_all_edges
        st = _resolve(project)
        conn = st.mgr.conn if slot == 0 else st.mgr.open_version_conn(slot)
        nodes = list(_get_all_nodes(conn).values())
        raw_edges = _get_all_edges(conn)
        edges = [{"src": k[0], "rel": k[1], "dst": k[2], **v} for k, v in raw_edges.items()]
        return JSONResponse({"nodes": nodes, "edges": edges})

    @app.get("/api/diff")
    async def api_diff(from_slot: int, to_slot: int, project: str | None = None):
        from core.graph_api import compute_diff
        st = _resolve(project)
        try:
            diff = compute_diff(st.mgr, from_slot, to_slot)
        except FileNotFoundError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        return JSONResponse(diff)

    @app.get("/api/neighborhood")
    async def api_neighborhood(node_id: str, depth: int = 1, project: str | None = None):
        from core.graph_api import get_neighborhood
        return JSONResponse(get_neighborhood(_resolve(project).mgr.conn, node_id, depth=depth))

    @app.get("/api/path")
    async def api_path(start: str, end: str, project: str | None = None):
        from core.graph_api import find_path
        return JSONResponse(find_path(_resolve(project).mgr.conn, start, end))

    @app.post("/api/commit")
    async def api_commit(body: dict[str, Any] = {}, project: str | None = None):
        st = _resolve(project)
        message = body.get("message", "Manual commit from UI")
        entry = st.mgr.commit_snapshot(message)
        await st.hub.broadcast(json.dumps({"event": "snapshot", "entry": entry}))
        return JSONResponse(entry)

    @app.get("/api/trail")
    async def api_trail(limit: int = 100, project: str | None = None):
        return JSONResponse(_read_jsonl(_resolve(project).root / ".cortex" / "trail.jsonl", limit))

    @app.get("/api/search")
    async def api_search(q: str = "", top_n: int = 20, project: str | None = None):
        if not q:
            return JSONResponse([])
        from core.analysis import pulse_search
        return JSONResponse(pulse_search(_resolve(project).mgr.conn, q, top_n=top_n))

    @app.get("/api/clusters")
    async def api_clusters(project: str | None = None):
        from core.analysis import detect_signal_clusters
        st = _resolve(project)
        return JSONResponse(detect_signal_clusters(st.mgr.conn, st.root))

    @app.get("/api/keystones")
    async def api_keystones(top_n: int = 10, project: str | None = None):
        from core.analysis import get_keystones
        return JSONResponse(get_keystones(_resolve(project).mgr.conn, top_n=top_n))

    @app.get("/api/latent-bridges")
    async def api_latent_bridges(top_n: int = 20, project: str | None = None):
        from core.analysis import get_latent_bridges
        st = _resolve(project)
        return JSONResponse(get_latent_bridges(st.mgr.conn, st.root, top_n=top_n))

    @app.get("/api/ledger")
    async def api_ledger(limit: int = 200, project: str | None = None):
        return JSONResponse(_read_jsonl(_resolve(project).root / ".cortex" / "ledger.jsonl", limit))

    @app.get("/api/brief")
    async def api_brief(project: str | None = None):
        from core.analysis import generate_brief
        st = _resolve(project)
        return JSONResponse({"brief": generate_brief(st.mgr.conn, st.root)})

    @app.post("/api/export")
    async def api_export(body: dict[str, Any] = {}, project: str | None = None):
        from core.export import export_graphml, export_obsidian, export_wiki, export_svg
        st = _resolve(project)
        fmt = body.get("format", "graphml")
        if fmt == "graphml":
            return Response(content=export_graphml(st.mgr.conn), media_type="application/xml")
        elif fmt == "svg":
            return Response(content=export_svg(st.mgr.conn), media_type="image/svg+xml")
        elif fmt == "wiki":
            return Response(content=export_wiki(st.mgr.conn, st.root), media_type="text/markdown")
        elif fmt == "obsidian":
            import tempfile, zipfile, io
            with tempfile.TemporaryDirectory() as tmpdir:
                export_obsidian(st.mgr.conn, Path(tmpdir))
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    for f in Path(tmpdir).glob("*.md"):
                        zf.write(f, f.name)
                buf.seek(0)
                return Response(
                    content=buf.read(),
                    media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="cortex-obsidian.zip"'},
                )
        return JSONResponse({"error": f"Unknown format: {fmt}"}, status_code=400)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket, project: str | None = None):
        try:
            st = _resolve(project)
        except HTTPException:
            await ws.close(code=1008)
            return
        await st.hub.connect(ws)
        try:
            from core.graph_api import _get_all_nodes, _get_all_edges
            nodes = list(_get_all_nodes(st.mgr.conn).values())
            raw_edges = _get_all_edges(st.mgr.conn)
            edges = [{"src": k[0], "rel": k[1], "dst": k[2]} for k in raw_edges]
            await ws.send_text(json.dumps({
                "event": "init",
                "nodes": nodes,
                "edges": edges,
                "timeline": st.mgr.get_timeline(),
            }))
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            st.hub.disconnect(ws)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_ui(full_path: str):
        index = _STATIC / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return HTMLResponse("<h1>Cortex UI not found.</h1>")

    return app


def _read_jsonl(path: Path, limit: int) -> list:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    return entries[-limit:]


def main():
    parser = argparse.ArgumentParser(description="Cortex web server")
    parser.add_argument("--root", default=".", help="Project root directory")
    parser.add_argument("--port", type=int, default=7842, help="HTTP port")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    args = parser.parse_args()
    app = _build_app(Path(args.root).resolve())
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
