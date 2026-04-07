"""Receipt OCR and survey-code extraction."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

from PIL import Image, ImageFilter, ImageOps

try:
    import pytesseract
    _HAS_TESSERACT = True
except ImportError:
    _HAS_TESSERACT = False


# Known retailer survey patterns. Each entry contains:
#   name, survey_url, code_regex (captures the code), keywords that identify the retailer.
RETAILER_PATTERNS = [
    {
        "name": "Walmart",
        "url": "https://survey.walmart.com",
        "keywords": ["walmart", "save money. live better"],
        "code_regex": r"ID\s*#?[:\s]*([0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4})",
    },
    {
        "name": "Target",
        "url": "https://informtarget.com",
        "keywords": ["target", "expect more. pay less"],
        "code_regex": r"User\s*ID[:\s]*([0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4})",
    },
    {
        "name": "Home Depot",
        "url": "https://homedepot.com/survey",
        "keywords": ["home depot", "homedepot"],
        "code_regex": r"User\s*ID[:\s]*([0-9A-Z]{4}[\s-]?[0-9A-Z]{5}[\s-]?[0-9A-Z]{5})",
    },
    {
        "name": "Lowe's",
        "url": "https://lowes.com/survey",
        "keywords": ["lowe's", "lowes"],
        "code_regex": r"ID\s*#?[:\s]*([0-9]{3}[\s-]?[0-9]{3}[\s-]?[0-9]{3}[\s-]?[0-9]{3}[\s-]?[0-9]{3})",
    },
    {
        "name": "McDonald's",
        "url": "https://mcdvoice.com",
        "keywords": ["mcdonald", "mcdvoice"],
        "code_regex": r"([0-9]{5}[\s-]?[0-9]{5}[\s-]?[0-9]{5}[\s-]?[0-9]{5}[\s-]?[0-9]{6})",
    },
    {
        "name": "Walgreens",
        "url": "https://walgreenslistens.com",
        "keywords": ["walgreens", "walgreenslistens"],
        "code_regex": r"survey\s*code[:\s#]*([0-9]{4}[\s-]?[0-9]{4})",
    },
    {
        "name": "CVS",
        "url": "https://cvshealthsurvey.com",
        "keywords": ["cvs pharmacy", "cvshealthsurvey"],
        "code_regex": r"code[:\s#]*([0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4})",
    },
    {
        "name": "Kroger",
        "url": "https://krogerfeedback.com",
        "keywords": ["kroger", "krogerfeedback"],
        "code_regex": r"Entry\s*ID[:\s]*([0-9]{3}[\s-]?[0-9]{3}[\s-]?[0-9]{3}[\s-]?[0-9]{3})",
    },
    {
        "name": "Publix",
        "url": "https://publixsurvey.com",
        "keywords": ["publix"],
        "code_regex": r"survey\s*code[:\s#]*([0-9]{4}[\s-]?[0-9]{4}[\s-]?[0-9]{4})",
    },
    {
        "name": "Chick-fil-A",
        "url": "https://mycfavisit.com",
        "keywords": ["chick-fil-a", "chickfila", "mycfavisit"],
        "code_regex": r"code[:\s#]*([0-9]{5}[\s-]?[0-9]{3}[\s-]?[0-9]{3})",
    },
    {
        "name": "Subway",
        "url": "https://tellsubway.com",
        "keywords": ["subway", "tellsubway"],
        "code_regex": r"code[:\s#]*([0-9]{6,})",
    },
    {
        "name": "Dollar General",
        "url": "https://dgcustomerfirst.com",
        "keywords": ["dollar general", "dgcustomerfirst"],
        "code_regex": r"([0-9]{4}[\s-][0-9]{4}[\s-][0-9]{4}[\s-][0-9]{2})",
    },
]

# Generic fallback patterns for survey codes on receipts.
GENERIC_CODE_PATTERNS = [
    r"survey\s*(?:code|id|#)[:\s#]*([0-9A-Z]{4,}(?:[\s-][0-9A-Z]{2,}){1,5})",
    r"(?:validation|confirmation)\s*code[:\s#]*([0-9A-Z]{6,})",
    r"code[:\s#]*([0-9]{4}[\s-][0-9]{4}[\s-][0-9]{4,})",
]

# Generic URL pattern (survey website printed on receipt).
URL_PATTERN = re.compile(
    r"(?:https?://)?((?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?)",
    re.IGNORECASE,
)


@dataclass
class ReceiptDetails:
    """Structured details extracted from a receipt image."""
    raw_text: str
    retailer: Optional[str] = None
    survey_url: Optional[str] = None
    survey_code: Optional[str] = None
    store_location: Optional[str] = None
    date: Optional[str] = None
    total: Optional[str] = None
    items: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "retailer": self.retailer,
            "survey_url": self.survey_url,
            "survey_code": self.survey_code,
            "store_location": self.store_location,
            "date": self.date,
            "total": self.total,
            "line_items": self.items,
            "raw_text": self.raw_text,
        }


def _preprocess(image: Image.Image) -> Image.Image:
    """Convert to grayscale, auto-contrast, and sharpen for better OCR."""
    img = image.convert("L")
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    # Upscale small images for better OCR accuracy.
    w, h = img.size
    if max(w, h) < 1200:
        scale = 1200 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img


def ocr_image(image_bytes: bytes) -> str:
    """Run OCR on an image, returning the extracted text."""
    img = Image.open(BytesIO(image_bytes))
    img = _preprocess(img)
    if not _HAS_TESSERACT:
        raise RuntimeError(
            "pytesseract is not installed. Install it and the Tesseract binary "
            "(e.g. `apt install tesseract-ocr`) to enable OCR."
        )
    return pytesseract.image_to_string(img)


def _identify_retailer(text: str) -> Optional[dict]:
    low = text.lower()
    for retailer in RETAILER_PATTERNS:
        for kw in retailer["keywords"]:
            if kw in low:
                return retailer
    return None


def _find_code(text: str, retailer: Optional[dict]) -> Optional[str]:
    # Try retailer-specific regex first.
    if retailer:
        m = re.search(retailer["code_regex"], text, re.IGNORECASE)
        if m:
            return re.sub(r"\s+", "", m.group(1))
    # Fall back to generic patterns.
    for pat in GENERIC_CODE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return re.sub(r"\s+", "", m.group(1))
    return None


def _find_url(text: str) -> Optional[str]:
    for line in text.splitlines():
        # Look on lines that look like survey invitations.
        if any(w in line.lower() for w in ("survey", "tell", "feedback", "listen", "visit", "voice")):
            m = URL_PATTERN.search(line)
            if m:
                url = m.group(1)
                if not url.startswith("http"):
                    url = "https://" + url
                return url
    return None


def _find_total(text: str) -> Optional[str]:
    m = re.search(r"total[:\s]*\$?\s*([0-9]+\.[0-9]{2})", text, re.IGNORECASE)
    return m.group(1) if m else None


def _find_date(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text)
    return m.group(1) if m else None


def _find_items(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        # Heuristic: item lines usually end with a price.
        if re.search(r"\$?\s*[0-9]+\.[0-9]{2}\s*$", line.strip()):
            cleaned = line.strip()
            if "total" not in cleaned.lower() and "tax" not in cleaned.lower():
                items.append(cleaned)
    return items[:20]


def parse_receipt(text: str) -> ReceiptDetails:
    """Parse OCR'd receipt text into structured details."""
    details = ReceiptDetails(raw_text=text)
    retailer = _identify_retailer(text)
    if retailer:
        details.retailer = retailer["name"]
        details.survey_url = retailer["url"]
    else:
        url = _find_url(text)
        if url:
            details.survey_url = url
    details.survey_code = _find_code(text, retailer)
    details.total = _find_total(text)
    details.date = _find_date(text)
    details.items = _find_items(text)
    # Store location: first non-empty line is often the store name/address.
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        details.store_location = " | ".join(lines[:3])
    return details


def scan_receipt(image_bytes: bytes) -> ReceiptDetails:
    """OCR an uploaded receipt image and parse it."""
    text = ocr_image(image_bytes)
    return parse_receipt(text)
