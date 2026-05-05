import pytest

from pipeline.db import get_connection, init_schema


@pytest.fixture
def conn(tmp_path):
    c = get_connection(tmp_path / "test.duckdb")
    init_schema(c)
    yield c
    c.close()


def _columns(conn, table_name):
    rows = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table_name],
    ).fetchall()
    return {name: dtype for name, dtype in rows}


def test_init_creates_both_tables(conn):
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    assert "job_emails" in tables
    assert "job_threads" in tables


def test_init_creates_three_enums(conn):
    type_names = {
        r[0]
        for r in conn.execute(
            "SELECT type_name FROM duckdb_types() WHERE logical_type = 'ENUM'"
        ).fetchall()
    }
    assert "stage_enum" in type_names
    assert "outcome_enum" in type_names
    assert "classification_method_enum" in type_names


def test_init_is_idempotent(conn):
    init_schema(conn)


_STAGE_TYPE = "ENUM('applied', 'screening', 'interview_1', 'interview_2', 'interview_3', 'offer', 'rejection', 'recruiter_outreach', 'ghosted')"
_OUTCOME_TYPE = "ENUM('pending', 'rejected', 'offer_received', 'offer_accepted', 'offer_declined', 'withdrew', 'ghosted')"
_METHOD_TYPE = "ENUM('regex', 'heuristic', 'llm_single', 'llm_thread', 'manual')"


def test_job_emails_has_expected_columns(conn):
    assert _columns(conn, "job_emails") == {
        "email_id":                 "VARCHAR",
        "thread_id":                "VARCHAR",
        "company":                  "VARCHAR",
        "role":                     "VARCHAR",
        "stage":                    _STAGE_TYPE,
        "outreach_type":            "VARCHAR",
        "is_spam":                  "BOOLEAN",
        "is_recruiter_inbound":     "BOOLEAN",
        "received_date":            "TIMESTAMP",
        "subject":                  "VARCHAR",
        "sender":                   "VARCHAR",
        "calendar_invite_detected": "BOOLEAN",
        "confidence_score":         "DECIMAL(3,2)",
        "classification_method":    _METHOD_TYPE,
        "raw_content":              "VARCHAR",
        "extracted_data":           "JSON",
        "processed_at":             "TIMESTAMP",
        "last_reclassified_at":     "TIMESTAMP",
    }


def test_job_threads_has_expected_columns(conn):
    assert _columns(conn, "job_threads") == {
        "thread_id":     "VARCHAR",
        "company":       "VARCHAR",
        "role":          "VARCHAR",
        "current_stage": _STAGE_TYPE,
        "stage_history": "JSON",
        "first_contact": "TIMESTAMP",
        "last_contact":  "TIMESTAMP",
        "is_active":     "BOOLEAN",
        "total_emails":  "INTEGER",
        "outcome":       _OUTCOME_TYPE,
    }


def test_pk_constraint_on_email_id(conn):
    conn.execute(
        "INSERT INTO job_emails (email_id, thread_id, received_date, sender) "
        "VALUES ('id1', 't1', NOW(), 'a@b.com')"
    )
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO job_emails (email_id, thread_id, received_date, sender) "
            "VALUES ('id1', 't2', NOW(), 'c@d.com')"
        )


def test_pk_constraint_on_thread_id(conn):
    conn.execute("INSERT INTO job_threads (thread_id) VALUES ('t1')")
    with pytest.raises(Exception):
        conn.execute("INSERT INTO job_threads (thread_id) VALUES ('t1')")


def test_stage_enum_rejects_invalid_value(conn):
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO job_emails (email_id, thread_id, received_date, sender, stage) "
            "VALUES ('id1', 't1', NOW(), 'a@b.com', 'nonsense')"
        )


def test_outcome_enum_defaults_to_pending(conn):
    conn.execute("INSERT INTO job_threads (thread_id) VALUES ('t1')")
    result = conn.execute(
        "SELECT outcome FROM job_threads WHERE thread_id = 't1'"
    ).fetchone()
    assert result[0] == "pending"
