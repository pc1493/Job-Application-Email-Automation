# Project Context — Job Application Email Automation

_Generated 2026-05-05. Pass this file to Opus when writing specs 02 and 03._

---

## What this project is

A Python pipeline that reads Gmail, classifies job-application emails using the
Claude API, and writes structured records to a local DuckDB database. Read-only
against Gmail. No web UI — SQL queries are the interface.

**User:** Peter Chen — peterchen.ba@gmail.com  
**Phase now:** Phase 1 (historical fetch + classify + store, manual verification)

---

## Stack

| Component | Library / Tool | Notes |
|---|---|---|
| Language | Python 3.11 | Runs inside Docker (node:20 base) |
| Gmail read | google-api-python-client + google-auth-oauthlib | OAuth2 credentials in `creds/` (gitignored) |
| LLM classification | Anthropic Python SDK (`anthropic>=0.25.0`) | Model: Claude Sonnet 4. Key in `.env` as `ANTHROPIC_API_KEY` |
| Storage | DuckDB (`duckdb>=0.10.0`) | Local file at `data/emails.duckdb` (gitignored) |
| Env vars | python-dotenv | `.env` at project root (gitignored) |
| Tests | pytest (not in requirements.txt yet — was used, assumed available) | `tmp_path` fixture for all DB tests |
| Container | Docker, node:20 base + Python 3.11, Claude Code CLI installed | `build.ps1` / `run.ps1` for Windows host |

---

## What is already built (Spec 01 — complete)

### `pipeline/schema.sql`
DDL for two tables and three ENUM types:

**ENUMs:**
- `stage_enum`: applied, screening, interview_1, interview_2, interview_3, offer, rejection, recruiter_outreach, ghosted
- `outcome_enum`: pending, rejected, offer_received, offer_accepted, offer_declined, withdrew, ghosted
- `classification_method_enum`: regex, heuristic, llm_single, llm_thread, manual

**`job_emails` table** — one row per email:

| Column | Type | Notes |
|---|---|---|
| email_id | TEXT PK | Gmail message ID |
| thread_id | TEXT NOT NULL | Gmail thread ID |
| company | TEXT | Extracted by classifier |
| role | TEXT | Extracted by classifier |
| stage | stage_enum | Classified stage |
| outreach_type | TEXT | Free text (e.g. "inbound recruiter") |
| is_spam | BOOLEAN DEFAULT FALSE | |
| is_recruiter_inbound | BOOLEAN DEFAULT FALSE | |
| received_date | TIMESTAMP NOT NULL | |
| subject | TEXT | |
| sender | TEXT NOT NULL | |
| calendar_invite_detected | BOOLEAN DEFAULT FALSE | |
| confidence_score | DECIMAL(3,2) | NULL=unclassified; 1.0=regex; 0–1.0=LLM self-reported |
| classification_method | classification_method_enum | |
| raw_content | TEXT | Do NOT log to stdout/files |
| extracted_data | JSON | LLM structured output |
| processed_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |
| last_reclassified_at | TIMESTAMP NULL | |

**`job_threads` table** — one row per Gmail thread (aggregated view):

| Column | Type | Notes |
|---|---|---|
| thread_id | TEXT PK | |
| company | TEXT | |
| role | TEXT | |
| current_stage | stage_enum | Latest stage in thread |
| stage_history | JSON | Ordered list of stage transitions |
| first_contact | TIMESTAMP | |
| last_contact | TIMESTAMP | |
| is_active | BOOLEAN DEFAULT TRUE | |
| total_emails | INTEGER DEFAULT 0 | |
| outcome | outcome_enum DEFAULT 'pending' | |

### `pipeline/db.py`
Three public symbols:

```python
def get_connection(db_path) -> duckdb.DuckDBPyConnection
def init_schema(conn) -> None          # reads schema.sql, idempotent
@contextmanager def connection(db_path) # yields conn, guarantees close
```

`confidence_score` convention (from module docstring):
- `1.0` — regex/deterministic (exact match, no uncertainty)
- `0–1.0` — LLM classification (model's self-reported confidence)
- `NULL` — not yet classified

### `tests/test_schema.py`
9 passing pytest tests covering: table existence, enum existence, idempotency,
exact column/type sets for both tables, PK violations, invalid enum rejection,
outcome default.

---

## What does NOT exist yet

- `pipeline/fetcher.py` — Gmail API fetch (Spec 02)
- `pipeline/classifier.py` — Claude API classification (Spec 03)
- `pipeline/orchestrator.py` — wires fetcher → classifier → DB write (likely Spec 04 or 05)
- Any `.env` or `creds/` content (user-managed, gitignored)
- `data/emails.duckdb` (runtime artifact, gitignored)
- Thread-level aggregation logic

---

## Key constraints for all future specs

1. **Never log raw email bodies** to stdout or files. Personal data.
2. **Confidence threshold:** auto-classify at ≥ 0.85; below that, flag for human review (leave `classification_method = NULL` or set a `needs_review` flag — TBD in spec).
3. **API key:** `ANTHROPIC_API_KEY` from `.env` only. Never hardcode.
4. **No new dependencies** without explicit spec approval. Current `requirements.txt`:
   - anthropic>=0.25.0
   - google-api-python-client>=2.120.0
   - google-auth-oauthlib>=1.2.0
   - google-auth-httplib2>=0.2.0
   - duckdb>=0.10.0
   - python-dotenv>=1.0.0
5. **pytest** is not in requirements.txt but is assumed available (installed separately in the container).
6. **DB path** at runtime: `data/emails.duckdb`. Tests always use `tmp_path`.
7. **Idempotent inserts** — the fetcher will be re-run; it must not duplicate rows. `email_id` is the Gmail message ID and the PK.
8. **Docker / POSIX paths only** — no Windows paths in generated code.

---

## Project file tree (relevant files only)

```
/workspace/
├── CLAUDE.md                    # Project rules (read this first)
├── DECISIONS.md                 # This file
├── requirements.txt             # Python deps (see above)
├── Dockerfile                   # node:20 + Python 3.11 + Claude Code CLI
├── entrypoint.sh                # Sets git config, optionally loads GITHUB_TOKEN
├── build.ps1 / run.ps1          # Windows host scripts to build/run Docker
├── .claude/settings.json        # {"permissions": {"defaultMode": "bypassPermissions"}}
├── pipeline/
│   ├── schema.sql               # DuckDB DDL — source of truth for schema
│   └── db.py                    # get_connection, init_schema, connection()
├── specs/
│   ├── _template.md             # Standard spec template
│   └── 01-duckdb-schema.md      # Spec 01 (complete)
├── tests/
│   └── test_schema.py           # 9 passing tests for schema/db
├── data/                        # gitignored — runtime DB lives here
├── logs/                        # gitignored — future event logs
└── creds/                       # gitignored — OAuth2 credentials
```

---

## Likely shape of Spec 02 (Gmail fetcher)

Goal: fetch historical emails from Gmail, write raw metadata + body to `job_emails`.

Key decisions to resolve in spec:
- **Search query:** what Gmail search string identifies job-application emails? (e.g. label-based, keyword-based, or broad + classifier-filters-later)
- **Fetch scope:** how far back historically? All mail, or a date range?
- **Fields to pull from Gmail API:** `id`, `threadId`, `payload.headers` (From, Subject, Date), `payload.body` or `snippet`
- **Partial body extraction:** full body vs. snippet — impacts classifier quality
- **Upsert vs. skip on duplicate:** email_id PK exists; insert-or-ignore is the safe default
- **OAuth flow:** credentials path (`creds/token.json`, `creds/credentials.json`), scopes needed (`https://www.googleapis.com/auth/gmail.readonly`)
- **Output:** rows inserted into `job_emails` with `confidence_score = NULL`, `classification_method = NULL`

---

## Likely shape of Spec 03 (LLM classifier)

Goal: for each unclassified email in `job_emails`, call Claude API to extract
`company`, `role`, `stage`, `is_recruiter_inbound`, `calendar_invite_detected`,
`confidence_score`, and write results back.

Key decisions to resolve in spec:
- **Prompt design:** what fields does the LLM extract? JSON schema for structured output.
- **Batching:** one API call per email, or thread-level batching (all emails in a thread as context)?
- **Confidence threshold:** 0.85 cutoff is defined in CLAUDE.md. Below threshold → what field/flag?
- **Retry / error handling:** transient API errors vs. permanent failures
- **Rate limiting:** Gmail returns up to ~500 messages; Claude API has TPM limits
- **Thread rollup:** after classifying individual emails, update `job_threads` table
- **classification_method value:** `llm_single` for per-email, `llm_thread` for thread-context calls

---

## Methodology reminders (from ~/.claude/methodology.md)

- Every task needs a spec before code is written. Spec is the contract.
- One spec = one verifiable artifact (a file, a module, a test suite).
- Subagents get: the spec + referenced instruction files + only needed input artifacts.
- Agent must not guess. If uncertain → `TODO` comment + stop + escalate.
- Max 2–3 correction iterations before escalating to human.
- Human verification gate before declaring spec complete or moving to next spec.
