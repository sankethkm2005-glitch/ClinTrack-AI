"""Document extraction service utilizing PyMuPDF for text and Tesseract for OCR."""

import fitz  # PyMuPDF
import io
import pytesseract
from PIL import Image
from pathlib import Path

from app.config import settings

if settings.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


class DocumentExtractor:
    """Extracts raw text and page mappings from medical PDFs and images."""

    @staticmethod
    def get_tesseract_status() -> dict:
        """Returns diagnostic info about Tesseract OCR availability."""
        tess_path = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        try:
            ver = pytesseract.get_tesseract_version()
            return {
                "available": True,
                "version": str(ver),
                "tesseract_path": str(tess_path),
                "message": f"Tesseract OCR is operational (v{ver}).",
                "notice": "OCR engine online and functional for image-to-text extraction.",
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "tesseract_path": str(tess_path),
                "message": "Tesseract OCR executable not detected on system PATH.",
                "notice": "Tesseract OCR is not installed or not on system PATH. Digital PDF extraction works natively via PyMuPDF. Scanned PDFs/images require Tesseract.",
            }

    @staticmethod
    def is_handwritten_suspect(text: str, filename: str) -> bool:
        """
        Conservative heuristic: if filename implies a handwritten prescription,
        or if OCR/text extraction returns virtually no recognizable words or high noise.
        """
        lower = filename.lower()
        if "handwritten" in lower or "rx_hand" in lower:
            return True
        # If extracted text is extremely low quality/sparse on an image/pdf
        if len(text.strip()) < 15 and ("rx" in lower or "prescription" in lower):
            return True
        return False

    @classmethod
    def extract_from_file(cls, file_path: str, mime_type: str, filename: str) -> dict:
        """
        Extract text page by page from PDF or image.
        Returns:
            dict: {
                "raw_text": str,
                "page_count": int,
                "page_texts": [{"page": int, "text": str}],
                "method": str,
                "requires_manual_review": bool,
                "review_reason": str | None
            }
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        page_texts = []
        raw_text_parts = []
        method = "pdf_text"

        if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
            doc = fitz.open(str(path))
            page_count = len(doc)

            for i in range(page_count):
                page = doc.load_page(i)
                text = page.get_text("text").strip()

                # If text is empty on a PDF page, attempt OCR via PyMuPDF rendering
                if not text:
                    try:
                        pix = page.get_pixmap(dpi=200)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        text = pytesseract.image_to_string(img).strip()
                        method = "tesseract_ocr"
                    except Exception:
                        text = ""

                page_num = i + 1
                page_texts.append({"page": page_num, "text": text})
                if text:
                    raw_text_parts.append(f"--- [Page {page_num}] ---\n{text}")
            doc.close()

        elif mime_type.startswith("image/") or path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            page_count = 1
            method = "tesseract_ocr"
            try:
                img = Image.open(str(path))
                text = pytesseract.image_to_string(img).strip()
            except Exception as e:
                text = f"[OCR Note: Tesseract OCR is unavailable or failed ({str(e)}). Preserving original document for manual clinician inspection.]"
                method = "manual_fallback"
            page_texts.append({"page": 1, "text": text})
            raw_text_parts.append(f"--- [Page 1] ---\n{text}")

        else:
            raise ValueError(f"Unsupported MIME type for extraction: {mime_type}")

        full_raw_text = "\n\n".join(raw_text_parts).strip()
        is_handwritten = cls.is_handwritten_suspect(full_raw_text, filename)

        return {
            "raw_text": full_raw_text,
            "page_count": page_count,
            "page_texts": page_texts,
            "method": method,
            "requires_manual_review": is_handwritten,
            "review_reason": (
                "Handwritten prescription or low OCR confidence detected. Manual doctor inspection required."
                if is_handwritten
                else None
            ),
        }
