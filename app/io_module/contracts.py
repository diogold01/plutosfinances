"""
Contratos e DTOs independentes do Módulo de Importação/Exportação CSV e Excel (Requisito 3).

Projetado com acoplamento zero em relação à camada de interface gráfica (`PySide6`) e ao
banco de dados, permitindo:
- Uso autônomo via linha de comando, scripts ou serviços.
- Integração futura com ferramentas externas de formatação e pós-processamento de planilhas
  por meio do protocolo `ExternalSpreadsheetFormatterHook`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, runtime_checkable


@dataclass
class CanonicalTransactionRow:
    """Representação canônica e independente de uma linha de movimentação financeira."""

    kind: str  # 'despesa', 'receita' ou 'transferencia'
    descricao: str
    valor: float
    data_vencimento: date
    data_lancamento: Optional[date] = None
    data_efetivacao: Optional[date] = None
    efetivada: bool = False
    categoria: str = "Outros"
    subcategoria: str = "Outros"
    conta: str = ""
    conta_destino: str = ""
    cartao: str = ""
    recorrencia: str = "Única"
    tags: List[str] = field(default_factory=list)
    observacoes: str = ""
    fingerprint: str = ""
    raw_row_index: int = 0
    num_parcela: int = 1
    num_parcelas: int = 1
    is_negative: bool = False


@dataclass
class CategorySummaryRow:
    """Linha de resumo consolidado por categoria para exportação de relatórios."""

    categoria: str
    total: float
    percentual: float = 0.0
    quantidade: int = 0


@dataclass
class CSVColumnMapping:
    """
    Modelo configurável de mapeamento de colunas CSV (compatível com `modelos_csv`
    e `modelos_csv_campos` do esquema relacional).
    """

    id: str = ""
    descricao_modelo: str = "Padrão Minhas Finanças (PT-BR)"
    separador: str = ";"
    possui_cabecalho: bool = True
    formato_data: str = "dd/MM/yyyy"
    valor_negativo_despesas: bool = True
    observacoes: str = ""
    id_conta: Optional[str] = None
    id_cartao: Optional[str] = None
    # Índices de colunas 0-based (None = detecção automática pelo cabeçalho)
    col_data: Optional[int] = None
    col_descricao: Optional[int] = None
    col_valor: Optional[int] = None
    col_categoria: Optional[int] = None
    col_subcategoria: Optional[int] = None
    col_tipo: Optional[int] = None
    col_situacao: Optional[int] = None
    col_conta: Optional[int] = None
    col_cartao: Optional[int] = None
    col_tags: Optional[int] = None
    col_observacoes: Optional[int] = None


@dataclass
class ImportReport:
    """Resumo detalhado do processamento de uma importação de planilha/extrato."""

    source_path: str
    format_type: str  # 'csv' ou 'xlsx'
    total_rows_read: int = 0
    imported_count: int = 0
    skipped_duplicates: int = 0
    skipped_invoice_payments: int = 0
    error_count: int = 0
    errors: List[str] = field(default_factory=list)
    imported_ids: List[str] = field(default_factory=list)


@dataclass
class ExportReport:
    """Resumo detalhado do processamento de uma exportação de planilha."""

    target_path: str
    format_type: str  # 'csv' ou 'xlsx'
    exported_rows: int = 0
    template_used: Optional[str] = None
    external_formatters_applied: List[str] = field(default_factory=list)


@runtime_checkable
class ExternalSpreadsheetFormatterHook(Protocol):
    """
    Protocolo de extensão para ferramentas externas de formatação de planilhas (Requisito 3).

    Qualquer ferramenta ou plugin externo (ex.: formatador corporativo OpenPyXL, injetor de
    tabelas dinâmicas, gerador de gráficos Excel ou normalizador de CSV) pode ser registrado
    no módulo de I/O implementando `__call__(file_path, metadata)`.
    """

    def __call__(self, file_path: Path, metadata: Dict[str, Any]) -> None: ...


@runtime_checkable
class SpreadsheetImporterProtocol(Protocol):
    """Contrato para leitores modulares de planilhas (CSV, Excel, etc.)."""

    def parse_file(
        self,
        file_path: Path | str,
        *,
        default_kind: str = "despesa",
        mapping: Optional[CSVColumnMapping] = None,
    ) -> List[CanonicalTransactionRow]: ...


@runtime_checkable
class SpreadsheetExporterProtocol(Protocol):
    """Contrato para exportadores modulares de planilhas (CSV, Excel, etc.)."""

    def export_transactions(
        self,
        file_path: Path | str,
        rows: Sequence[CanonicalTransactionRow],
        *,
        mode: str = "extrato",
        category_summary: Optional[Sequence[CategorySummaryRow]] = None,
        external_hooks: Optional[Sequence[ExternalSpreadsheetFormatterHook]] = None,
    ) -> ExportReport: ...


FormatterCallable = Callable[[Path, Dict[str, Any]], None]
