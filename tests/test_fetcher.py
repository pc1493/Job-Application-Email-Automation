import base64
import json
from datetime import timezone
from unittest.mock import MagicMock, patch

import pytest

from pipeline.db import get_connection, init_schema
from pipeline.fetcher import fetch_and_store, parse_message


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode()


def _make_msg(
    msg_id: str = "msg1",
    thread_id: str = "thread1",
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
    date: str = "Thu, 14 Nov 2024 12:00:00 +0000",
    body: str = "Hello, world!",
    internal_date: str = "1731585600000",
    extra_parts: list = None,
    mime_type: str = "text/plain",
) -> dict:
    parts = extra_parts or []
    payload_body = {"data": _b64(body)} if mime_type in ("text/plain", "text/html") else {}
    return {
        "id": msg_id,
        "threadId": thread_id,
        "internalDate": internal_date,
        "payload": {
            "mimeType": mime_type,
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": date},
            ],
            "body": payload_body,
            "parts": parts,
        },
    }


@pytest.fixture
def db(tmp_path):
    conn = get_connection(tmp_path / "test.duckdb")
    init_schema(conn)
    yield conn
    conn.close()


# ── parse_message tests ────────────────────────────────────────────────────────

def test_parse_message_extracts_required_fields():
    msg = _make_msg()
    result = parse_message(msg)
    assert result["email_id"] == "msg1"
    assert result["thread_id"] == "thread1"
    assert result["subject"] == "Test Subject"
    assert result["sender"] == "sender@example.com"
    assert "Hello" in result["raw_content"]
    assert result["received_date"] is not None
    assert result["calendar_invite_detected"] is False


def test_parse_message_decodes_encoded_subject():
    encoded = "=?utf-8?B?VGVzdA==?="
    msg = _make_msg(subject=encoded)
    result = parse_message(msg)
    assert result["subject"] == "Test"


def test_parse_message_handles_html_only_body():
    html = "<html><body><p>Hello <strong>World</strong></p></body></html>"
    msg = _make_msg(body=html, mime_type="text/html")
    result = parse_message(msg)
    assert "<" not in result["raw_content"]
    assert "Hello" in result["raw_content"]
    assert "World" in result["raw_content"]


def test_parse_message_handles_missing_body():
    msg = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1731585600000",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Thu, 14 Nov 2024 12:00:00 +0000"},
            ],
            "body": {},
            "parts": [],
        },
    }
    result = parse_message(msg)
    assert result["raw_content"] == ""


def test_parse_message_truncates_long_body():
    long_body = "x" * 60000
    msg = _make_msg(body=long_body)
    result = parse_message(msg)
    assert len(result["raw_content"]) == 50000


def test_parse_message_detects_calendar_invite_by_mimetype():
    ical_data = "BEGIN:VCALENDAR\nEND:VCALENDAR"
    msg = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1731585600000",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Thu, 14 Nov 2024 12:00:00 +0000"},
            ],
            "body": {},
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "",
                    "headers": [],
                    "body": {"data": _b64("Meeting details")},
                    "parts": [],
                },
                {
                    "mimeType": "text/calendar",
                    "filename": "",
                    "headers": [],
                    "body": {"data": _b64(ical_data)},
                    "parts": [],
                },
            ],
        },
    }
    result = parse_message(msg)
    assert result["calendar_invite_detected"] is True


def test_parse_message_collects_attachment_filenames():
    msg = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1731585600000",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Thu, 14 Nov 2024 12:00:00 +0000"},
            ],
            "body": {},
            "parts": [
                {
                    "mimeType": "text/plain",
                    "filename": "",
                    "headers": [],
                    "body": {"data": _b64("Plain text")},
                    "parts": [],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "resume.pdf",
                    "headers": [
                        {
                            "name": "Content-Disposition",
                            "value": "attachment; filename=resume.pdf",
                        }
                    ],
                    "body": {"attachmentId": "att1", "size": 1000},
                    "parts": [],
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "cover_letter.pdf",
                    "headers": [
                        {
                            "name": "Content-Disposition",
                            "value": "attachment; filename=cover_letter.pdf",
                        }
                    ],
                    "body": {"attachmentId": "att2", "size": 2000},
                    "parts": [],
                },
            ],
        },
    }
    result = parse_message(msg)
    data = json.loads(result["extracted_data"])
    assert set(data["attachments"]) == {"resume.pdf", "cover_letter.pdf"}


def test_parse_message_extracted_data_is_none_when_no_attachments():
    msg = _make_msg()
    result = parse_message(msg)
    assert result["extracted_data"] is None


def test_parse_message_falls_back_to_internal_date():
    msg = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1731585600000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                # No Date header
            ],
            "body": {"data": _b64("body")},
            "parts": [],
        },
    }
    result = parse_message(msg)
    expected = 1731585600000 / 1000
    assert result["received_date"].timestamp() == pytest.approx(expected, abs=1)
    assert result["received_date"].tzinfo is not None


def test_parse_message_raises_on_missing_from_header():
    msg = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1731585600000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Date", "value": "Thu, 14 Nov 2024 12:00:00 +0000"},
                # No From header
            ],
            "body": {"data": _b64("body")},
            "parts": [],
        },
    }
    with pytest.raises(ValueError, match="missing From header"):
        parse_message(msg)


# ── fetch_and_store tests ──────────────────────────────────────────────────────

def _make_fetch_msgs(count: int, prefix: str = "id") -> list:
    return [_make_msg(msg_id=f"{prefix}{i}", thread_id=f"t{i}") for i in range(count)]


@patch("pipeline.fetcher.get_message")
@patch("pipeline.fetcher.list_message_ids")
def test_fetch_and_store_inserts_new_messages(mock_list, mock_get, db, tmp_path):
    msgs = _make_fetch_msgs(3)
    mock_list.return_value = [m["id"] for m in msgs]
    mock_get.side_effect = lambda svc, mid: next(m for m in msgs if m["id"] == mid)

    result = fetch_and_store(MagicMock(), db, "-in:chats", tmp_path / "run.log")

    assert result == {"fetched": 3, "inserted": 3, "skipped": 0, "errors": 0}
    count = db.execute("SELECT COUNT(*) FROM job_emails").fetchone()[0]
    assert count == 3
    null_class = db.execute(
        "SELECT COUNT(*) FROM job_emails "
        "WHERE confidence_score IS NOT NULL OR classification_method IS NOT NULL"
    ).fetchone()[0]
    assert null_class == 0


@patch("pipeline.fetcher.get_message")
@patch("pipeline.fetcher.list_message_ids")
def test_fetch_and_store_skips_existing_messages(mock_list, mock_get, db, tmp_path):
    msgs = _make_fetch_msgs(3)
    # Pre-insert the first message
    db.execute(
        "INSERT INTO job_emails (email_id, thread_id, received_date, sender) "
        "VALUES (?, ?, NOW(), ?)",
        [msgs[0]["id"], msgs[0]["threadId"], "sender@example.com"],
    )
    mock_list.return_value = [m["id"] for m in msgs]
    mock_get.side_effect = lambda svc, mid: next(m for m in msgs if m["id"] == mid)

    result = fetch_and_store(MagicMock(), db, "-in:chats", tmp_path / "run.log")

    assert result["inserted"] == 2
    assert result["skipped"] == 1
    assert result["errors"] == 0


@patch("pipeline.fetcher.get_message")
@patch("pipeline.fetcher.list_message_ids")
def test_fetch_and_store_continues_past_per_message_errors(mock_list, mock_get, db, tmp_path):
    valid_msg = _make_msg(msg_id="id0", thread_id="t0")
    bad_msg = {
        "id": "id1",
        "threadId": "t1",
        "internalDate": "1731585600000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Date", "value": "Thu, 14 Nov 2024 12:00:00 +0000"},
                # No From header — will raise ValueError
            ],
            "body": {"data": _b64("body")},
            "parts": [],
        },
    }
    valid_msg2 = _make_msg(msg_id="id2", thread_id="t2")
    msgs = [valid_msg, bad_msg, valid_msg2]
    mock_list.return_value = [m["id"] for m in msgs]
    mock_get.side_effect = lambda svc, mid: next(m for m in msgs if m["id"] == mid)

    result = fetch_and_store(MagicMock(), db, "-in:chats", tmp_path / "run.log")

    assert result["inserted"] == 2
    assert result["errors"] == 1
    assert result["skipped"] == 0


@patch("pipeline.fetcher.get_message")
@patch("pipeline.fetcher.list_message_ids")
def test_log_does_not_contain_body_text(mock_list, mock_get, db, tmp_path):
    sentinel = "BODY_LEAK_SENTINEL_42"
    msg = _make_msg(msg_id="id0", body=sentinel)
    mock_list.return_value = ["id0"]
    mock_get.return_value = msg
    log_path = tmp_path / "run.log"

    fetch_and_store(MagicMock(), db, "-in:chats", log_path)

    log_text = log_path.read_text()
    assert sentinel not in log_text
