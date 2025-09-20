"""
OCR Module for handling scanned PDFs and images
Supports multiple OCR approaches with intelligent fallback
"""

import tempfile
import pathlib
import logging
from typing import Optional, List
import io

try:
    from pdf2image import convert_from_path
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Robust PDF processor with multiple extraction methods"""

    def __init__(self):
        self.ocr_available = OCR_AVAILABLE
        self.pdfminer_available = PDFMINER_AVAILABLE

        # Configure tesseract for Vietnamese + English
        if self.ocr_available:
            self.ocr_languages = 'vie+eng'

    def extract_text(self, pdf_path: pathlib.Path) -> str:
        """
        Extract text from PDF using multiple methods:
        1. PyPDF (fast, for text-based PDFs)
        2. pdfminer.six (fallback for complex PDFs)
        3. OCR (for scanned PDFs)
        """
        logger.info(f"Processing PDF: {pdf_path.name}")

        # Method 1: Try PyPDF first (fastest)
        text = self._try_pypdf(pdf_path)
        if text.strip():
            logger.info(f"✓ PyPDF successful for {pdf_path.name}")
            return text

        # Method 2: Try pdfminer.six
        if self.pdfminer_available:
            text = self._try_pdfminer(pdf_path)
            if text.strip():
                logger.info(f"✓ pdfminer successful for {pdf_path.name}")
                return text

        # Method 3: OCR as last resort
        if self.ocr_available:
            text = self._try_ocr(pdf_path)
            if text.strip():
                logger.info(f"✓ OCR successful for {pdf_path.name}")
                return text

        logger.warning(f"❌ All methods failed for {pdf_path.name}")
        return ""

    def _try_pypdf(self, pdf_path: pathlib.Path) -> str:
        """Extract text using PyPDF"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages).strip()
        except Exception as e:
            logger.debug(f"PyPDF failed for {pdf_path.name}: {e}")
            return ""

    def _try_pdfminer(self, pdf_path: pathlib.Path) -> str:
        """Extract text using pdfminer.six"""
        try:
            text = pdfminer_extract(str(pdf_path)) or ""
            return text.strip()
        except Exception as e:
            logger.debug(f"pdfminer failed for {pdf_path.name}: {e}")
            return ""

    def _try_ocr(self, pdf_path: pathlib.Path) -> str:
        """Extract text using OCR (for scanned PDFs)"""
        try:
            logger.info(f"🔍 Starting OCR for {pdf_path.name}...")

            # Convert PDF to images
            images = convert_from_path(
                str(pdf_path),
                dpi=300,  # High quality for better OCR
                fmt='PNG'
            )

            if not images:
                logger.warning(f"No images extracted from {pdf_path.name}")
                return ""

            logger.info(f"📄 Processing {len(images)} pages with OCR...")

            # OCR each page
            ocr_texts = []
            for i, image in enumerate(images):
                try:
                    # Enhance image quality for better OCR
                    enhanced_image = self._enhance_image(image)

                    # Perform OCR
                    page_text = pytesseract.image_to_string(
                        enhanced_image,
                        lang=self.ocr_languages,
                        config='--psm 1'  # Automatic page segmentation
                    )

                    if page_text.strip():
                        ocr_texts.append(
                            f"=== Page {i+1} ===\n{page_text.strip()}")
                        logger.debug(
                            f"✓ OCR page {i+1}: {len(page_text)} chars")
                    else:
                        logger.debug(f"⚠ OCR page {i+1}: empty result")

                except Exception as e:
                    logger.warning(f"OCR failed for page {i+1}: {e}")
                    continue

            result = "\n\n".join(ocr_texts)
            logger.info(f"✓ OCR completed: {len(result)} characters extracted")
            return result

        except Exception as e:
            logger.error(f"OCR processing failed for {pdf_path.name}: {e}")
            return ""

    def _enhance_image(self, image: Image.Image) -> Image.Image:
        """Enhance image quality for better OCR results"""
        try:
            # Convert to grayscale for better OCR
            if image.mode != 'L':
                image = image.convert('L')

            # Increase contrast and sharpness
            from PIL import ImageEnhance

            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)

            # Enhance sharpness
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(2.0)

            return image
        except Exception as e:
            logger.debug(f"Image enhancement failed: {e}")
            return image

    def get_capabilities(self) -> dict:
        """Return available processing capabilities"""
        return {
            "pypdf": True,
            "pdfminer": self.pdfminer_available,
            "ocr": self.ocr_available,
            "ocr_languages": getattr(self, 'ocr_languages', None)
        }


# Global processor instance
pdf_processor = PDFProcessor()


def extract_text_from_pdf(pdf_path: pathlib.Path) -> str:
    """Convenience function for extracting text from PDF"""
    return pdf_processor.extract_text(pdf_path)
