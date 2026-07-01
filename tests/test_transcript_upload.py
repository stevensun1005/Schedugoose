"""UWFlow-style transcript upload: /transcript extracts completed course codes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _client() -> TestClient:
    return TestClient(app)


def test_transcript_txt_extracts_codes() -> None:
    r = _client().post(
        "/transcript",
        files={"file": ("mycourses.txt", b"CS 135, MATH 135\nCS 136 done too", "text/plain")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["courses"] == ["CS 135", "MATH 135", "CS 136"]


def test_transcript_no_codes_is_friendly_error() -> None:
    r = _client().post(
        "/transcript",
        files={"file": ("junk.txt", b"hello world nothing here", "text/plain")},
    )
    body = r.json()
    assert body["ok"] is False
    assert body["courses"] == []
    assert "past" in body["error"].lower()  # "pasting" / "paste"


def test_transcript_broken_pdf_is_friendly_error() -> None:
    # %PDF magic but truncated garbage → readable error, not a 500.
    r = _client().post(
        "/transcript",
        files={"file": ("t.pdf", b"%PDF-1.4 garbage", "application/pdf")},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_standing_regex_allows_words_between() -> None:
    from agent.intake import parse_entering_term

    assert parse_entering_term("im a 2A CS student") == "2A"
    assert parse_entering_term("4B engineering student") == "4B"
    assert parse_entering_term("make 2A lighter") is None
