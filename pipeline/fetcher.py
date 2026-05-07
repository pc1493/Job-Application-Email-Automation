import base64
import email.header
import email.utils
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv

from pipeline.db import connection, init_schema
from pipeline.gmail_client import get_credentials, get_gmail_service, get_message, list_message_ids

_GMAIL_QUERY = "-in:chats -in:sent -in:drafts -in:trash -in:spam"
_CREDS_PATH = Path("creds/credentials.json")
_TOKEN_PATH = Path("creds/token.json")
_DB_PATH = Path("data/emails.duckdb")


def _get_header(headers: list, name: str) -> str | None:
    name_lower = name.lower()
    for h in headers:
        if h["name"].lower() == name_lower:
            return h["value"]
    return None


def _decode_mime_header(value: str) -> str:
    return str(email.header.make_header(email.header.decode_header(value)))


def _b64_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "==")


def _walk_parts(payload: dict):
    yield payload
    for part in payload.get("parts", []):
        yield from _walk_parts(part)


def _get_charset(part: dict) -> str | None:
    for h in part.get("headers", []):
        if h["name"].lower() == "content-type":
            for segment in h["value"].split(";"):
                segment = segment.strip()
                if segment.lower().startswith("charset="):
                    return segment[8:].strip().strip('"')
    return None


def _get_filename(part: dict) -> str | None:
    fname = part.get("filename", "")
    if fname:
        return fname
    for h in part.get("headers", []):
        if h["name"].lower() == "content-disposition":
            for segment in h["value"].split(";"):
                segment = segment.strip()
                if segment.lower().startswith("filename="):
                    fname = segment[9:].strip().strip('"')
                    if fname:
                        return fname
    return None


def parse_message(msg: dict) -> dict:
    payload = msg["payload"]
    headers = payload.get("headers", [])

    subject_raw = _get_header(headers, "Subject")
    subject = _decode_mime_header(subject_raw) if subject_raw else ""

    from_raw = _get_header(headers, "From")
    if from_raw is None:
        raise ValueError("missing From header")
    sender = _decode_mime_header(from_raw)

    date_raw = _get_header(headers, "Date")
    received_date = None
    if date_raw:
        try:
            received_date = email.utils.parsedate_to_datetime(date_raw)
        except Exception:
            pass
    if received_date is None:
        received_date = datetime.fromtimestamp(
            int(msg["internalDate"]) / 1000, tz=timezone.utc
        )

    plain_content = None
    html_content = None
    calendar_invite_detected = False
    attachment_filenames = []

    for part in _walk_parts(payload):
        mime_type = part.get("mimeType", "").lower()
        body_data = part.get("body", {}).get("data")
        fname = _get_filename(part)

        if mime_type in ("text/calendar", "application/ics") or (
            fname and fname.lower().endswith(".ics")
        ):
            calendar_invite_detected = True

        if fname:
            attachment_filenames.append(fname)

        if body_data:
            if mime_type == "text/plain" and plain_content is None:
                charset = _get_charset(part) or "utf-8"
                plain_content = _b64_decode(body_data).decode(charset, errors="replace")
            elif mime_type == "text/html" and html_content is None:
                charset = _get_charset(part) or "utf-8"
                html_text = _b64_decode(body_data).decode(charset, errors="replace")
                html_content = BeautifulSoup(html_text, "html.parser").get_text(
                    separator=" ", strip=True
                )

    if plain_content is not None:
        raw_content = plain_content[:50000]
    elif html_content is not None:
        raw_content = html_content[:50000]
    else:
        raw_content = ""

    extracted_data = (
        json.dumps({"attachments": attachment_filenames}) if attachment_filenames else None
    )

    return {
        "email_id": msg["id"],
        "thread_id": msg["threadId"],
        "received_date": received_date,
        "subject": subject,
        "sender": sender,
        "raw_content": raw_content,
        "calendar_invite_detected": calendar_invite_detected,
        "extracted_data": extracted_data,
    }


def fetch_and_store(service, conn, query: str, log_path: Path) -> dict:
    logger = logging.getLogger(f"pipeline.fetcher.{str(log_path)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.FileHandler(str(log_path))
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)

    fetched = 0
    inserted = 0
    errors = 0

    try:
        for msg_id in list_message_ids(service, query):
            fetched += 1
            try:
                msg = get_message(service, msg_id)
                parsed = parse_message(msg)

                result = conn.execute(
                    """
                    INSERT INTO job_emails (
                        email_id, thread_id, received_date, subject, sender,
                        raw_content, calendar_invite_detected, extracted_data
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (email_id) DO NOTHING
                    RETURNING email_id
                    """,
                    [
                        parsed["email_id"],
                        parsed["thread_id"],
                        parsed["received_date"],
                        parsed["subject"],
                        parsed["sender"],
                        parsed["raw_content"],
                        parsed["calendar_invite_detected"],
                        parsed["extracted_data"],
                    ],
                )
                if result.fetchone() is not None:
                    inserted += 1
                    action = "inserted"
                else:
                    action = "skipped"

                logger.info(
                    "email_id=%s sender=%s subject=%s action=%s",
                    parsed["email_id"],
                    parsed["sender"],
                    parsed["subject"][:80],
                    action,
                )
            except Exception as exc:
                errors += 1
                logger.info(
                    "email_id=%s action=error: %s: %s",
                    msg_id,
                    type(exc).__name__,
                    str(exc),
                )
    finally:
        handler.close()
        logger.removeHandler(handler)

    skipped = fetched - inserted - errors
    return {"fetched": fetched, "inserted": inserted, "skipped": skipped, "errors": errors}


def main():
    load_dotenv()

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    log_path = log_dir / f"fetch-{timestamp}.log"

    creds = get_credentials(_CREDS_PATH, _TOKEN_PATH)
    service = get_gmail_service(creds)

    with connection(_DB_PATH) as conn:
        init_schema(conn)
        result = fetch_and_store(service, conn, _GMAIL_QUERY, log_path)

    print(result)


if __name__ == "__main__":
    main()
