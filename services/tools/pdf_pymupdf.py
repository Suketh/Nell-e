from typing import Any
from importlib import import_module


def extract_text(pdf_path: str, max_pages: int = 30) -> str:
    try:
        fitz = import_module("fitz")
    except Exception as exc:
        raise RuntimeError("PyMuPDF (`fitz`) is not installed in the current Python environment.") from exc
    text_chunks: list[str] = []
    doc: Any = fitz.open(pdf_path)
    try:
        for index, page in enumerate(doc):
            if index >= max_pages:
                break
            text_chunks.append(str(page.get_text()))
    finally:
        doc.close()
    return "\n".join(text_chunks)
