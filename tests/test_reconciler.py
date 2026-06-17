import json
import pytest
from pathlib import Path
from core.reconciler import reconcile_versions


def test_reconcile_non_overlapping():
    base = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 1000, "message": "a"}]}
    ours = {"current_slot": 2, "versions": [
        {"slot": 1, "unix_ts": 1000, "message": "a"},
        {"slot": 2, "unix_ts": 2000, "message": "ours"},
    ]}
    theirs = {"current_slot": 3, "versions": [
        {"slot": 1, "unix_ts": 1000, "message": "a"},
        {"slot": 3, "unix_ts": 3000, "message": "theirs"},
    ]}
    result = reconcile_versions(base, ours, theirs)
    slots = {v["slot"] for v in result["versions"]}
    assert slots == {1, 2, 3}


def test_reconcile_conflict_keeps_newer():
    base = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 1000, "message": "a"}]}
    ours = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 2000, "message": "newer"}]}
    theirs = {"current_slot": 1, "versions": [{"slot": 1, "unix_ts": 1500, "message": "older"}]}
    result = reconcile_versions(base, ours, theirs)
    assert result["versions"][0]["message"] == "newer"


def test_reconcile_preserves_up_to_max_5():
    base = {"current_slot": 0, "versions": []}
    ours = {"current_slot": 3, "versions": [
        {"slot": i, "unix_ts": i * 1000, "message": f"v{i}"} for i in range(1, 4)
    ]}
    theirs = {"current_slot": 5, "versions": [
        {"slot": i, "unix_ts": i * 1000, "message": f"v{i}"} for i in range(3, 6)
    ]}
    result = reconcile_versions(base, ours, theirs)
    assert len(result["versions"]) <= 5
