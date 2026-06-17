"""
Graph Reconciler — 3-way merge strategy for .cortex/versions.json.

Used as a git merge driver:
  git config merge.cortex-versions.driver 'cortex reconcile %O %A %B'
  .gitattributes: .cortex/versions.json merge=cortex-versions
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_VERSIONS = 5


def reconcile_versions(base: dict, ours: dict, theirs: dict) -> dict:
    by_slot: dict[int, dict] = {}

    for v in base.get("versions", []):
        slot = v.get("slot")
        if slot is not None:
            by_slot[slot] = v

    for v in ours.get("versions", []):
        slot = v.get("slot")
        if slot is None:
            continue
        existing = by_slot.get(slot)
        if existing is None or v.get("unix_ts", 0) > existing.get("unix_ts", 0):
            by_slot[slot] = v

    for v in theirs.get("versions", []):
        slot = v.get("slot")
        if slot is None:
            continue
        existing = by_slot.get(slot)
        if existing is None or v.get("unix_ts", 0) > existing.get("unix_ts", 0):
            by_slot[slot] = v

    merged = sorted(by_slot.values(), key=lambda v: v.get("unix_ts", 0))
    if len(merged) > MAX_VERSIONS:
        merged = merged[-MAX_VERSIONS:]

    current_slot = merged[-1]["slot"] if merged else 0
    return {"current_slot": current_slot, "versions": merged}


def reconcile_files(base_path: str, ours_path: str, theirs_path: str) -> int:
    try:
        base = json.loads(Path(base_path).read_text())
        ours = json.loads(Path(ours_path).read_text())
        theirs = json.loads(Path(theirs_path).read_text())
    except Exception as exc:
        print(f"[cortex reconcile] Error reading merge inputs: {exc}", file=sys.stderr)
        return 1

    result = reconcile_versions(base, ours, theirs)
    Path(ours_path).write_text(json.dumps(result, indent=2))
    return 0
