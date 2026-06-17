"""
Bootstrap the Cortex graph for ArgusOne (Argus.Deals).

Run from the cortex repo root:
    python scripts/bootstrap_argusone.py --root C:/Users/USER/Documents/Code/ArgusOne
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import DatabaseManager
from core.graph_api import _node_label


def _exists(conn, label: str, nid: str) -> bool:
    r = conn.execute(f"MATCH (n:{label} {{id: $id}}) RETURN count(*) AS c", {"id": nid})
    return r.get_next()[0] > 0 if r.has_next() else False


def _set(conn, label: str, nid: str, prop: str, val) -> None:
    conn.execute(f"MATCH (n:{label} {{id: $id}}) SET n.{prop} = $val", {"id": nid, "val": val})


def infra(conn, nid, name, description, provider="", region=""):
    if not _exists(conn, "Infrastructure", nid):
        conn.execute(
            "CREATE (n:Infrastructure {id: $id, name: '', description: '', code_block: '', "
            "provider: '', region: '', source_file: '', source_line: 0})", {"id": nid}
        )
    _set(conn, "Infrastructure", nid, "name", name)
    _set(conn, "Infrastructure", nid, "description", description)
    _set(conn, "Infrastructure", nid, "provider", provider)
    _set(conn, "Infrastructure", nid, "region", region)
    print(f"  + Infrastructure: {name}")


def database(conn, nid, name, description, db_type=""):
    if not _exists(conn, "Database", nid):
        conn.execute(
            "CREATE (n:Database {id: $id, name: '', description: '', code_block: '', "
            "db_type: '', connection_string: '', source_file: '', source_line: 0})", {"id": nid}
        )
    _set(conn, "Database", nid, "name", name)
    _set(conn, "Database", nid, "description", description)
    _set(conn, "Database", nid, "db_type", db_type)
    print(f"  + Database: {name}")


def service(conn, nid, name, description, service_type="", endpoint=""):
    if not _exists(conn, "Service", nid):
        conn.execute(
            "CREATE (n:Service {id: $id, name: '', description: '', code_block: '', "
            "service_type: '', endpoint: '', source_file: '', source_line: 0})", {"id": nid}
        )
    _set(conn, "Service", nid, "name", name)
    _set(conn, "Service", nid, "description", description)
    _set(conn, "Service", nid, "service_type", service_type)
    _set(conn, "Service", nid, "endpoint", endpoint)
    print(f"  + Service: {name}")


def file_node(conn, nid, name, description, file_path="", language=""):
    if not _exists(conn, "File", nid):
        conn.execute(
            "CREATE (n:File {id: $id, name: '', description: '', code_block: '', "
            "file_path: '', language: '', source_file: '', source_line: 0})", {"id": nid}
        )
    _set(conn, "File", nid, "name", name)
    _set(conn, "File", nid, "description", description)
    _set(conn, "File", nid, "file_path", file_path)
    _set(conn, "File", nid, "language", language)
    print(f"  + File: {name}")


def design(conn, nid, name, section, description, status="shipped", rationale="", source_file=""):
    if not _exists(conn, "SystemDesign", nid):
        conn.execute(
            "CREATE (n:SystemDesign {id: $id, name: '', description: '', code_block: '', "
            "design_type: '', status: '', section: '', rationale: '', "
            "source_file: '', source_line: 0})", {"id": nid}
        )
    _set(conn, "SystemDesign", nid, "name", name)
    _set(conn, "SystemDesign", nid, "description", description)
    _set(conn, "SystemDesign", nid, "section", section)
    _set(conn, "SystemDesign", nid, "status", status)
    _set(conn, "SystemDesign", nid, "rationale", rationale)
    _set(conn, "SystemDesign", nid, "source_file", source_file)
    print(f"  + SystemDesign: {name}")


def edge(conn, src_id, rel, dst_id):
    src_label = _node_label(conn, src_id)
    dst_label = _node_label(conn, dst_id)
    if not src_label:
        print(f"  ! Edge skip: src not found: {src_id}")
        return
    if not dst_label:
        print(f"  ! Edge skip: dst not found: {dst_id}")
        return
    # Check if edge already exists
    try:
        r = conn.execute(
            f"MATCH (a:{src_label} {{id: $s}})-[:{rel}]->(b:{dst_label} {{id: $d}}) "
            f"RETURN count(*) AS c", {"s": src_id, "d": dst_id}
        )
        if r.has_next() and r.get_next()[0] > 0:
            return  # already exists
    except Exception:
        pass
    try:
        conn.execute(
            f"MATCH (a:{src_label} {{id: $s}}), (b:{dst_label} {{id: $d}}) "
            f"CREATE (a)-[:{rel}]->(b)", {"s": src_id, "d": dst_id}
        )
    except Exception as exc:
        print(f"  ! Edge ({src_id})-[{rel}]->({dst_id}) failed: {exc}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="C:/Users/USER/Documents/Code/ArgusOne")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    print(f"Bootstrapping Cortex graph for: {root.name}\n")

    mgr = DatabaseManager(root)
    mgr.init()
    conn = mgr.conn

    # ── Infrastructure ────────────────────────────────────────────────────────
    print("[Infrastructure]")
    infra(conn, "Infra:PostgreSQL",    "PostgreSQL",       "Primary durable store — games catalog, prices, history, users, wishlist, feedback", provider="self-hosted")
    infra(conn, "Infra:Redis",         "Redis Streams",    "Worker coordination via consumer groups and DLQs; rate-limiting and session cache", provider="self-hosted")
    infra(conn, "Infra:CloudflareR2",  "Cloudflare R2",    "Object storage for mirrored cover/hero images for the top 50 hot deals", provider="Cloudflare")
    infra(conn, "Infra:DockerCompose", "Docker Compose",   "Local and production orchestration for Postgres, Redis, and all worker services", provider="Docker")
    infra(conn, "Infra:Coolify",       "Coolify",          "Self-hosted PaaS for backend deployment; manages container lifecycle and env vars", provider="self-hosted")
    infra(conn, "Infra:Vercel",        "Vercel",           "Next.js frontend hosting with edge caching", provider="Vercel")
    infra(conn, "Infra:IGDB",          "IGDB API",         "Canonical game metadata source — dumps primary, live API patches urgent misses", provider="Twitch/IGDB")
    infra(conn, "Infra:ITAD",          "IsThereAnyDeal",   "Bootstrap-only historical price source; 12-month lows imported once per game", provider="ITAD")
    infra(conn, "Infra:Prometheus",    "Prometheus",       "Metrics scraping from Go workers and API", provider="self-hosted")
    infra(conn, "Infra:Grafana",       "Grafana",          "Dashboards for worker health, queue depth, and price pipeline lag", provider="self-hosted")

    # ── Databases ─────────────────────────────────────────────────────────────
    print("\n[Databases]")
    database(conn, "DB:Games",        "Games Table",        "Canonical game catalog: id, slug, title, IGDB metadata, image refs", db_type="postgresql")
    database(conn, "DB:Prices",       "Prices Table",       "Current regional prices per game per store per region (US/TR/EU)", db_type="postgresql")
    database(conn, "DB:PriceHistory", "Price History Table","Native price snapshots over time; ITAD bootstrap fills 12-month lows", db_type="postgresql")
    database(conn, "DB:StoreLinks",   "Store Links Table",  "Canonical store URLs per game: Steam, Epic, GOG, Humble", db_type="postgresql")
    database(conn, "DB:HotDeals",     "Hot Deals View",     "Computed top-50 deals ranked by discount depth and regional price", db_type="postgresql")
    database(conn, "DB:Wishlist",     "Wishlist Table",     "User wishlisted games with alert threshold per region", db_type="postgresql")
    database(conn, "DB:Feedback",     "Feedback Table",     "Page-scoped user feedback submissions", db_type="postgresql")
    database(conn, "DB:DLQ",          "Dead Letter Queue",  "Redis DLQ stream for failed messages awaiting replay or finalization", db_type="redis")

    # ── Services ──────────────────────────────────────────────────────────────
    print("\n[Services]")
    service(conn, "Svc:API",            "Go API (Fiber)",       "HTTP API: game search, price lookup, similar games, wishlist, feedback, admin endpoints", service_type="http", endpoint="/api/v1")
    service(conn, "Svc:Scheduler",      "Scheduler",            "Cron-driven master: triggers catalog refresh, price checks, media refresh, DLQ replay", service_type="worker")
    service(conn, "Svc:GameResolver",   "Game Resolver",        "Fuzzy-matches scraped titles to canonical IGDB catalog entries", service_type="worker")
    service(conn, "Svc:PriceScheduler", "Price Scheduler",      "Batches games into regional price check jobs by tier and deal signals", service_type="worker")
    service(conn, "Svc:StoreAdapters",  "Store Price Adapters", "Fetches live regional prices from Steam, Epic, GOG, Humble", service_type="worker")
    service(conn, "Svc:PriceUpdater",   "Price Updater",        "Writes current prices and native history snapshots to PostgreSQL", service_type="worker")
    service(conn, "Svc:ScrapeIngestor", "Scrape Ingestor",      "Validates raw scraper payloads before entering the resolver pipeline", service_type="worker")
    service(conn, "Svc:IGDBDump",       "IGDB Dump Processor",  "Loads IGDB catalog dumps as the authoritative game metadata source", service_type="worker")
    service(conn, "Svc:ImageIndexer",   "Image Indexer",        "Stores IGDB image IDs and derived URL metadata for games", service_type="worker")
    service(conn, "Svc:HotMedia",       "Hot Media Mirror",     "Mirrors cover and hero images for top-50 hot deals to Cloudflare R2", service_type="worker")
    service(conn, "Svc:ITADBootstrap",  "ITAD Bootstrap",       "One-time import of 12-month historical lows from IsThereAnyDeal per game", service_type="worker")
    service(conn, "Svc:DLQReplay",      "DLQ Replay Worker",    "Replays or finalizes dead-letter messages with audit logging", service_type="worker")
    service(conn, "Svc:Scraper",        "Python Scraper",       "Browser/client scrapers for Steam, Epic, GOG, Humble regional price pages", service_type="scraper")
    service(conn, "Svc:Mailer",         "Mailer",               "Sends wishlist deal alerts and admin notifications via email", service_type="worker")
    service(conn, "Svc:Alerter",        "Alerter",              "Monitors wishlist thresholds and triggers Mailer when deals hit target price", service_type="worker")
    service(conn, "Svc:Frontend",       "Next.js Frontend",     "React/Next.js UI: game browsing, deal discovery, wishlist, regional price display", service_type="web", endpoint="https://argus.deals")
    service(conn, "Svc:Workerd",        "Workerd",              "Cloudflare Workers runtime for edge routing and preview deployments", service_type="edge")

    # ── Files ─────────────────────────────────────────────────────────────────
    print("\n[Files]")
    file_node(conn, "File:GoAPI",         "backend/cmd/api",         "Fiber HTTP server entrypoint — registers all routes", "backend/cmd/api", "go")
    file_node(conn, "File:Router",        "backend/internal/router", "Route registration: games, prices, search, wishlist, feedback, admin", "backend/internal/router", "go")
    file_node(conn, "File:GoMod",         "backend/go.mod",          "Go module: Fiber v3, pgxpool, go-redis v9, oauth2, testcontainers", "backend/go.mod", "go")
    file_node(conn, "File:DockerCompose", "docker-compose.yml",      "Local dev orchestration: postgres, redis, all workers", "docker-compose.yml", "yaml")
    file_node(conn, "File:Scraper",       "scraper/",                "Python scrapers: steam.py, epic.py, gog.py, price_worker.py", "scraper", "python")
    file_node(conn, "File:Workflows",     "docs/workflows/",         "YAML workflow contracts defining worker I/O and stream envelopes (12 contracts)", "docs/workflows", "yaml")
    file_node(conn, "File:Migrations",    "backend/migrations/",     "SQL migration files managed by golang-migrate", "backend/migrations", "sql")
    file_node(conn, "File:Frontend",      "frontend/src/",           "Next.js app: pages, components, API client, vitest tests", "frontend/src", "typescript")
    file_node(conn, "File:Observability", "observability/",          "Prometheus + Grafana + Alloy config for metrics and dashboards", "observability", "yaml")
    file_node(conn, "File:GameResolver",  "backend/internal/gameresolver", "Fuzzy matching logic: title normalization, IGDB similarity scoring", "backend/internal/gameresolver", "go")
    file_node(conn, "File:PriceWorker",   "backend/internal/priceupdater", "Price write logic: current prices + native history snapshots", "backend/internal/priceupdater", "go")
    file_node(conn, "File:Queue",         "backend/internal/queue",  "Redis Streams consumer group helpers: read, ACK, DLQ push", "backend/internal/queue", "go")

    # ── SystemDesign ──────────────────────────────────────────────────────────
    print("\n[SystemDesign]")
    design(conn, "SD:RedisStreams", "Redis Streams as Worker Bus", "Data Pipeline",
        "All inter-service communication flows through Redis Streams consumer groups with DLQs. Workers consume from named streams, ACK on success, push to DLQ on failure.",
        rationale="Gives at-least-once delivery, consumer group fan-out, and built-in replay without a full message broker. DLQ pattern enables audit and recovery without losing messages.",
        source_file="docs/workflows/README.md")

    design(conn, "SD:IGDBPrimary", "IGDB Dumps as Canonical Catalog", "Data Pipeline",
        "IGDB bulk dumps are the authoritative game metadata source. Live API calls are reserved for urgent or high-value misses only. ITAD is bootstrap-only for historical prices.",
        rationale="Dump-first avoids rate limits, keeps costs zero at scale, and gives a stable offline snapshot. Live patching only for exceptions prevents API dependency in normal operation.",
        source_file="docs/PROJECT.md")

    design(conn, "SD:GoOwnsConsistency", "Go Owns All DB Consistency", "Architecture",
        "Go services own all writes to PostgreSQL: scheduler, resolver, price updater, DLQ replay. Python scrapers produce raw payloads only and never write to the DB directly.",
        rationale="Single-language ownership of DB consistency prevents data races and simplifies transaction semantics. Python used where browser/client scraping is easier to isolate.",
        source_file="backend/go.mod")

    design(conn, "SD:RegionalPricing", "Regional Price Model (US/TR/EU)", "Pricing",
        "Prices tracked per game per store per region. Launch regions: US/USD, TR/TRY, EU/EUR. Price tiers drive check frequency — hot deals checked more often.",
        rationale="Turkey region often has significantly lower pricing. Tracking all three gives international users accurate local prices and enables cross-region deal detection.",
        source_file="backend/internal/priceupdater")

    design(conn, "SD:WorkflowContracts", "Contract-First Workflow Specs", "Architecture",
        "Each worker is defined by a YAML contract specifying stream inputs, outputs, validation rules, error handling, and test strategy before implementation. 12 contracts total.",
        rationale="Contract-first prevents workers from drifting out of sync. YAML contracts serve as documentation and a test oracle for integration tests.",
        source_file="docs/workflows/README.md")

    design(conn, "SD:HotMediaMirror", "Hot Deal Image Mirroring", "Media",
        "Cover and hero images for the top 50 hot deals are mirrored to Cloudflare R2. IGDB-derived URLs are default; R2 mirrors served for top deals to avoid IGDB rate limits.",
        rationale="Serving images from R2 eliminates IGDB CDN dependency for the most-viewed content, reduces latency, and avoids hotlinking policy issues at scale.",
        source_file="backend/cmd/hot-media-mirror")

    design(conn, "SD:WishlistAlerts", "Wishlist Deal Alert System", "User Features",
        "Users set price thresholds per game per region. Alerter monitors prices vs thresholds; Mailer sends email alerts when deals hit target.",
        rationale="Price threshold alerts are the core retention mechanic — users return when their wishlisted game goes on sale in their preferred region.",
        source_file="backend/internal/wishlist")

    design(conn, "SD:DLQPattern", "Dead Letter Queue Replay", "Data Pipeline",
        "Failed messages land in a Redis DLQ stream. DLQ Replay Worker can replay them back into the pipeline or finalize (discard) them with audit log entries.",
        rationale="Without DLQ replay, any transient failure permanently loses scraper data. Audit log gives operators visibility into what was replayed or discarded.",
        source_file="backend/cmd/dlq-replay")

    design(conn, "SD:Observability", "Prometheus + Grafana Stack", "Operations",
        "Go workers expose /metrics endpoints. Prometheus scrapes via Alloy. Grafana dashboards show queue depth, pipeline lag, price update rates, and worker health.",
        rationale="Required to detect stuck workers, queue backlog buildup, and price pipeline lag before users notice stale prices.",
        source_file="observability/")

    design(conn, "SD:SourceAuthority", "Strict Source Authority Rules", "Data Pipeline",
        "IGDB dumps own game metadata. Stores own current regional price and availability. ITAD is bootstrap-only. Live IGDB API patching is reserved for urgent misses only.",
        rationale="Clear source authority prevents conflicting writes and makes data lineage traceable. Any system that can override canonical data is a consistency risk.",
        source_file="docs/PROJECT.md")

    # ── Edges ─────────────────────────────────────────────────────────────────
    print("\n[Edges]")

    # API
    edge(conn, "Svc:API",            "QUERIES",    "DB:Games")
    edge(conn, "Svc:API",            "QUERIES",    "DB:Prices")
    edge(conn, "Svc:API",            "QUERIES",    "DB:HotDeals")
    edge(conn, "Svc:API",            "QUERIES",    "DB:Wishlist")
    edge(conn, "Svc:API",            "QUERIES",    "DB:Feedback")
    edge(conn, "Svc:API",            "RUNS_ON",    "Infra:Coolify")
    edge(conn, "File:GoAPI",         "IMPLEMENTS", "Svc:API")
    edge(conn, "File:Router",        "IMPLEMENTS", "Svc:API")

    # Scheduler
    edge(conn, "Svc:Scheduler",      "TALKS_TO",   "Infra:Redis")
    edge(conn, "Svc:Scheduler",      "RUNS_ON",    "Infra:DockerCompose")

    # Scrape pipeline
    edge(conn, "Svc:Scraper",        "TALKS_TO",   "Svc:ScrapeIngestor")
    edge(conn, "File:Scraper",       "IMPLEMENTS", "Svc:Scraper")
    edge(conn, "Svc:ScrapeIngestor", "TALKS_TO",   "Infra:Redis")
    edge(conn, "Svc:ScrapeIngestor", "STORES_IN",  "DB:DLQ")

    # Game resolution
    edge(conn, "Svc:GameResolver",   "QUERIES",    "Infra:Redis")
    edge(conn, "Svc:GameResolver",   "STORES_IN",  "DB:Games")
    edge(conn, "Svc:GameResolver",   "STORES_IN",  "DB:StoreLinks")
    edge(conn, "File:GameResolver",  "IMPLEMENTS", "Svc:GameResolver")

    # Price pipeline
    edge(conn, "Svc:PriceScheduler", "TALKS_TO",   "Infra:Redis")
    edge(conn, "Svc:StoreAdapters",  "TALKS_TO",   "Infra:Redis")
    edge(conn, "Svc:PriceUpdater",   "STORES_IN",  "DB:Prices")
    edge(conn, "Svc:PriceUpdater",   "STORES_IN",  "DB:PriceHistory")
    edge(conn, "File:PriceWorker",   "IMPLEMENTS", "Svc:PriceUpdater")
    edge(conn, "File:Queue",         "IMPLEMENTS", "Svc:ScrapeIngestor")

    # IGDB / ITAD
    edge(conn, "Svc:IGDBDump",       "QUERIES",    "Infra:IGDB")
    edge(conn, "Svc:IGDBDump",       "STORES_IN",  "DB:Games")
    edge(conn, "Svc:ITADBootstrap",  "QUERIES",    "Infra:ITAD")
    edge(conn, "Svc:ITADBootstrap",  "STORES_IN",  "DB:PriceHistory")
    edge(conn, "Svc:ImageIndexer",   "QUERIES",    "Infra:IGDB")
    edge(conn, "Svc:ImageIndexer",   "STORES_IN",  "DB:Games")

    # Media — R2 is object storage infra, use USES (STORES_IN requires Database target)
    edge(conn, "Svc:HotMedia",       "USES",       "Infra:CloudflareR2")
    edge(conn, "Svc:HotMedia",       "QUERIES",    "DB:HotDeals")

    # Wishlist + alerts
    edge(conn, "Svc:Alerter",        "QUERIES",    "DB:Wishlist")
    edge(conn, "Svc:Alerter",        "QUERIES",    "DB:Prices")
    edge(conn, "Svc:Alerter",        "TALKS_TO",   "Svc:Mailer")

    # DLQ
    edge(conn, "Svc:DLQReplay",      "QUERIES",    "DB:DLQ")
    edge(conn, "Svc:DLQReplay",      "TALKS_TO",   "Infra:Redis")

    # Frontend
    edge(conn, "Svc:Frontend",       "TALKS_TO",   "Svc:API")
    edge(conn, "Svc:Frontend",       "RUNS_ON",    "Infra:Vercel")
    edge(conn, "File:Frontend",      "IMPLEMENTS", "Svc:Frontend")

    # Observability
    edge(conn, "Infra:Prometheus",   "QUERIES",    "Svc:API")
    edge(conn, "Infra:Prometheus",   "QUERIES",    "Svc:Scheduler")
    edge(conn, "Infra:Grafana",      "QUERIES",    "Infra:Prometheus")
    edge(conn, "File:Observability", "IMPLEMENTS", "Infra:Prometheus")

    # Infrastructure backing
    edge(conn, "Infra:PostgreSQL",   "RUNS_ON",    "Infra:DockerCompose")
    edge(conn, "Infra:Redis",        "RUNS_ON",    "Infra:DockerCompose")

    # SystemDesign -> implementation
    edge(conn, "SD:RedisStreams",        "USES",       "Infra:Redis")
    edge(conn, "SD:IGDBPrimary",         "USES",       "Infra:IGDB")
    edge(conn, "SD:IGDBPrimary",         "USES",       "Infra:ITAD")
    edge(conn, "SD:RegionalPricing",     "IMPLEMENTS", "Svc:PriceUpdater")
    edge(conn, "SD:RegionalPricing",     "IMPLEMENTS", "Svc:StoreAdapters")
    edge(conn, "SD:HotMediaMirror",      "IMPLEMENTS", "Svc:HotMedia")
    edge(conn, "SD:WishlistAlerts",      "IMPLEMENTS", "Svc:Alerter")
    edge(conn, "SD:WishlistAlerts",      "IMPLEMENTS", "Svc:Mailer")
    edge(conn, "SD:DLQPattern",          "IMPLEMENTS", "Svc:DLQReplay")
    edge(conn, "SD:DLQPattern",          "PART_OF",    "SD:RedisStreams")
    edge(conn, "SD:Observability",       "IMPLEMENTS", "Infra:Grafana")
    edge(conn, "SD:GoOwnsConsistency",   "PART_OF",    "SD:RedisStreams")
    edge(conn, "SD:WorkflowContracts",   "PART_OF",    "SD:RedisStreams")
    edge(conn, "SD:SourceAuthority",     "PART_OF",    "SD:IGDBPrimary")
    edge(conn, "File:Workflows",         "IMPLEMENTS", "SD:WorkflowContracts")
    edge(conn, "File:Migrations",        "MODIFIES",   "DB:Games")
    edge(conn, "File:Migrations",        "MODIFIES",   "DB:Prices")

    print("\n[Snapshot]")
    entry = mgr.commit_snapshot("Initial ArgusOne graph bootstrap")
    print(f"  Snapshot created: slot={entry['slot']}")

    mgr.close()

    # Count nodes
    from core.graph_api import NODE_TABLES, _rows
    mgr2 = DatabaseManager(root)
    mgr2.init()
    total = 0
    for t in NODE_TABLES:
        try:
            r = mgr2.conn.execute(f"MATCH (n:{t}) RETURN count(*) AS c")
            if r.has_next():
                total += r.get_next()[0]
        except Exception:
            pass
    mgr2.close()

    print(f"\nDone. {total} nodes written. Open http://localhost:7842")


if __name__ == "__main__":
    main()
