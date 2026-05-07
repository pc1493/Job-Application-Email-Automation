# Skill Reference — Job Application Email Automation

Reusable patterns and lessons from building this pipeline.
Each entry links to a bug doc where a failure first revealed the pattern.

---

## 1. Dockerized Python environment (node:20 base)

The container runs `python3`, not `python`. There is no `python` alias.
The system Python is protected by PEP 668 — `pip install` without
`--break-system-packages` will refuse.

**Always use:**
```bash
python3 -m pytest ...
pip3 install <pkg> --break-system-packages
```

Or better: install into a venv (not done here because Claude Code runs
inside the container with --dangerously-skip-permissions and a venv adds
activation friction). If the project grows, add a venv to Dockerfile.

See: [bug-001-python-command.md](bug-001-python-command.md),
[bug-002-pep668-install.md](bug-002-pep668-install.md)

---

## 2. pytest PYTHONPATH in a flat-package project

Without a `setup.py`, `pyproject.toml`, or `conftest.py` that manipulates
`sys.path`, pytest cannot find a top-level package like `pipeline/` unless
the workspace root is on `PYTHONPATH`.

**Fix once, forever:** add `pytest.ini` at the project root:
```ini
[pytest]
pythonpath = .
```
Requires pytest ≥ 7. All subsequent `pytest` invocations pick it up
automatically — no env-var prefix needed.

See: [bug-003-module-not-found.md](bug-003-module-not-found.md)

---

## 3. DuckDB: detecting insert vs. conflict without a second query

DuckDB supports `RETURNING` on `INSERT ... ON CONFLICT DO NOTHING`.
When a conflict occurs the RETURNING clause returns zero rows.
Use this to distinguish "inserted" from "skipped" in a single round-trip:

```python
result = conn.execute(
    """INSERT INTO job_emails (email_id, ...)
       VALUES (?, ...)
       ON CONFLICT (email_id) DO NOTHING
       RETURNING email_id""",
    params,
)
was_inserted = result.fetchone() is not None
```

Requires DuckDB ≥ 0.8 (project pins ≥ 0.10). Do not use SQLite's
`changes()` — DuckDB does not expose it.

---

## 4. Logging isolation in pytest

The Python `logging` module is global. File handlers added by one test
persist into the next if not cleaned up. Pattern that works:

```python
logger = logging.getLogger(f"my.module.{str(log_path)}")
logger.setLevel(logging.INFO)
logger.propagate = False          # don't double-log to root

handler = logging.FileHandler(str(log_path))
handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
logger.addHandler(handler)

try:
    # ... do work ...
finally:
    handler.close()
    logger.removeHandler(handler)  # leave logger object clean for next call
```

Key points:
- Use the log file path as part of the logger name → unique per test
  (each test gets its own `tmp_path`).
- `propagate = False` prevents root-logger handlers (e.g. caplog, stdout)
  from capturing the same lines.
- `finally` block guarantees cleanup even if the work raises.

---

## 5. Gmail API: MIME walking pattern

Gmail's `format='full'` response nests MIME parts recursively.
A single-pass generator handles all depths:

```python
def _walk_parts(payload: dict):
    yield payload
    for part in payload.get("parts", []):
        yield from _walk_parts(part)
```

Body data lives in `part["body"]["data"]` (base64url-encoded, no padding).
Safe decode:

```python
base64.urlsafe_b64decode(data + "==")   # extra == is harmless
```

Prefer `text/plain` first, fall back to `text/html` (strip with
BeautifulSoup), fall back to `""`. Walk the same tree once, collecting
body content, calendar signals, and attachment filenames in a single pass
— avoids O(n) scans for each signal.

---

## 6. Gmail API: attachment filename lookup

In the Gmail API response, the `filename` field lives directly on the
part dict (not nested under `body`). Also check `Content-Disposition`
header as a fallback:

```python
def _get_filename(part):
    fname = part.get("filename", "")
    if fname:
        return fname
    for h in part.get("headers", []):
        if h["name"].lower() == "content-disposition":
            for seg in h["value"].split(";"):
                seg = seg.strip()
                if seg.lower().startswith("filename="):
                    return seg[9:].strip().strip('"') or None
    return None
```

Never read or decode attachment bytes — filenames are safe metadata,
bytes are not (per #006).

---

## 7. RFC 2047 header decoding

Gmail subjects and From headers can be encoded as `=?charset?B?...?=`
or `=?charset?Q?...?=`. Always decode:

```python
import email.header

def _decode_mime_header(value: str) -> str:
    return str(email.header.make_header(email.header.decode_header(value)))
```

`decode_header` returns `[(bytes_or_str, charset_or_None), ...]`.
`make_header` reassembles them. `str()` gives the final string.
Handles plain (unencoded) headers transparently.

---

## 8. Mocking: patch where the name is used, not where it is defined

`pipeline/fetcher.py` does `from pipeline.gmail_client import get_message`.
After that import, `fetcher.get_message` is a local name. Patching
`pipeline.gmail_client.get_message` does nothing to the already-imported
reference in `fetcher`. Patch the right target:

```python
@patch("pipeline.fetcher.get_message")
@patch("pipeline.fetcher.list_message_ids")
def test_...(mock_list, mock_get, ...):
```

Note decorator order: `@patch` decorators apply bottom-up, but pytest
injects them into the function signature top-down (closest decorator →
first argument after `self`/fixtures).

---

## 9. Per-message error isolation in a fetch loop

Wrap each message's processing in a `try/except`, log the exception class
and message (never the raw body), count errors, and continue:

```python
for msg_id in list_message_ids(service, query):
    fetched += 1
    try:
        msg = get_message(service, msg_id)
        parsed = parse_message(msg)
        # ... insert ...
    except Exception as exc:
        errors += 1
        logger.info("email_id=%s action=error: %s: %s",
                    msg_id, type(exc).__name__, str(exc))
```

Auth/network errors outside the per-message scope (e.g. during pagination)
are NOT caught — they propagate naturally, which is the right behavior
(the whole run is broken, not just one message).

Return a summary dict: `{"fetched": N, "inserted": M, "skipped": N-M-E, "errors": E}`.
`skipped` is derived, not tracked separately, to keep accounting consistent.
