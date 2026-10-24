"""Build a static copy of the console for GitHub Pages (front end only, no server).

Run:  python -m web.build_static site   (after `python run_pipeline.py`)

Every GET endpoint of web/server.py is called once and saved as a .json file
next to the page, so the same app.js works without Flask. Ad-hoc SQL runs in
the browser on a copy of the SQLite file (sql.js).
"""
import shutil
import sys
from pathlib import Path

from src.config import DB_PATH, OUTPUT_DIR
from web.server import STATIC_DIR, _plotly_source, app, sql_files

SQL_JS = "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js"
ENDPOINTS = ["/api/summary", "/api/leads", "/api/config", "/api/journeys", "/api/outbox", "/api/sql"]


def build(out: Path) -> None:
    if not DB_PATH.exists():
        sys.exit("No database yet - run `python run_pipeline.py` first.")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC_DIR, out / "static")

    client = app.test_client()
    for endpoint in ENDPOINTS + [f"/api/sql/{name}" for name in sql_files()]:
        resp = client.get(endpoint)
        if resp.status_code != 200:
            sys.exit(f"{endpoint} returned HTTP {resp.status_code}")
        target = out / f"{endpoint.lstrip('/')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(resp.data)

    (out / "plotly.js").write_text(_plotly_source(), encoding="utf-8")
    shutil.copy(DB_PATH, out / "growth_ops.db")
    if (OUTPUT_DIR / "dashboard.html").exists():
        shutil.copy(OUTPUT_DIR / "dashboard.html", out / "report.html")

    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("</head>", f'<script>window.STATIC_SITE = true;</script>\n'
                                   f'<script src="{SQL_JS}"></script>\n</head>')
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").touch()  # serve files as-is (no Jekyll processing)
    print(f"static site written to {out}/ - open it with: python -m http.server -d {out}")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "site"))
