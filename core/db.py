"""
DatabaseManager: initializes and manages the Kùzu graph database
for Cortex. Handles the .cortex/ directory structure, schema creation,
and the 5-snapshot rolling version history.
"""

import gc
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import kuzu

MAX_VERSIONS = 5

# Schema DDL executed once on each fresh database instance
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
    """
    CREATE NODE TABLE IF NOT EXISTS NodeGroup(
        id STRING,
        name STRING,
        description STRING,
        section STRING,
        PRIMARY KEY (id)
    )
    """,
]

_REL_TABLES = [
    # File/Service/SystemDesign can contain each other
    "CREATE REL TABLE IF NOT EXISTS CONTAINS(FROM File TO File, FROM SystemDesign TO SystemDesign, FROM Service TO Service)",
    # Any node type can MODIFIES a File or Database
    "CREATE REL TABLE IF NOT EXISTS MODIFIES(FROM SystemDesign TO File, FROM SystemDesign TO Database, FROM File TO File, FROM File TO Database, FROM Service TO File)",
    # File-level dependencies
    "CREATE REL TABLE IF NOT EXISTS DEPENDS_ON(FROM File TO File, FROM Service TO Service, FROM Service TO File, weight DOUBLE)",
    # Anything that reads from a Database, Infrastructure, or Service (e.g. Prometheus scraping, FK refs)
    "CREATE REL TABLE IF NOT EXISTS QUERIES(FROM File TO Database, FROM Service TO Database, FROM SystemDesign TO Database, FROM Infrastructure TO Database, FROM Service TO Infrastructure, FROM Infrastructure TO Service, FROM Infrastructure TO Infrastructure, FROM Database TO Database, query_type STRING)",
    # Service/File/SystemDesign/Infrastructure can talk to Service or Infrastructure
    "CREATE REL TABLE IF NOT EXISTS TALKS_TO(FROM File TO Service, FROM Service TO Service, FROM Service TO Infrastructure, FROM SystemDesign TO Service, FROM SystemDesign TO Infrastructure, FROM Infrastructure TO Infrastructure, protocol STRING)",
    # Database/Service/Infrastructure hosted on Infrastructure
    "CREATE REL TABLE IF NOT EXISTS HOSTED_ON(FROM Database TO Infrastructure, FROM Service TO Infrastructure, FROM Infrastructure TO Infrastructure)",
    # SystemDesign/File can implement File/Service/Database/Infrastructure/SystemDesign
    "CREATE REL TABLE IF NOT EXISTS IMPLEMENTS(FROM SystemDesign TO File, FROM SystemDesign TO Service, FROM SystemDesign TO Database, FROM SystemDesign TO Infrastructure, FROM File TO Service, FROM File TO Database, FROM File TO Infrastructure, FROM File TO SystemDesign)",
    # Part-of hierarchy across SystemDesign nodes
    "CREATE REL TABLE IF NOT EXISTS PART_OF(FROM SystemDesign TO SystemDesign)",
    # SystemDesign/Service/Infrastructure uses Service or Infrastructure
    "CREATE REL TABLE IF NOT EXISTS USES(FROM SystemDesign TO Service, FROM SystemDesign TO Infrastructure, FROM Service TO Service, FROM Service TO Infrastructure, FROM Infrastructure TO Infrastructure)",
    # SystemDesign/Service/File stores data in Database
    "CREATE REL TABLE IF NOT EXISTS STORES_IN(FROM SystemDesign TO Database, FROM Service TO Database, FROM File TO Database)",
    # SystemDesign/Service/Database/File/Infrastructure runs on Infrastructure
    "CREATE REL TABLE IF NOT EXISTS RUNS_ON(FROM SystemDesign TO Infrastructure, FROM Service TO Infrastructure, FROM Database TO Infrastructure, FROM File TO Infrastructure, FROM Infrastructure TO Infrastructure)",
    (
        "CREATE REL TABLE IF NOT EXISTS MEMBER_OF("
        "FROM File TO NodeGroup, FROM SystemDesign TO NodeGroup, "
        "FROM Service TO NodeGroup, FROM Database TO NodeGroup, "
        "FROM Infrastructure TO NodeGroup, FROM NodeGroup TO NodeGroup)"
    ),
]


def _version_path(cortex_dir: Path, version: int) -> Path:
    """Return the path for a versioned snapshot (file or directory depending on Kùzu version)."""
    return cortex_dir / f"v{version}"


def _meta_path(cortex_dir: Path) -> Path:
    return cortex_dir / "versions.json"


def _load_meta(cortex_dir: Path) -> dict:
    p = _meta_path(cortex_dir)
    if p.exists():
        return json.loads(p.read_text())
    return {"current_slot": 0, "versions": []}


def _save_meta(cortex_dir: Path, meta: dict) -> None:
    _meta_path(cortex_dir).write_text(json.dumps(meta, indent=2))


def _apply_schema(conn: kuzu.Connection) -> None:
    for ddl in _NODE_TABLES:
        conn.execute(ddl)
    for ddl in _REL_TABLES:
        conn.execute(ddl)


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


class DatabaseManager:
    """
    Manages the Kùzu graph database stored in <project_root>/.cortex/.

    Versioning model
    ----------------
    - Up to MAX_VERSIONS (5) snapshots are kept as independent directories
      (.cortex/v1 … .cortex/v5).
    - The *live* database is .cortex/live/.
    - Metadata (slot assignments, timestamps, messages) lives in
      .cortex/versions.json.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cortex_dir = project_root / ".cortex"
        self.live_dir = self.cortex_dir / "live"
        self._db: Optional[kuzu.Database] = None
        self._conn: Optional[kuzu.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Create directories, open the live DB, apply schema."""
        self.cortex_dir.mkdir(exist_ok=True)
        # Kùzu creates its own subdirectory; do not pre-create live_dir.

        self._db = kuzu.Database(str(self.live_dir))
        self._conn = kuzu.Connection(self._db)
        _apply_schema(self._conn)
        _migrate_schema(self._conn)

        meta = _load_meta(self.cortex_dir)
        if not meta["versions"]:
            # Seed an initial "genesis" snapshot
            self._snapshot_live("Genesis commit", meta)

    def close(self) -> None:
        if self._conn:
            self._conn = None
        if self._db:
            self._db = None

    # ------------------------------------------------------------------
    # Public connection accessor
    # ------------------------------------------------------------------

    @property
    def conn(self) -> kuzu.Connection:
        if self._conn is None:
            raise RuntimeError("DatabaseManager not initialized — call init() first.")
        return self._conn

    # ------------------------------------------------------------------
    # Snapshot / version management
    # ------------------------------------------------------------------

    def commit_snapshot(self, message: str = "Manual commit") -> dict:
        """
        Snapshot the live DB into the rolling 5-slot history.

        This closes and reopens the underlying Kuzu database so Windows can
        release file locks before the snapshot copy. Re-acquire `mgr.conn`
        after calling this method; raw connection objects saved before the
        snapshot are no longer valid.

        Returns the metadata entry for the new version.
        """
        meta = _load_meta(self.cortex_dir)
        return self._snapshot_live(message, meta)

    def _copy_live_to(self, dest: Path) -> None:
        """Copy the live database to dest, closing and reopening the connection."""
        # Explicitly close before copying so Windows releases the file lock
        self._conn = None
        if self._db is not None:
            self._db.close()
            self._db = None
        gc.collect()

        if self.live_dir.is_dir():
            shutil.copytree(str(self.live_dir), str(dest))
        else:
            shutil.copy2(str(self.live_dir), str(dest))

        # Reopen
        self._db = kuzu.Database(str(self.live_dir))
        self._conn = kuzu.Connection(self._db)
        _apply_schema(self._conn)
        _migrate_schema(self._conn)

    def _snapshot_live(self, message: str, meta: dict) -> dict:
        versions: list = meta["versions"]

        # Determine the slot to write into (rotate oldest when full)
        if len(versions) < MAX_VERSIONS:
            slot = len(versions) + 1
        else:
            oldest_slot = versions[0]["slot"]
            old_path = _version_path(self.cortex_dir, oldest_slot)
            if old_path.is_dir():
                shutil.rmtree(old_path)
            elif old_path.exists():
                old_path.unlink()
            versions.pop(0)
            slot = oldest_slot

        dest = _version_path(self.cortex_dir, slot)
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()

        self._copy_live_to(dest)

        entry = {
            "slot": slot,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "unix_ts": time.time(),
            "message": message,
        }
        versions.append(entry)
        meta["versions"] = versions
        meta["current_slot"] = slot
        _save_meta(self.cortex_dir, meta)
        return entry

    def get_timeline(self) -> list[dict]:
        """
        Return the version history newest-first, annotated with a
        human-readable commit number.
        """
        meta = _load_meta(self.cortex_dir)
        versions = list(reversed(meta["versions"]))
        total = len(versions)
        for i, v in enumerate(versions):
            v["commit_number"] = total - i
            v["label"] = "Current" if i == 0 else f"Commit #{total - i}"
        return versions

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

    def open_version_conn(self, slot: int) -> kuzu.Connection:
        """
        Open a *read-only* connection to a historical snapshot.
        Caller is responsible for not mutating this connection.
        """
        snap_path = _version_path(self.cortex_dir, slot)
        if not snap_path.exists():
            raise FileNotFoundError(f"Snapshot slot {slot} not found at {snap_path}")
        db = kuzu.Database(str(snap_path), read_only=True)
        return kuzu.Connection(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def execute(self, cypher: str, params: Optional[dict] = None):
        """Run a Cypher query against the live database."""
        if params:
            return self.conn.execute(cypher, params)
        return self.conn.execute(cypher)

    def query_to_dicts(self, cypher: str, params: Optional[dict] = None) -> list[dict]:
        """Execute a Cypher query and return results as a list of dicts."""
        result = self.execute(cypher, params)
        rows = []
        while result.has_next():
            row = result.get_next()
            column_names = result.get_column_names()
            rows.append(dict(zip(column_names, row)))
        return rows
