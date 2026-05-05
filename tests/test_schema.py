import duckdb
import pytest

from pipeline.schema import create_schema


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.duckdb")


def _column_names(conn, table_name):
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table_name],
    ).fetchall()
    return {r[0] for r in rows}


def test_tables_created(db_path):
    create_schema(db_path)
    conn = duckdb.connect(db_path)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    conn.close()
    assert "emails" in tables
    assert "classified_emails" in tables


def test_emails_columns(db_path):
    create_schema(db_path)
    conn = duckdb.connect(db_path)
    cols = _column_names(conn, "emails")
    conn.close()
    assert cols == {
        "email_id", "thread_id", "from_address", "from_name",
        "subject", "received_at", "snippet", "gmail_labels", "fetched_at",
    }


def test_classified_emails_columns(db_path):
    create_schema(db_path)
    conn = duckdb.connect(db_path)
    cols = _column_names(conn, "classified_emails")
    conn.close()
    assert cols == {
        "email_id", "category", "confidence", "company_name", "job_title",
        "needs_review", "llm_response_json", "classified_at", "model_used",
    }


def test_idempotent(db_path):
    create_schema(db_path)
    create_schema(db_path)


def test_category_check_constraint(db_path):
    create_schema(db_path)
    conn = duckdb.connect(db_path)
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO classified_emails "
            "VALUES (?, ?, ?, ?, ?, ?, ?, now(), ?)",
            ["id1", "invalid_category", 0.9, None, None, False, None, "claude-sonnet-4-6"],
        )
    conn.close()
