"""Shared parsing utilities — price extraction, HTML stripping."""

import re
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Optional


def parse_price(price_str: str) -> Optional[Decimal]:
    """Parse a price string into a Decimal.

    Handles: "$24.99", "1,299.00", "€99,99", plain "24.99", None/empty.
    Returns None if parsing fails.
    """
    if not price_str:
        return None
    cleaned = re.sub(r"[^\d.,]", "", str(price_str))
    if not cleaned:
        return None
    # Handle European format (comma as decimal separator)
    if "," in cleaned and "." in cleaned:
        # "1,299.00" -> standard; "1.299,00" -> European
        if cleaned.rindex(",") > cleaned.rindex("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned and "." not in cleaned:
        # Could be "1,299" (thousands) or "29,99" (European decimal)
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            cleaned = cleaned.replace(",", ".")  # European decimal
        else:
            cleaned = cleaned.replace(",", "")  # Thousands separator
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def strip_html(html_str: str) -> str:
    """Strip HTML tags and normalize whitespace.

    Also unescapes HTML entities (&amp; -> &, etc).
    """
    if not html_str:
        return ""
    text = unescape(re.sub(r"<[^>]+>", " ", html_str))
    return re.sub(r"\s+", " ", text).strip()
