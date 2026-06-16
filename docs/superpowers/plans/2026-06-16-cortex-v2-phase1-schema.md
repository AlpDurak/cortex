# Cortex v2 — Phase 1: Schema & Data Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up stale files, reorganise tests, then add Source Pins (file+line on every node), migrate status vocabulary to Decision Arc (proposed/building/shipped), add Groups (hyperedge nodes), add Session Trail (.cortex/trail.jsonl), and wire the Anchored Commits reminder into `cortex init` and every first MCP call.

**Architecture:** All changes are confined to `core/db.py` and `cortex/mcp_server.py`. Schema migrations use the existing `_migrate_schema` additive-ALTER pattern. Groups are a new first-class Kùzu node table (`Group`) with a `MEMBER_OF` relationship table. Session Trail is an append-only JSONL file at `.cortex/trail.jsonl` — it is never snapshotted.

**Tech Stack:** Kùzu (embedded graph DB, Python bindings), FastMCP, Python 3.11+, pytest

---

## Task 0: File Cleanup

**Files:**
- Move: `core/schema_test.py` → `tests/test_schema.py`
- Move: `core/graph_api_test.py` → `tests/test_graph_api.py`
- Move: `cortex/mcp_server_test.py` → `tests/test_mcp_server.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create tests/ and __init__.py**

```bash
mkdir tests
touch tests/__init__.py
```

- [ ] **Step 2: Move test files with git**

```bash
git mv core/schema_test.py tests/test_schema.py
git mv core/graph_api_test.py tests/test_graph_api.py
git mv cortex/mcp_server_test.py tests/test_mcp_server.py
```

- [ ] **Step 3: Verify imports in moved files are unchanged**

`tests/test_schema.py` uses `from core.db import DatabaseManager` — unchanged, still resolves from project root.
`tests/test_graph_api.py` uses `from core.db import DatabaseManager` and `from core.graph_api import ...` — unchanged.
`tests/test_mcp_server.py` uses `import cortex.mcp_server as srv` — unchanged.

Run all three to confirm:
```bash
python tests/test_schema.py && python tests/test_graph_api.py && python tests/test_mcp_server.py
```
Expected: each prints "PASSED" at the end.

- [ ] **Step 4: Commit**

```bash
git add tests/
git add -u
git commit -m "chore: move tests to tests/, create tests/__init__.py"
```

---

## Task 1: Source Pins — Schema

**Files:**
- Modify: `core/db.py` — `_NODE_TABLES` list and `_migrate_schema` function

Source Pins add `source_file STRING` and `source_line INT64` to all 5 node tables. Add them to the `CREATE TABLE` DDL so fresh databases have them, and to `_migrate_schema` so existing databases gain them.

- [ ] **Step 1: Write the failing test**

Create `tests/test_source_pins.py`:

```python
import pytest
from pathlib import Path
from core.db import DatabaseManager


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    yield m
    m.close()


def test_file_node_has_source_pins(mgr):
    mgr.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'a.py', description: '', "
        "code_block: '', file_path: 'a.py', language: 'python', "
        "source_file: 'a.py', source_line: 10})"
    )
    rows = mgr.query_to_dicts(
        "MATCH (n:File {id: 'f1'}) RETURN n.source_file AS sf, n.source_line AS sl"
    )
    assert rows[0]["sf"] == "a.py"
    assert rows[0]["sl"] == 10


def test_system_design_has_source_pins(mgr):
    mgr.conn.execute(
        "CREATE (n:SystemDesign {id: 'sd1', name: 'A', description: '', "
        "code_block: '', design_type: 'task', status: 'proposed', "
        "section: 'Auth', rationale: '', source_file: 'design.md', source_line: 5})"
    )
    rows = mgr.query_to_dicts(
        "MATCH (n:SystemDesign {id: 'sd1'}) RETURN n.source_file AS sf, n.source_line AS sl"
    )
    assert rows[0]["sf"] == "design.md"
    assert rows[0]["sl"] == 5


def test_service_node_has_source_pins(mgr):
    mgr.conn.execute(
        "CREATE (n:Service {id: 'sv1', name: 'Stripe', description: '', "
        "code_block: '', service_type: 'third_party', endpoint: 'https://api.stripe.com', "
        "source_file: '', source_line: 0})"
    )
    rows = mgr.query_to_dicts(
        "MATCH (n:Service {id: 'sv1'}) RETURN n.source_file AS sf, n.source_line AS sl"
    )
    assert rows[0]["sf"] == ""
    assert rows[0]["sl"] == 0
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_source_pins.py -v
```
Expected: FAIL — Kùzu rejects unknown property `source_file`.

- [ ] **Step 3: Add source_file/source_line to _NODE_TABLES in core/db.py**

In `core/db.py`, add two fields before `PRIMARY KEY` in each CREATE NODE TABLE statement:

```python
_NODE_TABLES = [
    """
    CREATE NODE TABLE IF NOT EXISTS File(
        id STRING,
        name STRING,
        description STRING,
        code_block STRING,
        file_path STRING,
        language STRING,
        source_file STRING,
        source_line INT64,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS SystemDesign(
        id STRING,
        name STRING,
        description STRING,
        code_block STRING,
        design_type STRING,
        status STRING,
        section STRING,
        rationale STRING,
        source_file STRING,
        source_line INT64,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Service(
        id STRING,
        name STRING,
        description STRING,
        code_block STRING,
        service_type STRING,
        endpoint STRING,
        source_file STRING,
        source_line INT64,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Database(
        id STRING,
        name STRING,
        description STRING,
        code_block STRING,
        db_type STRING,
        connection_string STRING,
        source_file STRING,
        source_line INT64,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Infrastructure(
        id STRING,
        name STRING,
        description STRING,
        code_block STRING,
        provider STRING,
        region STRING,
        source_file STRING,
        source_line INT64,
        PRIMARY KEY (id)
    )
    """,
]
```

- [ ] **Step 4: Add Source Pins migrations to _migrate_schema in core/db.py**

```python
def _migrate_schema(conn: kuzu.Connection) -> None:
    """Add columns to existing tables that were created before this schema version."""
    migrations = [
        "ALTER TABLE SystemDesign ADD section STRING DEFAULT ''",
        "ALTER TABLE SystemDesign ADD rationale STRING DEFAULT ''",
        "ALTER TABLE File ADD source_file STRING DEFAULT ''",
        "ALTER TABLE File ADD source_line INT64 DEFAULT 0",
        "ALTER TABLE SystemDesign ADD source_file STRING DEFAULT ''",
        "ALTER TABLE SystemDesign ADD source_line INT64 DEFAULT 0",
        "ALTER TABLE Service ADD source_file STRING DEFAULT ''",
        "ALTER TABLE Service ADD source_line INT64 DEFAULT 0",
        "ALTER TABLE Database ADD source_file STRING DEFAULT ''",
        "ALTER TABLE Database ADD source_line INT64 DEFAULT 0",
        "ALTER TABLE Infrastructure ADD source_file STRING DEFAULT ''",
        "ALTER TABLE Infrastructure ADD source_line INT64 DEFAULT 0",
    ]
    for ddl in migrations:
        try:
            conn.execute(ddl)
        except Exception:
            pass  # column already exists — safe to ignore
```

- [ ] **Step 5: Run — verify PASS**

```bash
pytest tests/test_source_pins.py -v
```
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add core/db.py tests/test_source_pins.py
git commit -m "feat(schema): add Source Pins (source_file, source_line) to all node tables"
```

---

## Task 2: Source Pins — MCP Tool Parameter

**Files:**
- Modify: `cortex/mcp_server.py` — `write_system_design_node` signature and body

- [ ] **Step 1: Write the failing test**

Append to `tests/test_source_pins.py`:

```python
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import cortex.mcp_server as srv


def test_write_system_design_node_sets_source_pins(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:Auth:OAuthFlow",
        name="OAuthFlow",
        section="Auth",
        description="OAuth2 login",
        source_file="docs/auth.md",
        source_line=42,
    )
    assert "sd:Auth:OAuthFlow" in result
    assert "Error" not in result
    mgr = srv._get_mgr()
    rows = mgr.query_to_dicts(
        "MATCH (n:SystemDesign {id: 'sd:Auth:OAuthFlow'}) "
        "RETURN n.source_file AS sf, n.source_line AS sl"
    )
    assert rows[0]["sf"] == "docs/auth.md"
    assert rows[0]["sl"] == 42
    srv._mgr = None
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_source_pins.py::test_write_system_design_node_sets_source_pins -v
```
Expected: FAIL — `TypeError: unexpected keyword argument 'source_file'`

- [ ] **Step 3: Add source_file and source_line to write_system_design_node in cortex/mcp_server.py**

Add two new parameters after `connects_to`:

```python
@mcp.tool()
def write_system_design_node(
    id: Annotated[str, "Node ID: SystemDesign:Section:Name e.g. SystemDesign:Auth:GoogleOAuth"],
    name: Annotated[str, "Human-readable name for this design node"],
    section: Annotated[str, "Design section this belongs to, e.g. Auth, Payments, Storage"],
    description: Annotated[str, "Full description of the design intent"],
    status: Annotated[str, "proposed | building | shipped"] = "proposed",
    rationale: Annotated[str, "Why this approach was chosen"] = "",
    connects_to: Annotated[
        str,
        "JSON array of {rel, target_id} e.g. "
        '[{"rel":"IMPLEMENTS","target_id":"File:auth.py"}]. Pass \'[]\' for none.',
    ] = "[]",
    source_file: Annotated[str, "Source file where this decision is documented, e.g. docs/auth.md"] = "",
    source_line: Annotated[int, "Line number in source_file (0 = unset)"] = 0,
) -> str:
```

After the existing `_set("rationale", rationale)` call inside the function body, add:

```python
    _set("source_file", source_file)
    conn.execute(
        "MATCH (n:SystemDesign {id: $id}) SET n.source_line = $val",
        {"id": id, "val": source_line},
    )
```

- [ ] **Step 4: Run all source pin tests**

```bash
pytest tests/test_source_pins.py -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add cortex/mcp_server.py tests/test_source_pins.py
git commit -m "feat(mcp): expose source_file + source_line on write_system_design_node"
```

---

## Task 3: Decision Arc — Status Vocabulary

**Files:**
- Modify: `core/db.py` — add `migrate_decision_arc_status` method to `DatabaseManager`
- Modify: `cortex/mcp_server.py` — validate status in `write_system_design_node`
- Modify: `cortex/main.py` — call migrate in `_cmd_init`, add hook reminder print

Decision Arc renames: `planned` → `proposed`, `in-progress`/`in_progress` → `building`, `done` → `shipped`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_decision_arc.py`:

```python
import pytest
from pathlib import Path
from core.db import DatabaseManager
import cortex.mcp_server as srv


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    yield m
    m.close()


def test_proposed_accepted(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:B", name="B", section="A", description="desc", status="proposed"
    )
    assert "Error" not in result
    srv._mgr = None


def test_building_accepted(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:C", name="C", section="A", description="desc", status="building"
    )
    assert "Error" not in result
    srv._mgr = None


def test_shipped_accepted(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:D", name="D", section="A", description="desc", status="shipped"
    )
    assert "Error" not in result
    srv._mgr = None


def test_planned_rejected(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_system_design_node(
        id="sd:A:E", name="E", section="A", description="desc", status="planned"
    )
    assert "Error" in result
    srv._mgr = None


def test_migrate_renames_old_statuses(mgr):
    for old in ("planned", "in-progress", "done", "in_progress"):
        mgr.conn.execute(
            f"CREATE (n:SystemDesign {{id: 'sd:{old}', name: '{old}', description: '', "
            f"code_block: '', design_type: 'task', status: '{old}', section: '', "
            f"rationale: '', source_file: '', source_line: 0}})"
        )
    mgr.migrate_decision_arc_status()
    rows = mgr.query_to_dicts(
        "MATCH (n:SystemDesign) RETURN n.id AS id, n.status AS status"
    )
    by_id = {r["id"]: r["status"] for r in rows}
    assert by_id["sd:planned"] == "proposed"
    assert by_id["sd:in-progress"] == "building"
    assert by_id["sd:done"] == "shipped"
    assert by_id["sd:in_progress"] == "building"
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_decision_arc.py -v
```
Expected: FAIL on `test_planned_rejected` (no validation) and `test_migrate_renames_old_statuses` (method missing).

- [ ] **Step 3: Add migrate_decision_arc_status to DatabaseManager in core/db.py**

Add after `get_timeline`:

```python
def migrate_decision_arc_status(self) -> int:
    """Migrate old status vocabulary to Decision Arc values. Returns count updated."""
    mapping = {
        "planned": "proposed",
        "in-progress": "building",
        "in_progress": "building",
        "done": "shipped",
    }
    rows = self.query_to_dicts(
        "MATCH (n:SystemDesign) RETURN n.id AS id, n.status AS status"
    )
    updated = 0
    for row in rows:
        old = row.get("status") or ""
        new = mapping.get(old)
        if new:
            self.conn.execute(
                "MATCH (n:SystemDesign {id: $id}) SET n.status = $s",
                {"id": row["id"], "s": new},
            )
            updated += 1
    return updated
```

- [ ] **Step 4: Add status validation to write_system_design_node in cortex/mcp_server.py**

After the `conn_list` JSON parse and before the node existence check, add:

```python
    _valid_statuses = {"proposed", "building", "shipped"}
    if status not in _valid_statuses:
        return (
            f"Error: invalid status '{status}'. "
            f"Decision Arc values: proposed | building | shipped"
        )
```

- [ ] **Step 5: Update _cmd_init in cortex/main.py**

Replace the existing `_cmd_init` body with:

```python
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
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_decision_arc.py -v
```
Expected: 5 PASSED

- [ ] **Step 7: Commit**

```bash
git add core/db.py cortex/mcp_server.py cortex/main.py tests/test_decision_arc.py
git commit -m "feat(schema): Decision Arc status vocabulary (proposed/building/shipped)"
```

---

## Task 4: Groups — Node Table + MCP Tool

**Files:**
- Modify: `core/db.py` — add `Group` to `_NODE_TABLES`, add `MEMBER_OF` to `_REL_TABLES`, add Group migration
- Modify: `core/graph_api.py` — add `Group` to `NODE_TABLES`, `MEMBER_OF` to `REL_TABLES`
- Modify: `cortex/mcp_server.py` — add `write_group_node` MCP tool

- [ ] **Step 1: Write the failing test**

Create `tests/test_groups.py`:

```python
import pytest
from pathlib import Path
from core.db import DatabaseManager
import cortex.mcp_server as srv


@pytest.fixture
def mgr(tmp_path):
    m = DatabaseManager(tmp_path)
    m.init()
    yield m
    m.close()


def test_group_node_table_exists(mgr):
    mgr.conn.execute(
        "CREATE (g:Group {id: 'g1', name: 'AuthCluster', description: 'Auth subsystem', section: 'Auth'})"
    )
    rows = mgr.query_to_dicts("MATCH (g:Group {id: 'g1'}) RETURN g.name AS name")
    assert rows[0]["name"] == "AuthCluster"


def test_member_of_relationship(mgr):
    mgr.conn.execute(
        "CREATE (g:Group {id: 'g1', name: 'AuthCluster', description: '', section: 'Auth'})"
    )
    mgr.conn.execute(
        "CREATE (n:File {id: 'f1', name: 'auth.py', description: '', "
        "code_block: '', file_path: 'auth.py', language: 'python', source_file: '', source_line: 0})"
    )
    mgr.conn.execute(
        "MATCH (f:File {id: 'f1'}), (g:Group {id: 'g1'}) CREATE (f)-[:MEMBER_OF]->(g)"
    )
    rows = mgr.query_to_dicts(
        "MATCH (f:File)-[:MEMBER_OF]->(g:Group {id: 'g1'}) RETURN f.id AS fid"
    )
    assert rows[0]["fid"] == "f1"


def test_write_group_node_creates_group(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_group_node(
        id="Group:Auth",
        name="Auth",
        description="Authentication subsystem",
        section="Auth",
        member_ids="[]",
    )
    assert "Group:Auth" in result
    assert "Error" not in result
    srv._mgr = None


def test_write_group_node_warns_on_missing_member(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    result = srv.write_group_node(
        id="Group:Auth2",
        name="Auth2",
        description="",
        section="Auth",
        member_ids='["nonexistent:node"]',
    )
    assert "not found" in result.lower() or "Warning" in result
    srv._mgr = None
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_groups.py -v
```
Expected: FAIL on `test_group_node_table_exists` — Kùzu doesn't know `Group` table yet.

- [ ] **Step 3: Add Group to _NODE_TABLES and MEMBER_OF to _REL_TABLES in core/db.py**

Append to `_NODE_TABLES` list (after `Infrastructure`):

```python
    """
    CREATE NODE TABLE IF NOT EXISTS Group(
        id STRING,
        name STRING,
        description STRING,
        section STRING,
        PRIMARY KEY (id)
    )
    """,
```

Append to `_REL_TABLES` list (after `RUNS_ON`):

```python
    (
        "CREATE REL TABLE IF NOT EXISTS MEMBER_OF("
        "FROM File TO Group, FROM SystemDesign TO Group, "
        "FROM Service TO Group, FROM Database TO Group, "
        "FROM Infrastructure TO Group, FROM Group TO Group)"
    ),
```

Also add Group migration to `_migrate_schema` (the `CREATE TABLE IF NOT EXISTS` handles new installs; existing installs will get the table on next `init` since we're using `IF NOT EXISTS`).

- [ ] **Step 4: Update NODE_TABLES and REL_TABLES in core/graph_api.py**

Line 19 — change to:
```python
NODE_TABLES = ["File", "SystemDesign", "Service", "Database", "Infrastructure", "Group"]
```

Lines 22-25 — change to:
```python
REL_TABLES = [
    "CONTAINS", "MODIFIES", "DEPENDS_ON", "QUERIES", "TALKS_TO", "HOSTED_ON",
    "IMPLEMENTS", "PART_OF", "USES", "STORES_IN", "RUNS_ON", "MEMBER_OF",
]
```

- [ ] **Step 5: Add write_group_node MCP tool to cortex/mcp_server.py**

Add before the `if __name__ == "__main__"` block:

```python
@mcp.tool()
def write_group_node(
    id: Annotated[str, "Group ID, e.g. Group:Auth"],
    name: Annotated[str, "Human-readable group name"],
    description: Annotated[str, "What this group represents architecturally"],
    section: Annotated[str, "Design section this group belongs to"],
    member_ids: Annotated[
        str,
        "JSON array of existing node IDs to add as members, e.g. "
        '[{"id": "File:auth.py:f1"}]. Pass \'[]\' to create an empty group.',
    ] = "[]",
) -> str:
    """
    Creates or updates a Group node and wires member nodes to it via MEMBER_OF edges.

    Groups appear in the web UI as rectangular compound containers. Use them to
    represent subsystems, domains, or cross-cutting clusters of nodes.

    Member nodes must already exist in the graph. Unknown IDs are reported as
    warnings but do not block the write.
    """
    _trail_append("write_group_node", {"id": id, "name": name})
    mgr = _get_mgr()
    conn = mgr.conn

    try:
        members: list[str] = json.loads(member_ids)
    except json.JSONDecodeError as exc:
        return f"Error: `member_ids` is not valid JSON — {exc}"

    exists_r = conn.execute(
        "MATCH (g:Group {id: $id}) RETURN count(*) AS c", {"id": id}
    )
    rows = []
    while exists_r.has_next():
        rows.append(exists_r.get_next())
    if not (rows and rows[0][0] > 0):
        conn.execute(
            "CREATE (g:Group {id: $id, name: '', description: '', section: ''})",
            {"id": id},
        )

    for prop, val in [("name", name), ("description", description), ("section", section)]:
        conn.execute(
            f"MATCH (g:Group {{id: $id}}) SET g.{prop} = $val",
            {"id": id, "val": val},
        )

    from core.graph_api import _node_label
    created: list[str] = []
    warnings: list[str] = []

    for member_id in members:
        member_label = _node_label(conn, member_id)
        if not member_label:
            warnings.append(f"Member not found: {member_id}")
            continue
        try:
            conn.execute(
                f"MATCH (m:{member_label} {{id: $mid}}), (g:Group {{id: $gid}}) "
                "CREATE (m)-[:MEMBER_OF]->(g)",
                {"mid": member_id, "gid": id},
            )
            created.append(member_id)
        except Exception as exc:
            warnings.append(f"Edge failed for {member_id}: {exc}")

    snapshot = mgr.commit_snapshot(f"write_group_node: {name}")

    lines = [
        "# Group Node Written\n",
        f"ID:          {id}",
        f"Name:        {name}",
        f"Section:     {section}",
        f"Description: {description}",
        f"\nMembers added ({len(created)}): {', '.join(created) or '(none)'}",
    ]
    if warnings:
        lines.append(f"\nWarnings ({len(warnings)}):")
        lines += [f"  {w}" for w in warnings]
    lines.append(f"\nSnapshot: slot={snapshot['slot']} ts={snapshot['timestamp']}")
    return "\n".join(lines)
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_groups.py -v
```
Expected: 4 PASSED

- [ ] **Step 7: Commit**

```bash
git add core/db.py core/graph_api.py cortex/mcp_server.py tests/test_groups.py
git commit -m "feat(schema): Groups — Group node table + MEMBER_OF rel + write_group_node MCP tool"
```

---

## Task 5: Session Trail + Anchored Commits Reminder

**Files:**
- Modify: `cortex/mcp_server.py` — add `_trail_append`, `_get_session_id`, `_hook_reminder_shown`, `get_session_trail` tool; add `_trail_append(...)` call at top of every existing tool
- Modify: `cortex/web_server.py` — add `GET /api/trail` endpoint

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_trail.py`:

```python
import json
import sys
import pytest
from pathlib import Path
import cortex.mcp_server as srv


def _reset(tmp_path):
    srv.PROJECT_ROOT = tmp_path
    srv._mgr = None
    srv._session_id = None
    srv._hook_reminder_shown = False


def test_trail_file_created_after_tool_call(tmp_path):
    _reset(tmp_path)
    srv.get_graph_timeline()
    trail_path = tmp_path / ".cortex" / "trail.jsonl"
    assert trail_path.exists()
    entries = [json.loads(l) for l in trail_path.read_text().splitlines() if l.strip()]
    assert entries[0]["tool"] == "get_graph_timeline"
    assert "ts" in entries[0]
    assert "session" in entries[0]
    _reset(tmp_path)


def test_trail_accumulates(tmp_path):
    _reset(tmp_path)
    srv.get_graph_timeline()
    srv.list_design_sections()
    trail_path = tmp_path / ".cortex" / "trail.jsonl"
    entries = [json.loads(l) for l in trail_path.read_text().splitlines() if l.strip()]
    tools = [e["tool"] for e in entries]
    assert "get_graph_timeline" in tools
    assert "list_design_sections" in tools
    _reset(tmp_path)


def test_get_session_trail_tool(tmp_path):
    _reset(tmp_path)
    srv.get_graph_timeline()
    result = srv.get_session_trail()
    assert "get_graph_timeline" in result
    _reset(tmp_path)


def test_hook_reminder_on_first_call(tmp_path, capsys):
    _reset(tmp_path)
    srv.get_graph_timeline()
    captured = capsys.readouterr()
    assert "cortex hook install" in captured.err
    _reset(tmp_path)


def test_hook_reminder_only_once(tmp_path, capsys):
    _reset(tmp_path)
    srv.get_graph_timeline()
    capsys.readouterr()
    srv.list_design_sections()
    captured = capsys.readouterr()
    assert "cortex hook install" not in captured.err
    _reset(tmp_path)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_session_trail.py -v
```
Expected: FAIL — `AttributeError: module 'cortex.mcp_server' has no attribute '_session_id'`

- [ ] **Step 3: Add trail infrastructure to cortex/mcp_server.py**

After the existing imports, add:

```python
import uuid as _uuid
from datetime import datetime as _dt

_session_id: str | None = None
_hook_reminder_shown: bool = False


def _get_session_id() -> str:
    global _session_id
    if _session_id is None:
        _session_id = str(_uuid.uuid4())[:8]
    return _session_id


def _trail_append(tool_name: str, args: dict | None = None) -> None:
    global _hook_reminder_shown
    if not _hook_reminder_shown:
        _hook_reminder_shown = True
        import sys as _sys
        print(
            "\n[Cortex] Tip: run 'cortex hook install' to auto-snapshot on every git commit.\n",
            file=_sys.stderr,
        )
    mgr = _get_mgr()
    trail_path = mgr.cortex_dir / "trail.jsonl"
    entry = {
        "ts": _dt.utcnow().isoformat() + "Z",
        "tool": tool_name,
        "session": _get_session_id(),
        "args": args or {},
    }
    with trail_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 4: Add _trail_append call to the start of every existing MCP tool in cortex/mcp_server.py**

```python
# get_graph_timeline:
def get_graph_timeline() -> str:
    _trail_append("get_graph_timeline")
    mgr = _get_mgr()
    ...

# query_graph_diff:
def query_graph_diff(from_version, to_version) -> str:
    _trail_append("query_graph_diff", {"from_version": from_version, "to_version": to_version})
    ...

# explore_neighborhood:
def explore_neighborhood(node_id, depth=1) -> str:
    _trail_append("explore_neighborhood", {"node_id": node_id, "depth": depth})
    ...

# find_structural_path:
def find_structural_path(start_node_id, end_node_id) -> str:
    _trail_append("find_structural_path", {"start": start_node_id, "end": end_node_id})
    ...

# write_system_design_node:
def write_system_design_node(...) -> str:
    _trail_append("write_system_design_node", {"id": id, "name": name})
    ...

# write_agent_instructions:
def write_agent_instructions() -> str:
    _trail_append("write_agent_instructions")
    ...

# list_design_sections:
def list_design_sections() -> str:
    _trail_append("list_design_sections")
    ...
```

- [ ] **Step 5: Add get_session_trail MCP tool to cortex/mcp_server.py**

Add before `write_group_node`:

```python
@mcp.tool()
def get_session_trail(
    limit: Annotated[int, "Max entries to return (default 50)"] = 50
) -> str:
    """
    Returns recent MCP tool invocations logged in .cortex/trail.jsonl.

    The Session Trail records every tool call with its timestamp, tool name,
    session ID (8-char UUID prefix), and key arguments. Use this to understand
    what an AI agent did in a previous session.
    """
    _trail_append("get_session_trail")
    mgr = _get_mgr()
    trail_path = mgr.cortex_dir / "trail.jsonl"
    if not trail_path.exists():
        return "No trail entries yet."

    entries = []
    for line in trail_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    entries = entries[-limit:]
    lines = ["# Session Trail\n"]
    for e in entries:
        arg_str = f"  {e['args']}" if e.get("args") else ""
        lines.append(f"[{e['ts']}] session={e['session']}  {e['tool']}{arg_str}")
    return "\n".join(lines)
```

- [ ] **Step 6: Add GET /api/trail to cortex/web_server.py**

Inside `_build_app`, after the `/api/commit` route:

```python
    @app.get("/api/trail")
    async def api_trail(limit: int = 100):
        trail_path = project_root / ".cortex" / "trail.jsonl"
        if not trail_path.exists():
            return JSONResponse([])
        entries = []
        for line in trail_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        return JSONResponse(entries[-limit:])
```

- [ ] **Step 7: Run all Phase 1 tests**

```bash
pytest tests/test_source_pins.py tests/test_decision_arc.py tests/test_groups.py tests/test_session_trail.py -v
```
Expected: All PASSED

- [ ] **Step 8: Commit**

```bash
git add cortex/mcp_server.py cortex/web_server.py tests/test_session_trail.py
git commit -m "feat(trail): Session Trail + Anchored Commits reminder on first MCP call per session"
```

---

Phase 1 complete. Delivers: Source Pins, Decision Arc enforcement, Groups, Session Trail, Anchored Commits reminder.
