import fitz  # PyMuPDF


def extract_text(pdf_path: str, max_pages: int = 30):
    text = []
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        text.append(page.get_text())
    return "\n".join(text)
