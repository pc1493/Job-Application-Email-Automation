# Job Application Email Automation

## What this is
Automated pipeline that reads my Gmail inbox, classifies job-application-related
emails (applications, recruiter outreach, interview invites, rejections, offers),
and writes structured data to a local DuckDB store. Goal: 95%+ accuracy on
classification and stage detection without manually building rules.

## Stack
- Python 3.11+
- Gmail API (google-api-python-client)
- Anthropic Claude API (Sonnet 4) for classification + extraction
- DuckDB for local storage
- Daily batch (cron or scheduled run)

## Methodology
Follow @~/.claude/methodology.md. No deviations.

## Project-specific rules
- Never log raw email bodies to stdout or files. They contain personal data.
- Never commit `data/emails.duckdb`, `creds/`, or `.env` — already gitignored.
- LLM classification calls go through the Anthropic API key in `.env` (var: `ANTHROPIC_API_KEY`). Never hardcode.
- Confidence threshold for auto-classification: 0.85. Below that, flag for human review.

## Phases
1. **Phase 1 (now):** Historical fetch + classification + DuckDB write. Manual verification.
2. **Phase 2:** Incremental daily fetch. Scheduled job.
3. **Phase 3:** Hooks for QA. Edge case refinement.
4. **Phase 4 (stretch):** Stage detection (interview rounds, offer/rejection).

Currently in Phase 1.

## Out of scope
- Web UI or dashboard. SQL queries against DuckDB are the interface for now.
- Multi-user support.
- Calendar integration beyond parsing invite content.
- Auto-replying to emails. Read-only pipeline.

## Running tests
```
pytest tests/ -v
```
`pytest.ini` sets `pythonpath = .` so no `PYTHONPATH` prefix is needed.

## Active task
See `specs/` directory. Spec 02 (Gmail fetcher) complete. Next: spec 03 (classifier).
