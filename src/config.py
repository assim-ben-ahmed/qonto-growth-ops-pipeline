"""Paths and config loading shared by every pipeline step."""
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = ROOT / "output"
SQL_DIR = ROOT / "sql"
DB_PATH = DATA_DIR / "growth_ops.db"


def load_config() -> dict[str, Any]:
    """Load config.yaml and the optional .env file (for MISTRAL_API_KEY)."""
    load_dotenv(ROOT / ".env")
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs() -> None:
    """Create the local data/output folders (they are gitignored)."""
    for d in (RAW_DIR, CACHE_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
