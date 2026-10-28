"""Módulo Independente de Importação e Exportação CSV e Excel (Requisito 3)."""

from app.io_module.contracts import (
    CanonicalTransactionRow,
    CategorySummaryRow,
    CSVColumnMapping,
    ExportReport,
    ExternalSpreadsheetFormatterHook,
    ImportReport,
    SpreadsheetExporterProtocol,
    SpreadsheetImporterProtocol,
)
from app.io_module.csv_handler import (
    CSVSpreadsheetHandler,
    format_br_amount,
    parse_flexible_amount,
    parse_flexible_date,
)
from app.io_module.duplicate_checker import (
    DuplicateChecker,
    compute_row_fingerprint,
    normalize_text_for_hash,
)
from app.io_module.excel_handler import ExcelSpreadsheetHandler
from app.io_module.io_orchestrator import DataIOOrchestrator

__all__ = [
    "CanonicalTransactionRow",
    "CategorySummaryRow",
    "CSVColumnMapping",
    "CSVSpreadsheetHandler",
    "DataIOOrchestrator",
    "DuplicateChecker",
    "ExcelSpreadsheetHandler",
    "ExportReport",
    "ExternalSpreadsheetFormatterHook",
    "ImportReport",
    "SpreadsheetExporterProtocol",
    "SpreadsheetImporterProtocol",
    "compute_row_fingerprint",
    "format_br_amount",
    "normalize_text_for_hash",
    "parse_flexible_amount",
    "parse_flexible_date",
]
