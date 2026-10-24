"""Single entry point: python run_pipeline.py  (or --stage ingest|enrich|score|validate|ai|outbox|report)."""
import argparse
import logging
from datetime import datetime, timezone

from src import ai_notes, db, enrich, ingest, outbox, outcomes, report, route, tracking
from src.api_client import CompanyApiClient
from src.config import CACHE_DIR, DB_PATH, OUTPUT_DIR, ensure_dirs, load_config

STAGES = ["ingest", "enrich", "score", "validate", "ai", "outbox", "report"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Qonto growth-ops pipeline")
    parser.add_argument("--stage", choices=STAGES + ["all"], default="all")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    log = logging.getLogger("pipeline")
    cfg = load_config()
    ensure_dirs()
    conn = db.connect(DB_PATH)
    api = cfg["api"]
    client = CompanyApiClient(api["base_url"], CACHE_DIR, api["max_requests_per_second"],
                              api["timeout_seconds"], api["max_retries"])
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

    def wanted(stage: str) -> bool:
        return args.stage in (stage, "all")

    def companies() -> dict[str, dict]:
        return {r["siren"]: dict(r) for r in conn.execute("SELECT * FROM companies")}

    if wanted("ingest"):
        events = ingest.run(client, cfg, now)
        calls = tracking.run(events, cfg, now)
        # The simulated stream is regenerated from scratch, so drop the previous one.
        for table in ("events", "web_events"):
            conn.execute(f"DELETE FROM {table}")
        db.upsert(conn, "events", [ingest.event_to_row(e) for e in events])
        db.upsert(conn, "web_events", [tracking.to_row(c, cfg["channels"]) for c in calls])
    else:
        events = ingest.load_events()

    if wanted("enrich"):
        db.upsert(conn, "companies", enrich.run(client, events))

    if wanted("score"):
        old_notes = {r["siren"]: dict(r) for r in conn.execute("SELECT * FROM crm_leads")}
        # Full refresh of routing outputs: a lead that cooled down must leave the CRM table.
        for table in ("scored_leads", "crm_leads", "braze_nurture"):
            conn.execute(f"DELETE FROM {table}")
        tables = route.run(events, companies(), cfg)
        kept = route.carry_over_notes(tables["crm_leads"], old_notes)
        if kept and not wanted("ai"):
            log.info("kept %d existing AI notes - run --stage ai to refresh them", kept)
        for table, rows in tables.items():
            db.upsert(conn, table, rows)
            if table == "braze_nurture":
                route.write_braze_csv(rows, OUTPUT_DIR / "braze_nurture.csv")

    if wanted("validate"):
        conn.execute("DELETE FROM outcomes")
        db.upsert(conn, "outcomes", outcomes.run(events, companies(), cfg))
        pairs = conn.execute("SELECT s.score, o.converted FROM scored_leads s "
                             "JOIN outcomes o ON o.siren = s.siren").fetchall()
        log.info("score AUC on simulated outcomes: %s (0.5 = random, 1 = perfect)",
                 outcomes.auc([p[0] for p in pairs], [p[1] for p in pairs]))

    if wanted("ai"):
        leads = [dict(r) for r in conn.execute("SELECT * FROM crm_leads")]
        plans = {e["properties"]["siren"]: e["properties"]["plan_chosen"] for e in events}
        db.upsert(conn, "crm_leads", ai_notes.run(leads, companies(), plans, cfg))

    if wanted("outbox"):
        outbox.run(conn, OUTPUT_DIR / "outbox", now)

    if wanted("report"):
        report.run(conn, cfg, OUTPUT_DIR / "dashboard.html")

    log.info("done - API stats: %s", client.stats)


if __name__ == "__main__":
    main()
