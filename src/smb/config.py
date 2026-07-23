"""Shared paths and constants for the local (DuckDB) prototype."""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
WAREHOUSE = os.path.join(DATA_DIR, "warehouse.duckdb")
MODELS_DIR = os.path.join(ROOT, "src", "smb", "pipeline", "models")
REPORTS_DIR = os.path.join(ROOT, "reports")

RAW_EVENTS = os.path.join(RAW_DIR, "events", "events.parquet")

LAYERS = ["staging", "intermediate", "marts"]
