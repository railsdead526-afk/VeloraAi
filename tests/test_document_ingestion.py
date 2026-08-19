import io

import pytest
from pypdf import PdfWriter

from app.services.document_ingestion import DocumentExtractionError, extract_text


def test_extract_utf8_text_file():
    text, mime_type, source = extract_text("notes.md", "hello world".encode("utf-8"))
    assert text == "hello world"
    assert mime_type == "text/markdown"
    assert source == "md"


def test_reject_unsupported_file_type():
    with pytest.raises(DocumentExtractionError):
        extract_text("image.png", b"not a document")


def test_reject_non_utf8_text():
    with pytest.raises(DocumentExtractionError):
        extract_text("notes.txt", b"\xff\xfe")


def test_extract_pdf_text():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    payload = io.BytesIO()
    writer.write(payload)
    payload.seek(0)
    with pytest.raises(DocumentExtractionError):
        extract_text("empty.pdf", payload.read())
