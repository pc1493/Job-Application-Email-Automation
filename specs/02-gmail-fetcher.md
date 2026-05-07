# Task: Gmail historical fetcher

## Context
Second chunk in Phase 1. With the schema locked by spec 01, this chunk
populates `job_emails` with raw email metadata + body content from Gmail.
No classification happens here — every fetched row is inserted with
`confidence_score = NULL` and `classification_method = NULL`. Classification
is owned by spec 03.

Per #010, the fetcher is intentionally dumb: it does not try to filter for
job-related content. Per #011, the all-time backfill is justified because
spec 03's stage-1 heuristics will eliminate the obviously-irrelevant majority
before any LLM cost is incurred. Per #007, OAuth scope is `gmail.readonly` —
read-only, no labels modified. Per #002, Gmail's message ID is the primary
key, so re-runs are idempotent via `INSERT ... ON CONFLICT DO NOTHING`.
Per #006, raw email bodies are never written to logs or stdout.

## Required instruction files
@~/.claude/methodology.md
@/workspace/CLAUDE.md
@/workspace/DECISIONS.md  (specifically #002, #006, #007, #010, #011)
@/workspace/pipeline/schema.sql  (column contract — do not modify)
@/workspace/pipeline/db.py  (connection + init_schema helpers)

## Inputs
- `creds/credentials.json` — OAuth2 installed-app client secret JSON,
  downloaded from Google Cloud Console. Already present in repo.
- `pipeline/schema.sql` and `pipeline/db.py` — the database contract from
  spec 01. Read-only.
- `data/emails.duckdb` — DuckDB file. May or may not exist; the fetcher
  calls `init_schema` on startup (idempotent per spec 01).

## Goal
A fetcher module that, when run, retrieves all received Gmail messages for
the configured account, upserts them into `job_emails` with NULL
classification fields, and writes a per-run log of message metadata (no
bodies) to a timestamped file under `logs/`.

## Steps

1. Confirm `requirements.txt` already includes
   `google-api-python-client`, `google-auth-oauthlib`,
   `google-auth-httplib2`, `duckdb`, `python-dotenv`, and `beautifulsoup4`.
   The first five were added in earlier chunks; `beautifulsoup4` was added
   alongside this spec being drafted (used in step 5). Do NOT add anything
   else.

2. Create `pipeline/gmail_client.py` exposing:
   - `SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]`
   - `get_credentials(creds_path: Path, token_path: Path) -> Credentials`
     — Loads stored token if present and valid; refreshes if expired with
     a refresh token; otherwise runs `InstalledAppFlow.run_local_server`
     and writes the new token to `token_path`.
   - `get_gmail_service(creds: Credentials) -> Resource`
     — Returns a `googleapiclient.discovery.build("gmail", "v1", ...)`
     resource.
   - `list_message_ids(service, query: str) -> Iterator[str]`
     — Yields every message ID matching `query`, paginating through all
     `nextPageToken`s. Page size 100. Uses `users().messages().list`.
   - `get_message(service, message_id: str) -> dict`
     — Returns the raw Gmail message dict at `format='full'`.

   Token file path: `creds/token.json`. Verify `creds/` is gitignored
   (it should already be — see CLAUDE.md). Do NOT add a new
   `.gitignore` entry if `creds/` already covers it.

3. Create `pipeline/fetcher.py` exposing:
   - `parse_message(msg: dict) -> dict` — see steps 4–6.
   - `fetch_and_store(service, conn, query: str, log_path: Path) -> dict`
     — Iterates `list_message_ids(service, query)`, calls `get_message`
     for each, calls `parse_message`, and inserts via:
     `INSERT INTO job_emails (email_id, thread_id, received_date,
      subject, sender, raw_content, calendar_invite_detected,
      extracted_data)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT (email_id) DO NOTHING`.
     The `extracted_data` value is the JSON string returned by
     `parse_message` (see step 6) — e.g. `'{"attachments": [...]}'` —
     or `NULL` if the message has no attachments.
     Returns `{"fetched": N, "inserted": M, "skipped": N - M - errors,
     "errors": E}`.
   - `main()` — entry point for the `__main__` block. Loads `.env`,
     resolves `creds/credentials.json` and `creds/token.json`, opens a
     DuckDB connection at `data/emails.duckdb` via `pipeline.db.connection`,
     calls `init_schema`, calls `fetch_and_store` with the query from
     step 7, prints the result dict, exits 0.

4. Header parsing rules in `parse_message`:
   - Subject: pull header `"Subject"` (case-insensitive lookup), pass
     through `email.header.decode_header` + `email.header.make_header` to
     handle RFC 2047 encoded-words. Missing → empty string.
   - Sender: same decoding for the `"From"` header. Missing → raise
     `ValueError("missing From header")` — the fetch loop catches and
     counts as an error per step 8.
   - Date: prefer `email.utils.parsedate_to_datetime` on the `"Date"`
     header. If missing or `parsedate_to_datetime` raises, fall back to
     `datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)`.
     `internalDate` is always present on a `format='full'` response.

5. Body extraction in `parse_message`:
   - Walk `msg["payload"]` recursively (a part may contain `parts`).
   - Prefer the first `text/plain` part. Decode `body.data` via
     `base64.urlsafe_b64decode`, then decode bytes using the part's
     declared charset (default `'utf-8'`, `errors='replace'`).
   - If no `text/plain` part exists, fall back to the first `text/html`
     part, decode the same way, then strip tags via
     `BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)`.
   - If neither exists, set `raw_content = ""`.
   - Truncate `raw_content` to 50000 characters max. (Insurance against
     pathological emails — classifier prompts won't use more anyway.)

6. Calendar invite detection + attachment metadata in `parse_message`:
   - Walk the same MIME tree once, collecting both signals.
   - `calendar_invite_detected = True` if any part has `mimeType` of
     `"text/calendar"` or `"application/ics"`, OR has a filename
     ending in `.ics` (check the `Content-Disposition` filename header
     or the part's `filename` attribute). Otherwise `False`.
   - Attachment filenames: collect the `filename` of every part that
     has a non-empty filename (i.e. its headers include
     `Content-Disposition: attachment; filename=...` or it otherwise
     declares a filename). Inline parts with no filename are not
     attachments and are excluded. Filenames only — never read or
     decode the attachment bytes.
   - The parse_message return dict gains:
     - `calendar_invite_detected` (bool, as above)
     - `extracted_data` — JSON string `'{"attachments": [<filenames>]}'`
       if at least one attachment filename was collected; otherwise
       `None` (insert as SQL NULL).
   - Per #006, attachment bytes are never read or stored. Filenames are
     metadata, not body content — safe to record.

7. Gmail query passed to `fetch_and_store`:
   `"-in:chats -in:sent -in:drafts -in:trash -in:spam"`.
   This fetches every received message in INBOX + Archive, excluding chats,
   sent items, drafts, trash, and spam. Per #010, no job-relatedness
   filtering; per #011, all-time backfill cost is bounded by stage-1
   heuristics in spec 03.

   TODO: Peter to confirm before execution. Default is the broader query
   above (includes archived mail). Alternative is `"in:inbox"` only
   (excludes archived). Pick before running the backfill — the broader
   query is the default unless overridden.

8. Error handling and logging in `main()` and `fetch_and_store`:
   - Initialize a logger writing to
     `logs/fetch-<UTC ISO timestamp>.log` (e.g.
     `logs/fetch-2026-05-07T14-30-00Z.log`). Format: human-readable, one
     line per message.
   - Per message, log: `email_id`, `sender`, `subject` truncated to
     80 chars, `action` (one of `"inserted"`, `"skipped"`,
     `"error: <ExceptionClass>: <str(exc)>"`).
   - **Never** log `raw_content`, full HTML, full headers, full body
     bytes, or attachment bytes. Per #006 this is a hard rule. The test
     in step 9 enforces it.
   - Per-message exceptions inside the fetch loop are caught, logged,
     counted in the `errors` total, and the loop continues.
   - Auth errors and network errors raised outside per-message scope
     (e.g. during `get_credentials` or `list_message_ids` pagination)
     propagate naturally — they are not per-message problems.

9. Create `tests/test_fetcher.py` with these pytest tests. Use the
   `tmp_path` fixture for the DB and log files. Mock the Gmail service
   with `unittest.mock.MagicMock` — never hit the real Gmail API.

   - `test_parse_message_extracts_required_fields` — minimal valid
     message; assert `email_id`, `thread_id`, `received_date`,
     `subject`, `sender`, `raw_content`, `calendar_invite_detected`
     all populated as expected.
   - `test_parse_message_decodes_encoded_subject` — subject like
     `"=?utf-8?B?VGVzdA==?="` decodes to `"Test"`.
   - `test_parse_message_handles_html_only_body` — message with only a
     `text/html` part returns stripped text (no tags).
   - `test_parse_message_handles_missing_body` — `raw_content == ""`.
   - `test_parse_message_truncates_long_body` — body > 50000 chars is
     truncated to 50000.
   - `test_parse_message_detects_calendar_invite_by_mimetype` — a part
     with `mimeType="text/calendar"` sets the flag.
   - `test_parse_message_collects_attachment_filenames` — message with
     two attached parts (e.g. `resume.pdf`, `cover_letter.pdf`) yields
     `extracted_data == '{"attachments": ["resume.pdf", "cover_letter.pdf"]}'`
     (or equivalent JSON; assert by parsing, not string equality).
   - `test_parse_message_extracted_data_is_none_when_no_attachments` —
     plain message with no attached parts yields `extracted_data is None`.
   - `test_parse_message_falls_back_to_internal_date` — missing `Date`
     header, valid `internalDate` → date populated from `internalDate`.
   - `test_parse_message_raises_on_missing_from_header` — `ValueError`.
   - `test_fetch_and_store_inserts_new_messages` — fresh DB, mock
     service yields 3 messages; expect
     `{"fetched": 3, "inserted": 3, "skipped": 0, "errors": 0}` and
     3 rows in `job_emails`, all with NULL `confidence_score` and
     NULL `classification_method`.
   - `test_fetch_and_store_skips_existing_messages` — pre-insert one of
     the three messages; expect `inserted=2, skipped=1`.
   - `test_fetch_and_store_continues_past_per_message_errors` — make
     one of three messages raise in `parse_message`; expect
     `inserted=2, errors=1`.
   - `test_log_does_not_contain_body_text` — feed a mock message whose
     body contains the unique sentinel `"BODY_LEAK_SENTINEL_42"`; assert
     that string does not appear anywhere in the log file. Per #006,
     this is the hard guarantee.

10. Run `pytest tests/test_fetcher.py -v`. On failure, iterate per
    methodology §7 (max 2–3 iterations before escalation).

11. Smoke test (manual, requires real Gmail credentials):
    - Run `python -m pipeline.fetcher`.
    - First run: browser opens for OAuth consent; complete the flow.
      `creds/token.json` is written.
    - Expect printed dict with `inserted > 0` and `errors == 0` (or a
      small number of errors with sanitized log entries).
    - Spot-check via
      `duckdb data/emails.duckdb -c "SELECT COUNT(*) FROM job_emails"`.
    - Re-run immediately. Expect `inserted=0` and
      `skipped == previous total` (idempotency check).
    - `grep -ri "BODY_LEAK_SENTINEL" logs/` returns nothing (sanity
      check that no real test sentinel leaked).

## Output
- `requirements.txt` — `beautifulsoup4` already added by this spec's
  step 1 alongside drafting.
- `pipeline/gmail_client.py` — OAuth helpers, service builder, message
  listing/fetching.
- `pipeline/fetcher.py` — `parse_message`, `fetch_and_store`, `main`.
- `tests/test_fetcher.py` — 14 passing tests, all using mocked Gmail.
  Covers attachment-filename collection (per #006: filenames yes, bytes no).
- `creds/token.json` — created on first OAuth flow (already gitignored
  via `creds/`).
- `logs/fetch-<timestamp>.log` — one per fetch run.

## Acceptance criteria
- [ ] All 14 tests in `tests/test_fetcher.py` pass with `pytest -v`.
- [ ] `test_log_does_not_contain_body_text` passes — proves #006
      compliance at the unit level.
- [ ] Re-running `python -m pipeline.fetcher` against an
      already-populated DB inserts 0 new rows
      (idempotency via PK conflict per #002).
- [ ] No row written by the fetcher has a non-NULL `confidence_score`
      or non-NULL `classification_method`. Verify after a fresh
      backfill via:
      `SELECT COUNT(*) FROM job_emails
       WHERE confidence_score IS NOT NULL
          OR classification_method IS NOT NULL`
      returning 0.
- [ ] `creds/token.json` is gitignored — verified via
      `git check-ignore creds/token.json` returning the path.
- [ ] No new dependencies beyond `beautifulsoup4`. Verify against
      `requirements.txt` — do not assume.
- [ ] Verification: run @~/.claude/_verification.md before commit.

## Out of scope
- Do NOT classify any field. `company`, `role`, `stage`, `outreach_type`,
  `is_spam`, `is_recruiter_inbound`, `confidence_score`,
  `classification_method`, `extracted_data` all remain NULL or
  schema-default. That is spec 03's job.
- Do NOT touch `job_threads`. Thread rollup is a separate spec.
- Do NOT use the Gmail batch API (`service.new_batch_http_request()`).
  Sequential `messages.get` calls are simpler and stay well under quota
  for one user. Revisit only if backfill is observed to take hours.
- Do NOT add custom retry/backoff. Trust `google-api-python-client`'s
  defaults. Quota errors will surface; backoff added only if observed.
- Do NOT add a `needs_review` column or any new column. Schema is locked
  by spec 01.
- Do NOT modify `pipeline/schema.sql`, `pipeline/db.py`, `tests/test_schema.py`,
  or any spec 01 artifact.
- Do NOT add a `--since` flag, date-bounded filter, or any incremental-fetch
  logic. The query in step 7 is the entire scope; incremental fetch belongs
  to a Phase 2 spec.
- Do NOT log raw email bodies, HTML payloads, or attachment bytes under
  any circumstance. Per #006.
- Do NOT introduce dependencies beyond `beautifulsoup4`. Other Google
  libs and `duckdb` are already in `requirements.txt`.
- Do NOT add a `__main__` block to `pipeline/gmail_client.py` — it is a
  library helper. The `__main__` block belongs in `pipeline/fetcher.py`.
- Do NOT write a CLI argument parser. `pipeline/fetcher.py`'s `main()`
  takes no arguments — defaults are baked in for Phase 1. Configurability
  comes later if needed.
