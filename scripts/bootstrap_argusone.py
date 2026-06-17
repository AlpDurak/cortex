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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    print(f"  + INF: {name}")


def database(conn, nid, name, description, db_type=""):
    if not _exists(conn, "Database", nid):
        conn.execute(
            "CREATE (n:Database {id: $id, name: '', description: '', code_block: '', "
            "db_type: '', connection_string: '', source_file: '', source_line: 0})", {"id": nid}
        )
    _set(conn, "Database", nid, "name", name)
    _set(conn, "Database", nid, "description", description)
    _set(conn, "Database", nid, "db_type", db_type)
    print(f"  + DB: {name}")


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
    print(f"  + SVC: {name}")


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
    print(f"  + FILE: {name}")


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
    print(f"  + SD: {name}")


def node_group(conn, nid, name, description, section=""):
    if not _exists(conn, "NodeGroup", nid):
        conn.execute(
            "CREATE (n:NodeGroup {id: $id, name: '', description: '', section: ''})", {"id": nid}
        )
    _set(conn, "NodeGroup", nid, "name", name)
    _set(conn, "NodeGroup", nid, "description", description)
    _set(conn, "NodeGroup", nid, "section", section)
    print(f"  + GROUP: {name}")


def edge(conn, src_id, rel, dst_id):
    src_label = _node_label(conn, src_id)
    dst_label = _node_label(conn, dst_id)
    if not src_label:
        print(f"  ! skip edge: src not found: {src_id}")
        return
    if not dst_label:
        print(f"  ! skip edge: dst not found: {dst_id}")
        return
    try:
        r = conn.execute(
            f"MATCH (a:{src_label} {{id: $s}})-[:{rel}]->(b:{dst_label} {{id: $d}}) "
            f"RETURN count(*) AS c", {"s": src_id, "d": dst_id}
        )
        if r.has_next() and r.get_next()[0] > 0:
            return
    except Exception:
        pass
    try:
        conn.execute(
            f"MATCH (a:{src_label} {{id: $s}}), (b:{dst_label} {{id: $d}}) "
            f"CREATE (a)-[:{rel}]->(b)", {"s": src_id, "d": dst_id}
        )
    except Exception as exc:
        print(f"  ! Edge ({src_id})-[{rel}]->({dst_id}): {exc}")


def member_of(conn, member_id, group_id):
    member_label = _node_label(conn, member_id)
    if not member_label:
        print(f"  ! MEMBER_OF skip: {member_id} not found")
        return
    try:
        conn.execute(
            f"MATCH (a:{member_label} {{id: $m}}), (g:NodeGroup {{id: $g}}) "
            "CREATE (a)-[:MEMBER_OF]->(g)",
            {"m": member_id, "g": group_id}
        )
    except Exception as exc:
        print(f"  ! MEMBER_OF ({member_id})->[{group_id}]: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
    infra(conn, "Infra:PostgreSQL",   "PostgreSQL",         "Primary durable store — all catalog, pricing, history, users, wishlist, feedback tables", provider="self-hosted")
    infra(conn, "Infra:Redis",        "Redis",              "Redis Streams for worker coordination via consumer groups; also rate-limiting and session cache", provider="self-hosted")
    infra(conn, "Infra:R2",           "Cloudflare R2",      "Object storage: mirrored cover/hero images for top-50 hot deals", provider="Cloudflare")
    infra(conn, "Infra:DockerCompose","Docker Compose",     "Local and production orchestration for Postgres, Redis, and all worker services", provider="Docker")
    infra(conn, "Infra:Coolify",      "Coolify",            "Self-hosted PaaS managing backend container lifecycle and environment secrets", provider="self-hosted")
    infra(conn, "Infra:Vercel",       "Vercel",             "Next.js frontend hosting with edge caching and CDN", provider="Vercel")
    infra(conn, "Infra:IGDB",         "IGDB API",           "Game metadata authority — bulk dump downloads + Apicalypse /multiquery live API (4 req/sec limit)", provider="Twitch/IGDB")
    infra(conn, "Infra:ITAD",         "IsThereAnyDeal",     "Bootstrap-only historical price source; 12-month lows imported once per game", provider="ITAD")
    infra(conn, "Infra:Prometheus",   "Prometheus",         "Metrics scraping from Go workers and API /metrics endpoints via Alloy", provider="self-hosted")
    infra(conn, "Infra:Grafana",      "Grafana",            "Dashboards: queue depth, worker health, price pipeline lag, scrape throughput", provider="self-hosted")
    infra(conn, "Infra:TwitchOAuth",  "Twitch OAuth",       "Server-to-Server OAuth token provider for IGDB API access; auto-refreshed", provider="Twitch")
    infra(conn, "Infra:OpenCritic",   "OpenCritic API",     "Secondary enrichment via RapidAPI; 25 req/day hard limit; graceful degradation on quota", provider="RapidAPI")
    # Redis stream names as distinct infra nodes
    infra(conn, "Infra:Stream:Raw",     "stream:scrapes:raw",      "Redis Stream: raw scrape payloads from all store scrapers (XADD by scrapers)", provider="Redis")
    infra(conn, "Infra:Stream:Resolver","stream:resolver",         "Redis Stream: resolve jobs emitted by scrape ingestor (05->06)", provider="Redis")
    infra(conn, "Infra:Stream:Prices",  "stream:prices:update",    "Redis Stream: price update events from resolver to price-update worker (06->10)", provider="Redis")
    infra(conn, "Infra:Stream:DLQ",     "stream:dlq",              "Redis Stream: dead letter queue for failed messages awaiting replay or final-failure", provider="Redis")
    infra(conn, "Infra:Testcontainers", "Testcontainers (Go)",     "Integration test infra: spins up Postgres+Redis containers for TDD test suite", provider="Docker")

    # ── Databases ─────────────────────────────────────────────────────────────
    print("\n[Databases]")
    # Existing tables
    database(conn, "DB:Scrapes",       "scrapes",             "Scrape event metadata: id, namespace, date_string; tracks each scraping session", db_type="postgresql")
    database(conn, "DB:GameLibrary",   "game_library",        "Canonical game catalog: IGDB id/slug/metadata, ratings, popularity_score, cover_image_id, OC scores", db_type="postgresql")
    database(conn, "DB:StoreGames",    "store_games",         "Raw deal records per storefront; enrichment_status (pending/completed/not_found); links to game_library", db_type="postgresql")
    database(conn, "DB:StoreCovers",   "store_game_covers",   "Cover images scraped directly from storefronts; linked to store_games", db_type="postgresql")
    database(conn, "DB:PriceHistory",  "price_history",       "Time-series price snapshots per store_game; native history written by price-update worker", db_type="postgresql")
    database(conn, "DB:Wishlists",     "wishlists",           "User wishlists with target_price threshold, notify_email/push prefs; UNIQUE(user_id, game_library_id)", db_type="postgresql")
    # Planned tables (workflow v2)
    database(conn, "DB:CurrentPrices", "current_prices",      "Current regional price per game/store/region (US/TR/EU); price_*_usd_cents for cross-region compare (planned W1)", db_type="postgresql")
    database(conn, "DB:StoreLinks",    "store_links",         "Canonical store URLs per game: steam/epic/gog; store_game_native_id (migration 000060 planned)", db_type="postgresql")
    database(conn, "DB:HotDeals",      "hot_deals view",      "Computed top-50 deals ranked by discount depth and regional price", db_type="postgresql")
    database(conn, "DB:ResolverQueue", "resolver_reviews",    "Review queue for ambiguous resolver results; miss queue for unresolved titles (planned)", db_type="postgresql")
    database(conn, "DB:ITADBootstrap", "itad_bootstrap_runs", "Per game/store/region ITAD bootstrap audit trail (planned)", db_type="postgresql")
    database(conn, "DB:HotMediaMirrors","hot_media_mirrors",  "IGDB image IDs, R2 keys, fallback URLs, rank score, cleanup state (planned)", db_type="postgresql")
    database(conn, "DB:DLQAudit",      "dlq_replay_audit",    "Scoped replay/final-failure audit events written by DLQ worker", db_type="postgresql")
    database(conn, "DB:DLQ",           "DLQ (Redis)",         "Redis DLQ stream — failed messages awaiting replay or finalization", db_type="redis")
    database(conn, "DB:Feedback",      "feedback",            "Page-scoped user feedback submissions", db_type="postgresql")

    # ── Services ──────────────────────────────────────────────────────────────
    print("\n[Services]")
    # Scrapers
    service(conn, "Svc:SteamScraper", "Steam Scraper",       "Scrapes Steam store page per appid; STEAM_COUNTRY knob for regional pricing; outputs to stream:scrapes:raw", service_type="scraper")
    service(conn, "Svc:EpicScraper",  "Epic Scraper",        "Epic GraphQL API scraper; builds app_id=namespace:offerId composite; country param for regional price", service_type="scraper")
    service(conn, "Svc:GOGScraper",   "GOG Scraper",         "GOG catalog scraper; numeric product id as app_id; GOG_COUNTRY/GOG_CURRENCY params", service_type="scraper")
    service(conn, "Svc:PriceWorkerPy","Price Worker (Python)","build_update_envelope(): assembles prices.update payload from scrape data; same shape as worker 10 input", service_type="scraper")
    # Go workers (worker 01-12 order)
    service(conn, "Svc:Scheduler",        "App Scheduler (W01)",          "Cron-driven master: triggers catalog refresh, price-check batches, media refresh, DLQ replay", service_type="worker")
    service(conn, "Svc:IGDBDump",         "IGDB Dump Processor (W02)",    "Loads IGDB dump CSV as primary catalog source; emits store-link and image-indexing work", service_type="worker")
    service(conn, "Svc:StoreLinkExtract", "Store Link Extractor (W03)",   "Extracts canonical store links (steam/epic/gog) from IGDB websites and external IDs", service_type="worker")
    service(conn, "Svc:ImageIndexer",     "Game Image Indexer (W04)",     "Stores IGDB image/video IDs and derived URL metadata without mirroring binaries", service_type="worker")
    service(conn, "Svc:ScrapeIngestor",   "Scrape Ingestor (W05)",        "Validates raw store scrape payloads via consumer group; emits resolver jobs; XACK on success only", service_type="worker")
    service(conn, "Svc:GameResolver",     "Game Resolver (W06)",          "Resolves scraped games to IGDB records: exact match -> API-patch -> fuzzy -> review queue; emits prices.update", service_type="worker")
    service(conn, "Svc:ITADBootstrap",    "ITAD Bootstrap (W07)",         "One-time import of 12-month historical lows from IsThereAnyDeal per game/store/region", service_type="worker")
    service(conn, "Svc:PriceScheduler",   "Price Check Scheduler (W08)",  "Converts game tiers and deal signals into regional price-check batches", service_type="worker")
    service(conn, "Svc:StoreAdapters",    "Store Price Adapters (W09)",   "Python: fetches current regional prices from Steam, Epic, GOG; outputs to stream:prices:update", service_type="worker")
    service(conn, "Svc:PriceUpdater",     "Price Update Worker (W10)",    "Writes current_prices + native price_history atomically; emits alert candidates; XACK on success only", service_type="worker")
    service(conn, "Svc:HotMedia",         "Hot Media Mirror (W11)",       "Mirrors cover+hero images for top-50 hot deals to Cloudflare R2; cleans up evicted assets", service_type="worker")
    service(conn, "Svc:DLQReplay",        "DLQ Replay Worker (W12)",      "Replays or finalizes dead-letter messages; writes dlq_replay_audit entries", service_type="worker")
    # Enrichment (legacy Service C from early docs, predates worker contracts)
    service(conn, "Svc:EnrichmentWorker", "Enrichment Worker",            "Scans store_games for enrichment_status=pending; batches 50 games; IGDB multiquery 10-at-a-time; ON CONFLICT upsert to game_library", service_type="worker")
    # User-facing
    service(conn, "Svc:Alerter",   "Alerter",          "Monitors current_prices vs wishlist thresholds; triggers Mailer when deal hits target price", service_type="worker")
    service(conn, "Svc:Mailer",    "Mailer",           "Sends wishlist deal-alert emails and admin notifications", service_type="worker")
    service(conn, "Svc:Frontend",  "Next.js Frontend", "React/Next.js UI: game browse, deal discovery, wishlist, regional price display, feedback", service_type="web", endpoint="https://argus.deals")
    service(conn, "Svc:Workerd",   "Workerd",          "Cloudflare Workers runtime for edge routing and preview deployments", service_type="edge")
    # API
    service(conn, "Svc:API",       "Go API (Fiber)",   "HTTP REST API: game search, price lookup, similar games, wishlist CRUD, feedback, admin", service_type="http", endpoint="/api/v1")

    # ── Files ─────────────────────────────────────────────────────────────────
    print("\n[Files]")
    file_node(conn, "File:GoAPI",           "backend/cmd/api",                  "Fiber HTTP server entrypoint — registers all route groups", "backend/cmd/api", "go")
    file_node(conn, "File:Router",          "backend/internal/router",          "Route registration: games, prices, search, wishlist, feedback, admin", "backend/internal/router", "go")
    file_node(conn, "File:GameResolver",    "backend/internal/gameresolver",    "Fuzzy matching: title normalization, IGDB similarity scoring, review-queue push", "backend/internal/gameresolver", "go")
    file_node(conn, "File:PriceUpdater",    "backend/internal/priceupdater",    "Price write logic: current_prices + native price_history snapshots; COALESCE(native_id, store_game_id) resolution", "backend/internal/priceupdater", "go")
    file_node(conn, "File:Enrichment",      "backend/internal/enrichment",      "IGDB multiquery batching (10 at a time); OpenCritic integration; idempotent ON CONFLICT upsert to game_library", "backend/internal/enrichment", "go")
    file_node(conn, "File:Queue",           "backend/internal/queue",           "Redis Streams helpers: XREADGROUP, XACK, XADD to DLQ; consumer group lifecycle", "backend/internal/queue", "go")
    file_node(conn, "File:GoMod",           "backend/go.mod",                   "Go module: Fiber v3, pgxpool, go-redis v9, golang-migrate, testcontainers", "backend/go.mod", "go")
    file_node(conn, "File:Migrations",      "backend/migrations/",              "SQL migration files (golang-migrate): schema up to 000060 (store_game_native_id planned)", "backend/migrations", "sql")
    file_node(conn, "File:DockerCompose",   "docker-compose.yml",               "Local dev orchestration: argus-postgres, argus-redis containers on shared network", "docker-compose.yml", "yaml")
    file_node(conn, "File:SteamPy",         "scraper/steam.py",                 "Steam storefront scraper; STEAM_COUNTRY env knob; XADD to stream:scrapes:raw", "scraper/steam.py", "python")
    file_node(conn, "File:EpicPy",          "scraper/epic.py",                  "Epic GraphQL scraper; namespace:offer_id composite app_id; country param", "scraper/epic.py", "python")
    file_node(conn, "File:GOGPy",           "scraper/gog.py",                   "GOG catalog scraper; numeric product id; GOG_COUNTRY/GOG_CURRENCY params", "scraper/gog.py", "python")
    file_node(conn, "File:PriceWorkerPy",   "scraper/price_worker.py",          "build_update_envelope(): builds prices.update payload from scrape data; reuses worker 10 path", "scraper/price_worker.py", "python")
    file_node(conn, "File:Workflows",       "docs/workflows/",                  "12 YAML workflow contracts: stream inputs/outputs, retry policy, DLQ, metrics, acceptance gates", "docs/workflows", "yaml")
    file_node(conn, "File:Frontend",        "frontend/src/",                    "Next.js app: pages, components, API client, vitest tests, tailwind", "frontend/src", "typescript")
    file_node(conn, "File:Observability",   "observability/",                   "Prometheus + Grafana + Alloy config: scrape targets, alert rules, dashboards", "observability", "yaml")
    file_node(conn, "File:ProjectDoc",      "docs/PROJECT.md",                  "Master project handover doc: architecture, tech stack, DB schema, enrichment logic", "docs/PROJECT.md", "markdown")

    # ── SystemDesign ──────────────────────────────────────────────────────────
    print("\n[SystemDesign]")
    design(conn, "SD:RedisStreams",        "Redis Streams as Worker Bus",        "Data Pipeline",
        "All inter-service communication uses Redis Streams consumer groups. Workers XREADGROUP, write DB, XACK on success. No XACK on failure keeps message in PEL for retry.",
        rationale="At-least-once delivery with zero message loss. Transactional boundary: DB write + XACK are atomic at the worker level. DLQ catches permanent failures.",
        source_file="docs/workflows/README.md")

    design(conn, "SD:AtomicXACK",         "Atomic Write + XACK Pattern",       "Data Pipeline",
        "Every worker follows: XREADGROUP claim message -> pgx.Tx write -> XACK on success only. On failure: rollback + no XACK = message retained in PEL for retry. SIGTERM triggers graceful drain.",
        rationale="Prevents duplicate processing from crash recovery while guaranteeing at-least-once delivery. No XACK on failure is the safety net.",
        source_file="backend/internal/queue")

    design(conn, "SD:IGDBPrimary",         "IGDB Dumps as Canonical Catalog",   "Data Pipeline",
        "IGDB bulk dump CSV is the authoritative game metadata source. Live API /multiquery is used only for urgent enrichment misses (max 10 games/call, 4 req/sec). ITAD is bootstrap-only for price history.",
        rationale="Dump-first avoids rate limits and costs nothing at scale. Live patching is expensive and rate-limited — reserved for urgent gaps only.",
        source_file="docs/PROJECT.md")

    design(conn, "SD:EnrichmentBatching",  "IGDB Batch Enrichment (10/call)",   "Data Pipeline",
        "EnrichmentWorker scans store_games where enrichment_status=pending in batches of 50. Calls IGDB /multiquery with 10 games per HTTP request. OpenCritic as secondary source (graceful degradation on quota).",
        rationale="IGDB rate limit is 4 req/sec. Batching 10 per call maximizes throughput within limits. Atomic 50-game transaction: panic on game #49 rolls back all 50.",
        source_file="backend/internal/enrichment")

    design(conn, "SD:GoOwnsDB",            "Go Owns All DB Writes",             "Architecture",
        "All PostgreSQL writes are owned by Go workers using pgx.Tx atomic transactions. Python scrapers produce stream payloads only — never write to DB directly.",
        rationale="Single-language DB ownership prevents data races and simplifies transaction semantics. Python is used only where browser/client scraping is easier.",
        source_file="docs/PROJECT.md")

    design(conn, "SD:TDDMandate",          "Test-Driven Development Mandate",   "Architecture",
        "All new features require tests written concurrently. Every package (db, worker, enrichment) has unit tests + testcontainers integration tests. No code merged without tests.",
        rationale="Production-Ready Day One philosophy. Prior experience showed untested code caused silent failures in the enrichment pipeline.",
        source_file="docs/PROJECT.md")

    design(conn, "SD:GracefulShutdown",    "Graceful Shutdown via context.Context","Operations",
        "All workers accept context.Context from SIGTERM/SIGINT. In-flight DB transactions and Redis XREADGROUP calls complete before exit. No message is lost or double-processed on restart.",
        rationale="Required for zero-downtime Coolify deployments and safe Redis consumer group drain.",
        source_file="backend/internal/queue")

    design(conn, "SD:RegionalPricing",     "Regional Price Model (US/TR/EU)",   "Pricing",
        "Prices tracked per game/store/region. Scrapers produce region-tagged raw scrapes with native ids and price_cents. Resolver (W06) emits region-keyed prices.update. Worker 10 writes regional current_prices.",
        rationale="TR/EU pricing differs significantly from US. Native ids (appid/offerId) required for adapter resolution; IGDB slugs alone are insufficient.",
        source_file="docs/workflows/regional_scrape_pricing.md")

    design(conn, "SD:NativeIdResolution",  "Native ID Resolution (migration 000060)","Pricing",
        "store_links.store_game_native_id column (planned migration 000060) populated by resolver from scraped native id. Worker 10 resolves via COALESCE(native_id, store_game_id).",
        rationale="GOG/Epic store_links hold IGDB slugs, not native store IDs. The adapter needs the native id (numeric/composite) to fetch live prices.",
        status="proposed",
        source_file="docs/workflows/regional_scrape_pricing.md")

    design(conn, "SD:WorkflowContracts",   "Contract-First Workflow Specs",     "Architecture",
        "Each of the 12 workers is defined by a YAML contract before implementation: stream inputs/outputs, validation rules, retry/DLQ policy, metrics, health checks, acceptance gates.",
        rationale="Contract-first prevents worker drift. YAML contracts are the test oracle for integration tests and the source of truth for dashboards and runbooks.",
        source_file="docs/workflows/README.md")

    design(conn, "SD:HotMediaMirror",      "Hot Deal Image Mirroring",          "Media",
        "Cover and hero images for top-50 hot deals mirrored to Cloudflare R2. IGDB CDN URLs used as fallback. R2 mirrors served for top deals to avoid IGDB rate limits on image delivery.",
        rationale="Serving top-deal images from R2 eliminates IGDB CDN dependency for most-viewed content, reduces latency, avoids hotlinking policy issues at scale.",
        source_file="backend/cmd/hot-media-mirror")

    design(conn, "SD:WishlistAlerts",      "Wishlist Price Alert System",       "User Features",
        "Users set price thresholds per game per region. Alerter monitors current_prices vs thresholds; Mailer sends email when deal hits target. notify_email/notify_push prefs per wishlist entry.",
        rationale="Price threshold alerts are the core retention mechanic — users return when their wishlisted game goes on sale in their preferred region.",
        source_file="backend/internal/wishlist")

    design(conn, "SD:DLQPattern",          "Dead Letter Queue + Replay",        "Data Pipeline",
        "Failed messages land in stream:dlq. DLQ Replay Worker (W12) can replay back into pipeline or finalize (discard) with dlq_replay_audit entry. Scoped replay by stream/timestamp supported.",
        rationale="Without DLQ replay, any transient failure permanently loses scraper data. Audit trail gives operators visibility into replayed/discarded messages.",
        source_file="backend/cmd/dlq-replay")

    design(conn, "SD:OpenCriticFallback",  "OpenCritic Graceful Degradation",  "Data Pipeline",
        "OC enrichment: if 25/day RapidAPI quota is exhausted or API key is missing, log warning and skip OC fields — do not crash the enrichment pipeline or mark game as failed.",
        rationale="OC is secondary data; crashing for 25 OC calls/day would block primary IGDB enrichment. Graceful skip is the correct production tradeoff.",
        source_file="backend/internal/enrichment")

    design(conn, "SD:ConsumerGroups",      "Redis Consumer Group Semantics",    "Data Pipeline",
        "Each worker type has its own consumer group on its input stream. XREADGROUP claims messages; XACK removes from PEL on success; unacknowledged messages are visible to XPENDING for monitoring.",
        rationale="Consumer groups enable multi-instance workers (horizontal scale), crash-safe message ownership, and built-in replay via XCLAIM on stale PEL entries.",
        source_file="backend/internal/queue")

    design(conn, "SD:IdempotentUpsert",    "Idempotent ON CONFLICT Upserts",   "Architecture",
        "All game_library writes use ON CONFLICT(igdb_id) DO UPDATE. store_links, current_prices, itad_bootstrap_runs also use upsert patterns. Workers can be replayed safely.",
        rationale="At-least-once delivery from Redis Streams means workers must be idempotent. Duplicate scrapes or replays from DLQ must not create duplicate rows.",
        source_file="backend/internal/enrichment")

    design(conn, "SD:Observability",       "Prometheus + Grafana Stack",        "Operations",
        "Go workers expose /metrics endpoints. Prometheus scrapes via Alloy. Grafana dashboards: queue depth, worker health, pipeline lag, price update rates, scrape throughput.",
        rationale="Required to detect stuck workers, queue backlog, and price pipeline lag before users notice stale prices. Oncall uses Grafana as primary signal.",
        source_file="observability/")

    # ── NodeGroups ────────────────────────────────────────────────────────────
    print("\n[Groups]")
    node_group(conn, "NG:Scrapers",       "Scrapers",               "Store-facing data harvesters that emit to stream:scrapes:raw", section="Data Pipeline")
    node_group(conn, "NG:IngestResolve",  "Ingest & Resolve",       "W05-W06: validate scrapes, resolve to IGDB catalog, emit prices.update", section="Data Pipeline")
    node_group(conn, "NG:CatalogEnrich",  "Catalog Enrichment",     "W02-W04 + legacy enrichment: IGDB dumps, store links, images, OC", section="Data Pipeline")
    node_group(conn, "NG:PricePipeline",  "Price Pipeline",         "W08-W10: schedule, fetch, and write regional current prices", section="Data Pipeline")
    node_group(conn, "NG:Reliability",    "Reliability Workers",    "W07 ITAD bootstrap, W11 hot media, W12 DLQ replay", section="Operations")
    node_group(conn, "NG:PostgreSQL",     "PostgreSQL Tables",      "All PostgreSQL database tables: catalog, pricing, users, history", section="Storage")
    node_group(conn, "NG:Streams",        "Redis Streams",          "Named Redis streams forming the worker communication bus", section="Data Pipeline")
    node_group(conn, "NG:ExternalAPIs",   "External APIs",          "Third-party APIs and auth providers", section="External")
    node_group(conn, "NG:OpsInfra",       "Ops & Deployment",       "Container orchestration, monitoring, hosting infrastructure", section="Operations")
    node_group(conn, "NG:UserFacing",     "User-Facing Layer",      "Frontend, API, alerting, and edge services", section="Frontend")
    node_group(conn, "NG:ScraperFiles",   "Scraper Source Files",   "Python scraper implementation files", section="Source")
    node_group(conn, "NG:GoSource",       "Go Source Files",        "Backend Go implementation files", section="Source")
    node_group(conn, "NG:Design",         "Architecture Decisions", "System design nodes capturing key architectural choices", section="Architecture")

    # ── Edges ─────────────────────────────────────────────────────────────────
    print("\n[Edges]")

    # Scrape pipeline: scrapers -> stream:raw -> ingestor -> stream:resolver -> resolver -> stream:prices -> price worker
    edge(conn, "Svc:SteamScraper", "TALKS_TO",  "Infra:Stream:Raw")
    edge(conn, "Svc:EpicScraper",  "TALKS_TO",  "Infra:Stream:Raw")
    edge(conn, "Svc:GOGScraper",   "TALKS_TO",  "Infra:Stream:Raw")
    edge(conn, "Svc:ScrapeIngestor","QUERIES",   "Infra:Stream:Raw")
    edge(conn, "Svc:ScrapeIngestor","TALKS_TO",  "Infra:Stream:Resolver")
    edge(conn, "Svc:ScrapeIngestor","STORES_IN", "DB:DLQ")
    edge(conn, "Svc:ScrapeIngestor","STORES_IN", "DB:Scrapes")
    edge(conn, "Svc:GameResolver",  "QUERIES",   "Infra:Stream:Resolver")
    edge(conn, "Svc:GameResolver",  "TALKS_TO",  "Infra:Stream:Prices")
    edge(conn, "Svc:GameResolver",  "STORES_IN", "DB:StoreGames")
    edge(conn, "Svc:GameResolver",  "STORES_IN", "DB:StoreLinks")
    edge(conn, "Svc:GameResolver",  "STORES_IN", "DB:ResolverQueue")
    edge(conn, "Svc:GameResolver",  "QUERIES",   "Infra:IGDB")

    # Price pipeline
    edge(conn, "Svc:Scheduler",     "TALKS_TO",  "Infra:Stream:Raw")
    edge(conn, "Svc:PriceScheduler","TALKS_TO",  "Infra:Redis")
    edge(conn, "Svc:StoreAdapters", "QUERIES",   "Infra:Stream:Prices")
    edge(conn, "Svc:StoreAdapters", "TALKS_TO",  "Infra:Stream:Prices")
    edge(conn, "Svc:PriceUpdater",  "QUERIES",   "Infra:Stream:Prices")
    edge(conn, "Svc:PriceUpdater",  "STORES_IN", "DB:CurrentPrices")
    edge(conn, "Svc:PriceUpdater",  "STORES_IN", "DB:PriceHistory")

    # Catalog enrichment
    edge(conn, "Svc:IGDBDump",      "QUERIES",   "Infra:IGDB")
    edge(conn, "Svc:IGDBDump",      "STORES_IN", "DB:GameLibrary")
    edge(conn, "Svc:IGDBDump",      "STORES_IN", "DB:StoreLinks")
    edge(conn, "Svc:StoreLinkExtract","QUERIES",  "Infra:IGDB")
    edge(conn, "Svc:StoreLinkExtract","STORES_IN","DB:StoreLinks")
    edge(conn, "Svc:ImageIndexer",  "QUERIES",   "Infra:IGDB")
    edge(conn, "Svc:ImageIndexer",  "STORES_IN", "DB:GameLibrary")
    edge(conn, "Svc:EnrichmentWorker","QUERIES",  "DB:StoreGames")
    edge(conn, "Svc:EnrichmentWorker","QUERIES",  "Infra:IGDB")
    edge(conn, "Svc:EnrichmentWorker","QUERIES",  "Infra:OpenCritic")
    edge(conn, "Svc:EnrichmentWorker","STORES_IN","DB:GameLibrary")

    # IGDB auth
    edge(conn, "Infra:IGDB",        "USES",      "Infra:TwitchOAuth")

    # ITAD bootstrap
    edge(conn, "Svc:ITADBootstrap", "QUERIES",   "Infra:ITAD")
    edge(conn, "Svc:ITADBootstrap", "STORES_IN", "DB:PriceHistory")
    edge(conn, "Svc:ITADBootstrap", "STORES_IN", "DB:ITADBootstrap")

    # Hot media
    edge(conn, "Svc:HotMedia",      "QUERIES",   "DB:HotDeals")
    edge(conn, "Svc:HotMedia",      "USES",      "Infra:R2")
    edge(conn, "Svc:HotMedia",      "STORES_IN", "DB:HotMediaMirrors")

    # DLQ
    edge(conn, "Svc:DLQReplay",     "QUERIES",   "DB:DLQ")
    edge(conn, "Svc:DLQReplay",     "TALKS_TO",  "Infra:Stream:DLQ")
    edge(conn, "Svc:DLQReplay",     "STORES_IN", "DB:DLQAudit")

    # Wishlist alerts
    edge(conn, "Svc:Alerter",       "QUERIES",   "DB:CurrentPrices")
    edge(conn, "Svc:Alerter",       "QUERIES",   "DB:Wishlists")
    edge(conn, "Svc:Alerter",       "TALKS_TO",  "Svc:Mailer")

    # API
    edge(conn, "Svc:API",           "QUERIES",   "DB:GameLibrary")
    edge(conn, "Svc:API",           "QUERIES",   "DB:CurrentPrices")
    edge(conn, "Svc:API",           "QUERIES",   "DB:HotDeals")
    edge(conn, "Svc:API",           "QUERIES",   "DB:Wishlists")
    edge(conn, "Svc:API",           "QUERIES",   "DB:Feedback")
    edge(conn, "Svc:API",           "RUNS_ON",   "Infra:Coolify")

    # Frontend
    edge(conn, "Svc:Frontend",      "TALKS_TO",  "Svc:API")
    edge(conn, "Svc:Frontend",      "RUNS_ON",   "Infra:Vercel")

    # Observability
    edge(conn, "Infra:Prometheus",  "QUERIES",   "Svc:API")
    edge(conn, "Infra:Prometheus",  "QUERIES",   "Svc:PriceUpdater")
    edge(conn, "Infra:Grafana",     "QUERIES",   "Infra:Prometheus")

    # DB FK relationships are documented in node descriptions; FK edges omitted (schema type constraint)

    # File IMPLEMENTS
    edge(conn, "File:GoAPI",         "IMPLEMENTS", "Svc:API")
    edge(conn, "File:Router",        "IMPLEMENTS", "Svc:API")
    edge(conn, "File:GameResolver",  "IMPLEMENTS", "Svc:GameResolver")
    edge(conn, "File:PriceUpdater",  "IMPLEMENTS", "Svc:PriceUpdater")
    edge(conn, "File:Enrichment",    "IMPLEMENTS", "Svc:EnrichmentWorker")
    edge(conn, "File:Queue",         "IMPLEMENTS", "Svc:ScrapeIngestor")
    edge(conn, "File:Queue",         "IMPLEMENTS", "Svc:DLQReplay")
    edge(conn, "File:SteamPy",       "IMPLEMENTS", "Svc:SteamScraper")
    edge(conn, "File:EpicPy",        "IMPLEMENTS", "Svc:EpicScraper")
    edge(conn, "File:GOGPy",         "IMPLEMENTS", "Svc:GOGScraper")
    edge(conn, "File:PriceWorkerPy", "IMPLEMENTS", "Svc:PriceWorkerPy")
    edge(conn, "File:Frontend",      "IMPLEMENTS", "Svc:Frontend")
    edge(conn, "File:Workflows",     "IMPLEMENTS", "SD:WorkflowContracts")
    edge(conn, "File:Observability", "IMPLEMENTS", "Infra:Prometheus")
    edge(conn, "File:Observability", "IMPLEMENTS", "Infra:Grafana")
    edge(conn, "File:Migrations",    "MODIFIES",   "DB:GameLibrary")
    edge(conn, "File:Migrations",    "MODIFIES",   "DB:CurrentPrices")
    edge(conn, "File:Migrations",    "MODIFIES",   "DB:StoreLinks")

    # SD IMPLEMENTS
    edge(conn, "SD:RedisStreams",       "USES",      "Infra:Redis")
    edge(conn, "SD:AtomicXACK",         "PART_OF",   "SD:RedisStreams")
    edge(conn, "SD:ConsumerGroups",     "PART_OF",   "SD:RedisStreams")
    edge(conn, "SD:DLQPattern",         "PART_OF",   "SD:RedisStreams")
    edge(conn, "SD:IGDBPrimary",        "USES",      "Infra:IGDB")
    edge(conn, "SD:IGDBPrimary",        "USES",      "Infra:ITAD")
    edge(conn, "SD:EnrichmentBatching", "IMPLEMENTS","Svc:EnrichmentWorker")
    edge(conn, "SD:RegionalPricing",    "IMPLEMENTS","Svc:PriceUpdater")
    edge(conn, "SD:RegionalPricing",    "IMPLEMENTS","Svc:StoreAdapters")
    edge(conn, "SD:NativeIdResolution", "PART_OF",   "SD:RegionalPricing")
    edge(conn, "SD:HotMediaMirror",     "IMPLEMENTS","Svc:HotMedia")
    edge(conn, "SD:WishlistAlerts",     "IMPLEMENTS","Svc:Alerter")
    edge(conn, "SD:WishlistAlerts",     "IMPLEMENTS","Svc:Mailer")
    edge(conn, "SD:DLQPattern",         "IMPLEMENTS","Svc:DLQReplay")
    edge(conn, "SD:IdempotentUpsert",   "IMPLEMENTS","Svc:EnrichmentWorker")
    edge(conn, "SD:IdempotentUpsert",   "IMPLEMENTS","Svc:PriceUpdater")
    edge(conn, "SD:OpenCriticFallback", "PART_OF",   "SD:EnrichmentBatching")
    edge(conn, "SD:TDDMandate",         "USES",      "Infra:Testcontainers")
    edge(conn, "SD:Observability",      "IMPLEMENTS","Infra:Grafana")
    edge(conn, "SD:WorkflowContracts",  "PART_OF",   "SD:RedisStreams")

    # ── MEMBER_OF ─────────────────────────────────────────────────────────────
    print("\n[Group membership]")

    for nid in ["Svc:SteamScraper", "Svc:EpicScraper", "Svc:GOGScraper", "Svc:PriceWorkerPy"]:
        member_of(conn, nid, "NG:Scrapers")

    for nid in ["Svc:ScrapeIngestor", "Svc:GameResolver"]:
        member_of(conn, nid, "NG:IngestResolve")

    for nid in ["Svc:IGDBDump", "Svc:StoreLinkExtract", "Svc:ImageIndexer", "Svc:EnrichmentWorker"]:
        member_of(conn, nid, "NG:CatalogEnrich")

    for nid in ["Svc:Scheduler", "Svc:PriceScheduler", "Svc:StoreAdapters", "Svc:PriceUpdater"]:
        member_of(conn, nid, "NG:PricePipeline")

    for nid in ["Svc:ITADBootstrap", "Svc:HotMedia", "Svc:DLQReplay"]:
        member_of(conn, nid, "NG:Reliability")

    for nid in ["DB:Scrapes", "DB:GameLibrary", "DB:StoreGames", "DB:StoreCovers",
                "DB:PriceHistory", "DB:Wishlists", "DB:CurrentPrices", "DB:StoreLinks",
                "DB:HotDeals", "DB:Feedback", "DB:ResolverQueue", "DB:ITADBootstrap",
                "DB:HotMediaMirrors", "DB:DLQAudit"]:
        member_of(conn, nid, "NG:PostgreSQL")

    for nid in ["Infra:Stream:Raw", "Infra:Stream:Resolver", "Infra:Stream:Prices", "Infra:Stream:DLQ", "DB:DLQ"]:
        member_of(conn, nid, "NG:Streams")

    for nid in ["Infra:IGDB", "Infra:ITAD", "Infra:TwitchOAuth", "Infra:OpenCritic"]:
        member_of(conn, nid, "NG:ExternalAPIs")

    for nid in ["Infra:PostgreSQL", "Infra:Redis", "Infra:R2", "Infra:DockerCompose",
                "Infra:Coolify", "Infra:Vercel", "Infra:Prometheus", "Infra:Grafana",
                "Infra:Testcontainers"]:
        member_of(conn, nid, "NG:OpsInfra")

    for nid in ["Svc:API", "Svc:Frontend", "Svc:Workerd", "Svc:Alerter", "Svc:Mailer"]:
        member_of(conn, nid, "NG:UserFacing")

    for nid in ["File:SteamPy", "File:EpicPy", "File:GOGPy", "File:PriceWorkerPy"]:
        member_of(conn, nid, "NG:ScraperFiles")

    for nid in ["File:GoAPI", "File:Router", "File:GameResolver", "File:PriceUpdater",
                "File:Enrichment", "File:Queue", "File:GoMod", "File:Migrations",
                "File:DockerCompose", "File:Workflows", "File:Frontend",
                "File:Observability", "File:ProjectDoc"]:
        member_of(conn, nid, "NG:GoSource")

    for nid in ["SD:RedisStreams", "SD:AtomicXACK", "SD:IGDBPrimary", "SD:EnrichmentBatching",
                "SD:GoOwnsDB", "SD:TDDMandate", "SD:GracefulShutdown", "SD:RegionalPricing",
                "SD:NativeIdResolution", "SD:WorkflowContracts", "SD:HotMediaMirror",
                "SD:WishlistAlerts", "SD:DLQPattern", "SD:OpenCriticFallback",
                "SD:ConsumerGroups", "SD:IdempotentUpsert", "SD:Observability"]:
        member_of(conn, nid, "NG:Design")

    print("\n[Snapshot]")
    entry = mgr.commit_snapshot("Full ArgusOne graph: workflows, groups, all 12 workers")
    print(f"  Snapshot: slot={entry['slot']}")

    mgr.close()

    # Count nodes
    from core.graph_api import NODE_TABLES
    mgr2 = DatabaseManager(root)
    mgr2.init()
    total = 0
    for t in NODE_TABLES:
        try:
            r = mgr2.conn.execute(f"MATCH (n:{t}) RETURN count(*) AS c")
            if r.has_next():
                n = r.get_next()[0]
                total += n
                if n:
                    print(f"  {t}: {n}")
        except Exception:
            pass
    mgr2.close()
    print(f"\nDone. {total} nodes total.")


if __name__ == "__main__":
    main()
