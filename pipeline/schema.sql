CREATE TYPE IF NOT EXISTS stage_enum AS ENUM (
    'applied',
    'screening',
    'interview_1',
    'interview_2',
    'interview_3',
    'offer',
    'rejection',
    'recruiter_outreach',
    'ghosted'
);

CREATE TYPE IF NOT EXISTS outcome_enum AS ENUM (
    'pending',
    'rejected',
    'offer_received',
    'offer_accepted',
    'offer_declined',
    'withdrew',
    'ghosted'
);

CREATE TYPE IF NOT EXISTS classification_method_enum AS ENUM (
    'regex',
    'heuristic',
    'llm_single',
    'llm_thread',
    'manual'
);

CREATE TABLE IF NOT EXISTS job_emails (
    email_id                 TEXT PRIMARY KEY,
    thread_id                TEXT NOT NULL,
    company                  TEXT,
    role                     TEXT,
    stage                    stage_enum,
    outreach_type            TEXT,
    is_spam                  BOOLEAN DEFAULT FALSE,
    is_recruiter_inbound     BOOLEAN DEFAULT FALSE,
    received_date            TIMESTAMP NOT NULL,
    subject                  TEXT,
    sender                   TEXT NOT NULL,
    calendar_invite_detected BOOLEAN DEFAULT FALSE,
    confidence_score         DECIMAL(3,2),
    classification_method    classification_method_enum,
    raw_content              TEXT,
    extracted_data           JSON,
    processed_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_reclassified_at     TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS job_threads (
    thread_id     TEXT PRIMARY KEY,
    company       TEXT,
    role          TEXT,
    current_stage stage_enum,
    stage_history JSON,
    first_contact TIMESTAMP,
    last_contact  TIMESTAMP,
    is_active     BOOLEAN DEFAULT TRUE,
    total_emails  INTEGER DEFAULT 0,
    outcome       outcome_enum DEFAULT 'pending'
);
