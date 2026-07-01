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


def test_transcript_aes_encrypted_pdf() -> None:
    # Quest transcripts are AES-encrypted with an empty user password —
    # requires pypdf[crypto] and a decrypt("") call, not a "can't read" error.
    import io

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    # Minimal text content: a real course code on the page.
    from pypdf.generic import DecodedStreamObject, NameObject

    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 40 700 Td (CS 135 CS 136 MATH 135) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
        })
    })
    writer.encrypt(user_password="", owner_password="uw", algorithm="AES-256")
    buf = io.BytesIO()
    writer.write(buf)

    r = _client().post(
        "/transcript",
        files={"file": ("transcript.pdf", buf.getvalue(), "application/pdf")},
    )
    body = r.json()
    assert body["ok"] is True, body
    assert "CS 135" in body["courses"]
