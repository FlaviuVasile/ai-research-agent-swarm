"""Local PDF specialist. OCR is deliberately not claimed or performed."""
import logging
import pymupdf
from research_swarm.config import Settings
from research_swarm.models import Extraction

logger = logging.getLogger(__name__)

class PDFMaster:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def extract(self, data: bytes) -> Extraction:
        if not data or len(data) > self.settings.max_pdf_bytes:
            raise ValueError("Upload a nonempty PDF no larger than 25 MB.")
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                if doc.needs_pass:
                    raise ValueError("Password-protected PDFs are not supported. Upload an unlocked copy.")
                if not 1 <= len(doc) <= self.settings.max_pages:
                    raise ValueError("PDF must contain between 1 and 500 pages.")
                pages: list[str] = []
                unreadable: list[int] = []
                for number, page in enumerate(doc, 1):
                    text = page.get_text("text", sort=True).strip()
                    if text:
                        pages.append(f"[Page {number}]\n{text}")
                    else:
                        unreadable.append(number)
                if not pages:
                    raise ValueError("PDF contains no readable text. It may be scanned or blank. OCR is not implemented.")
                warnings = []
                if unreadable:
                    warnings.append(f"{len(unreadable)} pages had no readable text (first pages: {unreadable[:20]}). "
                                    "Image content was not analyzed; OCR is not implemented.")
                logger.info("Extracted %d text pages", len(pages))
                return Extraction("\n\n".join(pages), warnings)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Could not read this PDF. It may be invalid or corrupted.") from exc
