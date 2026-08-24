from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader


class DocumentExtractionError(RuntimeError):
    pass


SUPPORTED_EXTENSIONS = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".pdf": "application/pdf",
}


def extract_text(filename: str, content: bytes) -> tuple[str, str, str]:
    suffix = Path(filename or "").suffix.lower()
    mime_type = SUPPORTED_EXTENSIONS.get(suffix)
    if not mime_type:
        raise DocumentExtractionError("Only TXT, Markdown, and PDF files are supported")

    if suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [(page.extract_text() or "") for page in reader.pages]
        except Exception as exc:
            raise DocumentExtractionError("Unable to extract text from PDF") from exc
        text = "\n\n".join(pages).strip()
    else:
        try:
            text = content.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError("Text files must use UTF-8 encoding") from exc

    if not text:
        raise DocumentExtractionError("The uploaded document contains no extractable text")
    return text, mime_type, suffix.lstrip(".")
