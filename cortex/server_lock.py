"""Lockfile + discovery so a second `cortex run` attaches to a live server."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

LOCK_PATH = Path.home() / ".cortex" / "server.json"


def write_lock(host: str, port: int, path: Path = LOCK_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"host": host, "port": port, "pid": os.getpid(), "started_at": time.time()}
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_lock(path: Path = LOCK_PATH) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear_lock(path: Path = LOCK_PATH) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def decide(lock: dict | None, probe: Callable[[str, int], dict | None]) -> str:
    if not lock:
        return "start"
    health = probe(lock.get("host", "127.0.0.1"), int(lock.get("port", 7842)))
    if health and health.get("status") == "ok":
        return "attach"
    return "start"


def probe_health(host: str, port: int, timeout: float = 1.0) -> dict | None:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None
