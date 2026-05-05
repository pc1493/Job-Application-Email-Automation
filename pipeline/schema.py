import duckdb


def create_schema(db_path: str) -> None:
    conn = duckdb.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                email_id     TEXT         PRIMARY KEY,
                thread_id    TEXT         NOT NULL,
                from_address TEXT         NOT NULL,
                from_name    TEXT,
                subject      TEXT,
                received_at  TIMESTAMPTZ  NOT NULL,
                snippet      TEXT,
                gmail_labels TEXT[],
                fetched_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS classified_emails (
                email_id          TEXT         PRIMARY KEY,
                category          TEXT         NOT NULL
                                      CHECK (category IN (
                                          'application', 'recruiter_outreach',
                                          'interview_invite', 'rejection',
                                          'offer', 'other'
                                      )),
                confidence        FLOAT        NOT NULL,
                company_name      TEXT,
                job_title         TEXT,
                needs_review      BOOLEAN      NOT NULL,
                llm_response_json TEXT,
                classified_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
                model_used        TEXT         NOT NULL
            )
        """)
    finally:
        conn.close()
