"""In-process registry of open projects, each owning its DB and WebSocket hub."""

from __future__ import annotations

import hashlib
from pathlib import Path

from core.db import DatabaseManager
from core.project_info import get_project_name, find_favicon


def project_id(root) -> str:
    abs_path = str(Path(root).resolve())
    return hashlib.sha1(abs_path.encode("utf-8")).hexdigest()[:8]


class Hub:
    """Tracks WebSocket clients for one project and broadcasts text frames."""

    def __init__(self):
        self._clients: list = []

    async def connect(self, ws):
        await ws.accept()
        self._clients.append(ws)

    def disconnect(self, ws):
        self._clients = [c for c in self._clients if c is not ws]

    async def broadcast(self, message: str):
        dead = []
        for client in self._clients:
            try:
                await client.send_text(message)
            except Exception:
                dead.append(client)
        for d in dead:
            self.disconnect(d)


class ProjectState:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.id = project_id(self.root)
        self.name = get_project_name(self.root)
        self.favicon_path = find_favicon(self.root)
        self.mgr = DatabaseManager(self.root)
        self.mgr.init()
        self.hub = Hub()


class Registry:
    def __init__(self):
        self._projects: dict[str, ProjectState] = {}
        self._primary_id: str | None = None

    def register(self, root) -> ProjectState:
        pid = project_id(root)
        existing = self._projects.get(pid)
        if existing is not None:
            return existing
        state = ProjectState(root)
        self._projects[state.id] = state
        if self._primary_id is None:
            self._primary_id = state.id
        return state

    def get(self, pid: str) -> ProjectState | None:
        return self._projects.get(pid)

    def list(self) -> list[ProjectState]:
        return list(self._projects.values())

    @property
    def primary(self) -> ProjectState | None:
        if self._primary_id is None:
            return None
        return self._projects.get(self._primary_id)

    def remove(self, pid: str) -> bool:
        if pid not in self._projects or len(self._projects) <= 1:
            return False
        state = self._projects.pop(pid)
        try:
            state.mgr.close()
        except Exception:
            pass
        if self._primary_id == pid:
            self._primary_id = next(iter(self._projects), None)
        return True
