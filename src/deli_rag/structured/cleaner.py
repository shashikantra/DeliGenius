from __future__ import annotations

import re
import logging
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


class DataCleaner:
    """Centralized cleaning rules for all structured data (see DECISIONS.md 11.2)."""

    @staticmethod
    def clean_string(val: str | None, *, title_case: bool = True) -> str | None:
        """Trim whitespace and optionally Title Case."""
        if val is None:
            return None
        cleaned = " ".join(str(val).split()).strip()
        if not cleaned:
            return None
        return cleaned.title() if title_case else cleaned

    @staticmethod
    def clean_number(val: Any, default: float = 0.0) -> float:
        """Strip currency symbols/commas and convert to float."""
        if val is None or str(val).strip() == "":
            return default
        s = str(val).replace("$", "").replace(",", "").replace("%", "").strip()
        try:
            return float(s)
        except ValueError:
            return default

    @staticmethod
    def clean_int(val: Any, default: int = 0) -> int:
        """Convert to integer, stripping commas."""
        if val is None or str(val).strip() == "":
            return default
        s = str(val).replace(",", "").strip()
        try:
            return int(float(s))
        except ValueError:
            return default

    @staticmethod
    def clean_date(val: str | None) -> str | None:
        """Convert MM/DD/YYYY or M/D/YY to ISO YYYY-MM-DD."""
        if not val:
            return None
        s = str(val).strip()
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return s

    @staticmethod
    def is_valid_upc(upc: str | None) -> bool:
        """A UPC must be digits only and at least 8 chars long."""
        if not upc:
            return False
        upc = str(upc).strip()
        return upc.isdigit() and len(upc) >= 8