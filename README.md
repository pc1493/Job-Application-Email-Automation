# Job Application Email Automation

Reads Gmail, classifies job-application emails using Claude, and stores structured data in DuckDB. Currently in Phase 1: historical fetch + classification.

## Prerequisites

- Docker Desktop on Windows
- A Gmail account with OAuth credentials (see Gmail API setup below)
- An Anthropic API key

## Setup

### 1. Clone and configure

```
cp .env.example .env
# Edit .env and fill in your ANTHROPIC_API_KEY
```

### 2. Gmail API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the Gmail API.
3. Create an OAuth 2.0 credential (Desktop app type).
4. Download the JSON file and save it to `creds/gmail_credentials.json`.
5. On first run the pipeline will open a browser for OAuth consent and write the token to `creds/gmail_token.json`.

### 3. Build and run

```powershell
.\build.ps1   # builds the Docker image (once, or after Dockerfile changes)
.\run.ps1     # starts an interactive Claude Code session inside the container
```

Inside the container, your project files are at `/workspace`.

## Project layout

```
pipeline/       source code for the fetch/classify/store pipeline
specs/          task specs (one file per chunk of work)
tests/          tests
creds/          OAuth credentials — gitignored, never commit
data/           DuckDB database file — gitignored
logs/           runtime logs — gitignored
```

## Querying results

```sql
-- From inside the container
python3 -c "import duckdb; con = duckdb.connect('data/emails.duckdb'); print(con.execute('SELECT * FROM classified_emails LIMIT 10').df())"
```

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | Active | Historical fetch, classification, DuckDB write |
| 2 | Planned | Incremental daily fetch |
| 3 | Planned | QA hooks, edge case refinement |
| 4 | Stretch | Stage detection (interview rounds, offers) |
# Job-Application-Email-Automation
