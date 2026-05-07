# Architectural Decisions

Append-only log of architectural decisions for this project. Each entry is
immutable — if a decision changes, write a new entry that supersedes the old one.
Do not edit history.

Format: numbered entries, newest at the bottom. Reference other entries by
number (e.g. "see #003"). Reference from specs the same way.

Not for: commit-message-level trivia, renames, formatting choices. Only for
decisions where the *why* would be unclear from the code alone.

---

## Index

- #001 — DuckDB as local storage layer
- #002 — Gmail message ID as primary key on `job_emails`
- #003 — Two-table schema: `job_emails` + `job_threads`
- #004 — Confidence score convention (NULL / 0–1.0 / 1.0)
- #005 — 0.85 confidence threshold for auto-classification
- #006 — Never log raw email bodies
- #007 — Read-only Gmail access (`gmail.readonly` scope)
- #008 — Claude Haiku 4.5 as classifier, with Sonnet escalation hatch
- #009 — `classification_method` enum splits regex / heuristic / llm_single / llm_thread / manual
- #010 — Dumb fetch + classifier filter (fetcher does not judge job-relatedness)
- #011 — Two-stage classification: Python heuristics, then Haiku LLM on the remainder

---

## #001 — DuckDB as local storage layer

**Date:** 2026-XX-XX (TODO: Peter, fill in from Opus chat history)
**Status:** Active

**Decision:** Use DuckDB as the storage engine. Local file at `data/emails.duckdb`,
gitignored. No server, no shared database.

**Rationale:** Single-file, no server, embedded in Python — matches Phase 1
requirement of local-only single-user operation. Postgres was implicitly
considered and rejected as overkill (no concurrent access needed, no remote
deployment planned). Choice was made on intuition rather than benchmarked
alternatives. Revisit if Phase 2 ever needs multi-user access or remote DB.

**Implications:**
- Schema lives in `pipeline/schema.sql` as the source of truth.
- All queries go through `pipeline/db.py` helpers.
- Migrating to Postgres later (if Phase 2 ever needs multi-user access) means
  rewriting connection handling but the SQL itself is mostly portable.

---

## #002 — Gmail message ID as primary key on `job_emails`

**Date:** 2026-XX-XX (during spec 01)
**Status:** Active

**Decision:** `job_emails.email_id` (TEXT, Gmail message ID) is the primary key.

**Rationale:** The fetcher is designed to be re-run (historical backfill, then
incremental updates). Using Gmail's own immutable message ID as the PK makes
inserts idempotent automatically — re-fetching the same message produces a
PK conflict, which we handle as "already seen, skip." No deduplication logic
needed.

**Implications:**
- Insert pattern is `INSERT … ON CONFLICT DO NOTHING` (or equivalent).
- We never generate our own surrogate IDs for emails.
- If a Gmail message is deleted on Gmail's side, our row persists. That's a
  feature (audit trail), not a bug.

---

## #003 — Two-table schema: `job_emails` + `job_threads`

**Date:** 2026-XX-XX (TODO: Peter, fill in from Opus chat history)
**Status:** Active

**Decision:** Schema has two tables: `job_emails` (one row per email) and
`job_threads` (one row per Gmail thread, aggregated rollup).

**Rationale:** One row per email preserves raw evidence for re-classification
if prompts or logic change. One row per thread provides the natural query
unit for application lifecycle (current stage, outcome). A single wide table
was implicitly considered and rejected because thread-level aggregates would
need recomputation on every query. Choice was made on design intuition rather
than load-tested alternatives. Revisit if thread rollup logic becomes a
bottleneck or if the duplication between tables creates consistency bugs.

**Implications:**
- `job_threads` is derived from `job_emails`. It must be re-derivable from
  scratch if logic changes.
- Thread rollup logic is its own concern (likely a later spec).
- Queries about "how is application X going" hit `job_threads`. Queries
  about "what did the recruiter say in email Y" hit `job_emails`.

---

## #004 — Confidence score convention (NULL / 0–1.0 / 1.0)

**Date:** 2026-XX-XX (during spec 01)
**Status:** Active

**Decision:** `job_emails.confidence_score` follows three states:
- `NULL` — not yet classified
- `1.0` — deterministic match (regex / exact rule), no uncertainty
- `0–1.0` — LLM classification, model's self-reported confidence

**Rationale:** Three states cleanly separate "no attempt yet" from "tried and
got a noisy answer" from "tried and got a certain answer." `NULL` is critical:
it lets the orchestrator find unclassified rows with `WHERE confidence_score
IS NULL` rather than needing a separate `is_classified` flag.

**Implications:**
- Re-classification is signaled by `last_reclassified_at`, not by setting
  confidence back to NULL.
- A row can move from NULL → some value, but never back to NULL.

---

## #005 — 0.85 confidence threshold for auto-classification

**Date:** 2026-XX-XX (TODO: Peter, fill in from Opus chat history)
**Status:** Active

**Decision:** Classifications with `confidence_score >= 0.85` are accepted
automatically. Below 0.85 requires human review.

**Rationale:** Chosen as initial heuristic without sample-data calibration —
0.85 felt high enough to filter low-confidence noise but not so high that it
flags everything for review. Alternatives (0.8, 0.9) were not tested.
Acceptable starting point because consequences of misclassification in
Phase 1 are low (manual review, not user-facing action). Revisit after the
first ~100 classified emails are manually reviewed: if false positives at
≥0.85 are common, raise the threshold; if too many obvious-correct rows fall
below 0.85, lower it.

**Implications:**
- The classifier (spec 03) must produce a confidence value the LLM is
  prompted to self-report.
- "Below threshold" handling needs a flag or workflow — TBD in spec 03
  (whether to leave `classification_method = NULL`, add a `needs_review`
  column, or some other approach).
- This threshold may need tuning after Phase 1 sees real data.

---

## #006 — Never log raw email bodies

**Date:** 2026-XX-XX (during spec 01)
**Status:** Active

**Decision:** Raw email content (`raw_content` column) is never written to
stdout, log files, or any output stream. It lives in the DB only.

**Rationale:** Emails contain personal data — names, contact info, salary
figures, sometimes credentials in attachments. Logs are the highest leak
risk: they get pasted into chats, committed accidentally, sent to monitoring
services. The DB is the one place this data lives, and access goes through
explicit SQL.

**Implications:**
- Logging in fetcher and classifier must explicitly redact body content.
  Log message metadata only: `email_id`, `subject` truncated, `sender`,
  classification result.
- Error messages must not include raw body. Tracebacks that risk this
  must be caught and re-raised with sanitized context.
- Test fixtures use synthetic email bodies, never real ones.

---

## #007 — Read-only Gmail access (`gmail.readonly` scope)

**Date:** 2026-XX-XX (planned for spec 02)
**Status:** Active

**Decision:** OAuth scope is `https://www.googleapis.com/auth/gmail.readonly`.
We never modify, send, label, or delete in Gmail.

**Rationale:** The pipeline is purely an observer of the inbox. Read-only
scope means a bug in our code can't damage the user's actual mailbox — at
worst, we have a wrong row in DuckDB, which is fixable. This also keeps the
OAuth consent screen narrower and the threat surface smaller if credentials
ever leak.

**Implications:**
- "Mark as read," "apply label," "auto-reply" — none of these are options
  without a scope change, which is a deliberate decision, not a casual one.
- If a future spec needs write access, it requires re-doing the OAuth
  consent flow with broader scopes.

---

## #008 — Claude Haiku 4.5 as classifier, with Sonnet escalation hatch

**Date:** 2026-05-06 (revised from earlier Sonnet-only choice)
**Status:** Active

**Decision:** Default classifier is Claude Haiku 4.5 (`claude-haiku-4-5`).
Low-confidence classifications (below the threshold in #005) MAY be
re-classified by Claude Sonnet 4.6 as an escalation path before falling
through to manual review. Escalation path is not required for Phase 1 — it
can be added in a later spec if Haiku alone produces too many low-confidence
results.

**Rationale:** Email classification is a structured extraction task —
well-defined fields (company, role, stage, booleans), no multi-step reasoning
required. This is the category Haiku 4.5 is explicitly positioned for, with
quality matching the older Sonnet 4 at roughly one-third the cost
($1/$5 per million tokens vs $3/$15 for Sonnet 4.6). Earlier choice of
Sonnet 4 predated Haiku 4.5's release; revisiting now with the cheaper
option as default. Sonnet stays available as an escalation tier so that
ambiguous cases — where the marginal quality might tip a row above the
confidence threshold — aren't immediately dumped on a human reviewer.

**Implications:**
- Model strings live in config (`.env` or a constants module), not hardcoded.
  Both `CLASSIFIER_PRIMARY_MODEL` and `CLASSIFIER_ESCALATION_MODEL` so a swap
  is one config edit.
- Phase 1 implementation may use Haiku only and skip the escalation step —
  that decision belongs in spec 03.
- If Haiku quality on real emails is poor, the escape hatch is to flip the
  default to Sonnet without code changes.
- Cost projection: at ~5000 historical emails × ~2k tokens each, Haiku
  classification of the full backfill costs roughly $10–$15. Sonnet would
  cost ~$30–$45. Difference matters more for ongoing volume than for the
  one-time backfill.

---

## #009 — `classification_method` enum splits regex / heuristic / llm_single / llm_thread / manual

**Date:** 2026-XX-XX (during spec 01)
**Status:** Active

**Decision:** `classification_method_enum` has five values:
- `regex` — deterministic pattern match
- `heuristic` — non-LLM rule-based logic (e.g. sender domain rules)
- `llm_single` — LLM classified the email in isolation
- `llm_thread` — LLM classified the email with thread context
- `manual` — human override

**Rationale:** Tracking *how* a row was classified is essential for debugging
and for prioritizing re-classification. If classifier prompts change, we want
to re-run only `llm_single` and `llm_thread` rows, leaving `manual` and
`regex` alone. Without this column, we'd have no way to identify which rows
were touched by which version of the logic.

**Implications:**
- Manual overrides (a human editing a row) must set `classification_method
  = 'manual'` so future automated runs skip them.
- The split between `llm_single` and `llm_thread` is a real architectural
  choice — see spec 03's design for whether we batch by thread or not.
- Adding a new method (e.g. an embedding-based classifier later) means
  adding to the enum, which is a schema migration.

---

## #010 — Dumb fetch + classifier filter

**Date:** 2026-05-07 (planned for spec 02)
**Status:** Active

**Decision:** The fetcher does not attempt to filter for job-relatedness. It
pulls every received Gmail message (Gmail query excludes only chats, sent,
drafts, spam, and trash) and inserts each row with NULL classification fields.
The classifier (spec 03) is the sole owner of the "is this job-related?"
decision.

**Rationale:** Smart filtering at fetch time — keyword-matching on subjects
or sender lists — was considered and rejected. The failure mode is invisible:
emails that should have been in the dataset get silently dropped, and there's
no row to inspect later. Letting the classifier decide means false negatives
exist as low-confidence rows we can review, rather than as missing rows we
never knew about. The dumb fetch is only economically viable in combination
with #011 (heuristics filter the obvious bulk before any LLM cost is paid).

**Implications:**
- The fetcher's only filter is the Gmail query string. No subject/sender
  allowlists or denylists in fetcher code.
- Every fetched row has `confidence_score = NULL` and
  `classification_method = NULL` on insert.
- Total `job_emails` row count after backfill will be much larger than the
  count of actual job emails (likely 10–20× larger). DuckDB compresses well
  and Phase 1 is single-user, so disk size is not a concern.
- The classifier MUST handle the obviously-not-job case efficiently or LLM
  cost balloons. That's what #011 exists for.

---

## #011 — Two-stage classification: Python heuristics, then Haiku LLM

**Date:** 2026-05-07 (planned for spec 03; informs spec 02 scope)
**Status:** Active

**Decision:** Classification runs in two stages.

- **Stage 1 — Heuristics:** Deterministic Python rules (sender-domain rules,
  subject regexes) run on every NULL-confidence row. A stage-1 hit sets
  `classification_method = 'heuristic'` and `confidence_score = 1.0`.
- **Stage 2 — Haiku LLM:** Claude Haiku 4.5 (per #008) runs on rows still
  NULL after stage 1. Sets `classification_method = 'llm_single'` (or
  `'llm_thread'` per #009) with the LLM's self-reported confidence.

Stage-1 rules are NOT designed in advance. They will be learned from real
data after the spec-02 backfill via exploratory SQL (high-volume senders,
common subject patterns that are obviously not job-related). Spec 03 is
therefore blocked on spec 02 completion plus an exploratory pass.

**Rationale:** Without stage 1, the LLM would have to look at every email —
newsletters, GitHub notifications, calendar reminders, retail receipts. Those
dominate the inbox by volume and are trivially identifiable by sender or
subject. Heuristics eliminate this bulk for free, leaving the LLM to handle
only the genuinely ambiguous cases. This is what makes the dumb fetch in
#010 economically viable: cost scales with the ambiguous-fraction, not the
total inbox size.

**Implications:**
- Spec 02 (fetcher) can proceed before stage-1 rules are designed.
- Spec 03 has a mandatory prerequisite: exploratory SQL on the populated
  DB to identify the heuristic ruleset. Without that, spec 03 cannot be
  drafted with the same precision as spec 01.
- The cost projection in #008 (~$10–$15 for ~5000 emails via Haiku) was
  predicated on most rows being job-related. Under #010 + #011, the LLM
  only sees the post-heuristic remainder — likely a much smaller set —
  so the projection is conservative, not aggressive.
- The `classification_method` enum (#009) already includes both
  `'heuristic'` and `'llm_single'`, so no schema change is needed.
- A row that scored confidence 1.0 via heuristics never gets re-examined by
  the LLM unless explicitly re-classified.