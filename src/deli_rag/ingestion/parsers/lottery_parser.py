from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from .base import ParsedDocument, register


@register
class LotteryParser:
    """NJ Lottery report parser — PLACEHOLDER (per DECISIONS §9).

    Registered against `.lottery.pdf` so files route here explicitly. When a real
    sample is available, replace `parse()` with a layout-aware implementation that
    mirrors RiaParser.
    """
    name: ClassVar[str] = "lottery"
    supported_mimes: ClassVar[set[str]] = {"application/pdf"}
    supported_extensions: ClassVar[set[str]] = {".lottery.pdf"}

    def parse(self, path: Path) -> ParsedDocument:
        raise NotImplementedError(
            "NJ Lottery parser is a placeholder. Provide a sample report under "
            "tests/fixtures/ and update LotteryParser.parse() with the real layout."
        )