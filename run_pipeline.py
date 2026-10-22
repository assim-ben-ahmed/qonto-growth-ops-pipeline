"""Single entry point: python run_pipeline.py  (or --stage ingest|enrich|score|ai|report)."""
import argparse
import logging

from src import ai_notes, db, enrich, ingest, report, route
from src.api_client import CompanyApiClient
from src.config import CACHE_DIR, DB_PATH, OUTPUT_DIR, ensure_dirs, load_config

STAGES = ["ingest", "enrich", "score", "ai", "report"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Qonto growth-ops pipeline")
    parser.add_argument("--stage", choices=STAGES + ["all"], default="all")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cfg = load_config()
    ensure_dirs()
    conn = db.connect(DB_PATH)
    api = cfg["api"]
    client = CompanyApiClient(api["base_url"], CACHE_DIR, api["max_requests_per_second"],
                              api["timeout_seconds"], api["max_retries"])

    def wanted(stage: str) -> bool:
        return args.stage in (stage, "all")

    if wanted("ingest"):
        events = ingest.run(client, cfg)
        db.upsert(conn, "events", [ingest.event_to_row(e) for e in events])
    else:
        events = ingest.load_events()

    if wanted("enrich"):
        db.upsert(conn, "companies", enrich.run(client, events))

    if wanted("score"):
        companies = {r["siren"]: dict(r) for r in conn.execute("SELECT * FROM companies")}
        # Full refresh of routing outputs: a lead that cooled down must leave the CRM table.
        for table in ("scored_leads", "crm_leads", "braze_nurture"):
            conn.execute(f"DELETE FROM {table}")
        for table, rows in route.run(events, companies, cfg).items():
            db.upsert(conn, table, rows)
            if table == "braze_nurture":
                route.write_braze_csv(rows, OUTPUT_DIR / "braze_nurture.csv")

    if wanted("ai"):
        companies = {r["siren"]: dict(r) for r in conn.execute("SELECT * FROM companies")}
        leads = [dict(r) for r in conn.execute("SELECT * FROM crm_leads")]
        plans = {e["properties"]["siren"]: e["properties"]["plan_chosen"] for e in events}
        db.upsert(conn, "crm_leads", ai_notes.run(leads, companies, plans, cfg))

    if wanted("report"):
        report.run(conn, cfg, OUTPUT_DIR / "dashboard.html")

    logging.getLogger("pipeline").info("done - API stats: %s", client.stats)


if __name__ == "__main__":
    main()
