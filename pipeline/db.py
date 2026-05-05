"""
Database connection helpers for the job-application email pipeline.

confidence_score convention:
  1.0   — regex / deterministic classification (exact match, no uncertainty)
  0–1.0 — LLM classification (model's self-reported confidence)
  NULL  — email has not yet been classified
"""

from contextlib import contextmanager
from pathlib import Path

import duckdb

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path))


def init_schema(conn) -> None:
    sql = _SCHEMA_PATH.read_text()
    for statement in sql.split(";"):
        stmt = statement.strip()
        if stmt:
            conn.execute(stmt)


@contextmanager
def connection(db_path):
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()
