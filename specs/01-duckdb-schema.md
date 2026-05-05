# Task: DuckDB schema and connection helper

## Context
Foundational chunk for the job-tracker pipeline. Every downstream chunk
(fetcher writes raw email metadata, classifier writes extracted fields,
thread analyzer writes stage history) depends on this schema being locked.
Phase 1 of the project — manual verification, no hooks yet.

Schema lives as raw SQL in `pipeline/schema.sql` so it's inspectable
without running Python. Three ENUM types are defined to catch typos at
insert time for fields with known vocabularies (stage, outcome,
classification_method).

## Required instruction files
@~/.claude/methodology.md
@/workspace/CLAUDE.md

## Inputs
None. This is the foundation chunk. Earlier exploration notes (if present
in `notes/`) describe target tables informally — treat as background, not
authoritative. This spec is the source of truth.

## Goal
A Python module that creates and initializes two DuckDB tables plus three
ENUM types, idempotent on repeat runs, with a passing pytest suite
verifying schema integrity.

## Steps

1. Create `pipeline/schema.sql` with the following, in order:

   ENUM types (use `CREATE TYPE IF NOT EXISTS` — DuckDB supports this):

   `stage_enum`:
     - 'applied'
     - 'screening'
     - 'interview_1'
     - 'interview_2'
     - 'interview_3'
     - 'offer'
     - 'rejection'
     - 'recruiter_outreach'
     - 'ghosted'

   `outcome_enum`:
     - 'pending'
     - 'rejected'
     - 'offer_received'
     - 'offer_accepted'
     - 'offer_declined'
     - 'withdrew'
     - 'ghosted'

   `classification_method_enum`:
     - 'regex'
     - 'heuristic'
     - 'llm_single'
     - 'llm_thread'
     - 'manual'

   Then `CREATE TABLE IF NOT EXISTS job_emails`:
     - email_id TEXT PRIMARY KEY
     - thread_id TEXT NOT NULL
     - company TEXT
     - role TEXT
     - stage stage_enum
     - outreach_type TEXT
     - is_spam BOOLEAN DEFAULT FALSE
     - is_recruiter_inbound BOOLEAN DEFAULT FALSE
     - received_date TIMESTAMP NOT NULL
     - subject TEXT
     - sender TEXT NOT NULL
     - calendar_invite_detected BOOLEAN DEFAULT FALSE
     - confidence_score DECIMAL(3,2)
     - classification_method classification_method_enum
     - raw_content TEXT
     - extracted_data JSON
     - processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
     - last_reclassified_at TIMESTAMP NULL

   Then `CREATE TABLE IF NOT EXISTS job_threads`:
     - thread_id TEXT PRIMARY KEY
     - company TEXT
     - role TEXT
     - current_stage stage_enum
     - stage_history JSON
     - first_contact TIMESTAMP
     - last_contact TIMESTAMP
     - is_active BOOLEAN DEFAULT TRUE
     - total_emails INTEGER DEFAULT 0
     - outcome outcome_enum DEFAULT 'pending'

2. Create `pipeline/db.py` exposing:
     - `get_connection(db_path: str | Path) -> duckdb.DuckDBPyConnection`
     - `init_schema(conn) -> None` — reads `schema.sql`, executes statements
     - `connection(db_path)` — context manager wrapping `get_connection`,
       guarantees `conn.close()` on exit (including on exception)

   Module docstring must document the `confidence_score` convention:
   regex / deterministic hits use 1.0; LLM hits use the model's
   self-reported confidence; NULL when not yet classified.

3. Create `tests/test_schema.py` with these pytest tests. Use the
   `tmp_path` fixture for the DB file in every test — never hit a shared
   DB or write to `data/`:

     - `test_init_creates_both_tables` — after `init_schema`, both tables
       appear in `information_schema.tables`
     - `test_init_creates_three_enums` — query `pg_catalog.pg_type` (or
       DuckDB's equivalent) and confirm `stage_enum`, `outcome_enum`,
       `classification_method_enum` exist
     - `test_init_is_idempotent` — running `init_schema` twice on the
       same connection does not raise
     - `test_job_emails_has_expected_columns` — introspect via
       `information_schema.columns`, assert exact column name + type
       set matches the spec (no extras, no omissions)
     - `test_job_threads_has_expected_columns` — same, for job_threads
     - `test_pk_constraint_on_email_id` — inserting two rows with the
       same `email_id` raises a constraint violation
     - `test_pk_constraint_on_thread_id` — same, for job_threads
     - `test_stage_enum_rejects_invalid_value` — inserting a row with
       `stage='nonsense'` raises
     - `test_outcome_enum_defaults_to_pending` — inserting a thread
       without specifying outcome yields `outcome='pending'`

4. Run `pytest tests/test_schema.py -v`. On failure, iterate per
   methodology §7 (max 2–3 iterations before escalation).

5. Smoke-test outside pytest:
``python -c "from pipeline.db import connection, init_schema; 
import pathlib; p=pathlib.Path('data/smoke.duckdb'); 
p.unlink(missing_ok=True); 
p.parent.mkdir(exist_ok=True); 
c = import('pipeline.db', fromlist=['connection']).connection(p); 
ctx = c.enter(); init_schema(ctx); print('ok'); c.exit(None,None,None)"
   Expected output: `ok`. Then delete `data/smoke.duckdb`.``

## Output
- `pipeline/schema.sql` — DDL for three enums and two tables, human-readable
- `pipeline/db.py` — connection helper, context manager, init_schema,
  with the `confidence_score` convention documented in the module docstring
- `tests/test_schema.py` — 9 passing tests

## Acceptance criteria
- [ ] All 9 tests in `tests/test_schema.py` pass with `pytest -v`
- [ ] `init_schema()` is idempotent (verified by `test_init_is_idempotent`)
- [ ] All columns, types, enums, and defaults in `pipeline/schema.sql`
      exactly match this spec (no extras, no omissions, no renaming)
- [ ] Smoke test from Step 5 prints `ok` and exits 0
- [ ] No new dependencies added beyond `duckdb` and `pytest` — verify
      against `requirements.txt`, do not assume
- [ ] `pipeline/db.py` module docstring documents the `confidence_score`
      convention

## Out of scope
- Do NOT add migration tooling (alembic, dbt, etc.). `schema.sql` is
  migration v1; future schema changes will be handled when needed.
- Do NOT add seed data or sample rows.
- Do NOT add indexes. DuckDB is columnar; revisit only if a real query
  feels slow.
- Do NOT write the fetcher, classifier, thread analyzer, or orchestrator
  — those are separate tasks (02–05).
- Do NOT introduce an ORM (SQLAlchemy, SQLModel, etc.). Raw DuckDB API only.
- Do NOT add logging beyond letting connection errors propagate naturally.
- Do NOT modify `CLAUDE.md`, `methodology.md`, or this spec file.
- Do NOT add type-checking config (mypy, pyright config files) — out of
  scope for this chunk.
- Do NOT add a CLI, argparse, or `__main__` block to `pipeline/db.py`.
  It is a library module only.