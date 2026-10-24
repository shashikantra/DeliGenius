from .base import (
    ParsedDocument, ParsedElement, ParsedPage, Parser, TableRecord, get_parser_for,
)

# Import every parser module so @register runs.
from . import csv_parser          # noqa: F401
from . import docx_parser         # noqa: F401
from . import lottery_parser      # noqa: F401
from . import pdf_parser          # noqa: F401
from . import ria_parser          # noqa: F401
from . import sales_csv_parser    # noqa: F401
from . import xlsx_parser         # noqa: F401

__all__ = [
    "ParsedDocument", "ParsedElement", "ParsedPage", "Parser", "TableRecord",
    "get_parser_for",
]