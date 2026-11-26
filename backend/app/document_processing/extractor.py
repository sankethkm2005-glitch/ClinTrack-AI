"""Document extraction service utilizing PyMuPDF for text and Tesseract for OCR."""

import io
import os
import shutil
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from app.config import settings

STANDARD_WINDOWS_TESSERACT_PATHS = [
    Path.home() / "AppData" / "Local" / "Tesseract-OCR" / "tesseract.exe",
    Path(r"C:\Users\sanke\AppData\Local\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]


def resolve_tesseract_executable() -> tuple[str | None, str | None]:
    """
    Resolve and validate the Tesseract OCR executable path.
    Priority:
      1. Explicit TESSERACT_CMD environment variable or settings.TESSERACT_CMD.
      2. System PATH via shutil.which('tesseract').
      3. Standard Windows installation directories.
    Returns:
      (executable_path, error_message)
    """
    configured_cmd = (os.environ.get("TESSERACT_CMD") or settings.TESSERACT_CMD or "").strip()
    if configured_cmd:
        cfg_path = Path(configured_cmd)
        if cfg_path.is_file():
            return str(cfg_path), None
        which_cfg = shutil.which(configured_cmd)
        if which_cfg:
            return which_cfg, None
        return None, f"Configured TESSERACT_CMD executable not found: {configured_cmd}"

    which_path = shutil.which("tesseract")
    if which_path:
        return which_path, None

    for candidate in STANDARD_WINDOWS_TESSERACT_PATHS:
        if candidate.is_file():
            return str(candidate), None

    return None, (
        "Tesseract OCR executable not found on TESSERACT_CMD, system PATH, "
        "or standard Windows installation directories."
    )


def configure_tesseract() -> tuple[bool, str | None]:
    """Configure pytesseract.pytesseract.tesseract_cmd if a valid executable is found."""
    exe_path, err = resolve_tesseract_executable()
    if exe_path:
        pytesseract.pytesseract.tesseract_cmd = exe_path
        return True, None
    return False, err


# Configure at module import
configure_tesseract()


class DocumentExtractor:
    """Extracts raw text and page mappings from medical PDFs and images."""

    @staticmethod
    def get_tesseract_status() -> dict:
        """Returns diagnostic info about Tesseract OCR availability."""
        ok, err = configure_tesseract()
        tess_path = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
        if not ok:
            return {
                "available": False,
                "error": err,
                "tesseract_path": None,
                "message": err or "Tesseract OCR executable not detected.",
                "notice": (
                    "Tesseract OCR is not installed or not found. Digital PDF extraction "
                    "works natively via PyMuPDF. Scanned PDFs/images require Tesseract."
                ),
            }
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
                "message": f"Tesseract OCR validation failed: {e}",
                "notice": (
                    "Tesseract OCR executable failed validation. Digital PDF extraction "
                    "works natively via PyMuPDF. Scanned PDFs/images require Tesseract."
                ),
            }

    @staticmethod
    def ensure_tesseract_available() -> str:
        """Validate Tesseract executable before starting OCR; raises RuntimeError if unavailable."""
        ok, err = configure_tesseract()
        if not ok:
            raise RuntimeError(err or "Tesseract OCR executable is unavailable.")
        return pytesseract.pytesseract.tesseract_cmd

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
        ocr_errors = []

        if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
            doc = fitz.open(str(path))
            page_count = len(doc)

            for i in range(page_count):
                page = doc.load_page(i)
                text = page.get_text("text").strip()

                # If text is empty on a PDF page, attempt OCR via PyMuPDF rendering
                if not text:
                    try:
                        cls.ensure_tesseract_available()
                        pix = page.get_pixmap(dpi=200)
                        img = Image.open(io.BytesIO(pix.tobytes("png")))
                        text = pytesseract.image_to_string(img).strip()
                        method = "tesseract_ocr"
                    except Exception as e:
                        ocr_errors.append(f"Page {i + 1}: {str(e)}")
                        text = ""

                page_num = i + 1
                page_texts.append({"page": page_num, "text": text})
                if text:
                    raw_text_parts.append(f"--- [Page {page_num}] ---\n{text}")
            doc.close()

            if not raw_text_parts:
                if ocr_errors:
                    raise RuntimeError(f"OCR extraction failed on scanned PDF: {'; '.join(ocr_errors)}")
                raise RuntimeError("PDF document contains no extractable text.")

        elif mime_type.startswith("image/") or path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            page_count = 1
            method = "tesseract_ocr"
            try:
                cls.ensure_tesseract_available()
                img = Image.open(str(path))
                text = pytesseract.image_to_string(img).strip()
            except Exception as e:
                raise RuntimeError(f"OCR extraction failed on image: {str(e)}")
            if not text:
                raise RuntimeError("OCR extraction produced no readable text from image.")
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
