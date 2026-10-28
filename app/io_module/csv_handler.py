"""
Motor independente de leitura e exportação de arquivos CSV (`CSVSpreadsheetHandler`).

Suporta:
- Detecção automática de codificação (`utf-8-sig`, `utf-8`, `cp1252`, `latin-1`) e delimitador (`;`, `,`, `\t`).
- Mapeamento configurável (`CSVColumnMapping` / `modelos_csv`) ou detecção inteligente de cabeçalhos em português/inglês.
- Parsing flexível de datas (`DD/MM/YYYY`, `YYYY-MM-DD`, `DD-MM-YYYY`, `DD/MM/YY`) e valores monetários (`R$ 1.234,56`, `-450,00`, `1234.56`).
- Invocação de hooks externos (`ExternalSpreadsheetFormatterHook`) após a geração do arquivo.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.io_module.contracts import (
    CanonicalTransactionRow,
    CategorySummaryRow,
    CSVColumnMapping,
    ExportReport,
    ExternalSpreadsheetFormatterHook,
)
from app.io_module.duplicate_checker import normalize_text_for_hash


def parse_flexible_date(raw: Any, preferred_format: str = "dd/MM/yyyy") -> Optional[date]:
    """Converte strings de data (BR/ISO) ou objetos `date`/`datetime` para `date`."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    # Remove parte de hora se houver
    date_part = text.split(" ")[0].split("T")[0].strip()

    fmt_map = {
        "dd/MM/yyyy": "%d/%m/%Y",
        "yyyy-MM-dd": "%Y-%m-%d",
        "MM/dd/yyyy": "%m/%d/%Y",
        "dd-MM-yyyy": "%d-%m-%Y",
    }
    candidates = [
        fmt_map.get(preferred_format, "%d/%m/%Y"),
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%Y/%m/%d",
        "%m/%d/%Y",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(date_part, fmt).date()
        except ValueError:
            continue
    return None


def parse_flexible_amount(raw: Any) -> Tuple[float, bool]:
    """
    Analisa valores monetários em formato brasileiro (`R$ -1.234,56`, `(350,00)`)
    ou internacional (`-1234.56`) e retorna `(abs_valor, is_negative)`.
    """
    if raw is None:
        return 0.0, False
    if isinstance(raw, (int, float)):
        val = float(raw)
        return round(abs(val), 2), val < 0

    text = str(raw).strip()
    if not text:
        return 0.0, False

    is_neg = "-" in text or (text.startswith("(") and text.endswith(")"))
    cleaned = re.sub(r"[^\d,.\-]", "", text).replace("-", "")
    if not cleaned:
        return 0.0, False

    if "," in cleaned and "." in cleaned:
        # O último separador indica o decimal
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    try:
        num = float(cleaned)
        return round(abs(num), 2), is_neg
    except ValueError:
        return 0.0, False


def format_br_amount(val: float, signed: bool = False) -> str:
    """Formata um número decimal no padrão numérico brasileiro (`1234,56`)."""
    num = round(float(val or 0.0), 2)
    if not signed:
        num = abs(num)
    return f"{num:.2f}".replace(".", ",")


MONTH_PT_MAP: Dict[str, int] = {
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}

INCOME_KEYWORDS: Tuple[str, ...] = (
    "salario",
    "salário",
    "rendimento",
    "rendimentos",
    "dividendo",
    "dividendos",
    "provento",
    "proventos",
    "reembolso",
    "reembolsos",
    "estorno",
    "estornos",
    "cashback",
    "transferencia recebida",
    "transferência recebida",
    "transf recebida",
    "transf. recebida",
    "recebimento",
    "recebido",
    "recebida",
    "pix recebido",
    "ted recebida",
    "ted recebido",
    "doc recebido",
    "deposito recebido",
    "depósito recebido",
    "adiantamento salarial",
    "lucro",
    "venda",
    "resgate",
)

INCOME_CATEGORIES: Tuple[str, ...] = (
    "receita",
    "receitas",
    "salario",
    "salário",
    "salarios",
    "salários",
    "rendimento",
    "rendimentos",
    "provento",
    "proventos",
    "entradas",
    "outras receitas",
)


def parse_installment_info(rec_raw: Any, desc: str = "") -> Tuple[int, int, str]:
    """
    Decodifica informações de parcelas considerando texto padrão (ex: '2/6', 'Parcela 1 de 3'),
    notações de compras à vista ('1/1', 'Única') e distorções comuns do Excel (ex: '01/jan' para 1/1,
    '02/mar' para 2/3, ou datas nativas do Excel).
    """
    if isinstance(rec_raw, (datetime, date)):
        day, month = rec_raw.day, rec_raw.month
        if 1 <= day <= month and month <= 12:
            if month == 1:
                return 1, 1, "Única"
            return day, month, f"Parcela {day}/{month}"
        return 1, 1, "Única"

    text = str(rec_raw or "").strip()
    norm = text.lower()

    if norm in (
        "1/1",
        "01/01",
        "01/jan",
        "01/jan.",
        "unica",
        "única",
        "a vista",
        "à vista",
        "1",
    ):
        return 1, 1, "Única"

    # Caso Excel converta X/N para Dia/Mês (ex: 01/fev -> 1/2, 03/out -> 3/10)
    m_excel = re.search(
        r"(\d{1,2})\s*/\s*(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)", norm
    )
    if m_excel:
        p_cur = int(m_excel.group(1))
        p_tot = MONTH_PT_MAP.get(m_excel.group(2)[:3], 1)
        if 1 <= p_cur <= p_tot:
            if p_tot == 1:
                return 1, 1, "Única"
            return p_cur, p_tot, f"Parcela {p_cur}/{p_tot}"

    # Padrão normal: X/N ou X de N
    m_parc = re.search(r"(\d{1,2})\s*(?:/|de)\s*(\d{1,2})", text, re.IGNORECASE)
    if m_parc:
        p_cur = int(m_parc.group(1))
        p_tot = int(m_parc.group(2))
        if 1 <= p_cur <= p_tot:
            if p_tot == 1:
                return 1, 1, "Única"
            return p_cur, p_tot, f"Parcela {p_cur}/{p_tot}"

    # Tenta extrair da descrição caso não esteja na coluna de parcela
    if desc:
        m_desc = re.search(
            r"[-–—/(]?\s*(?:parcela\s*)?(\d{1,2})\s*(?:/|de)\s*(\d{1,2})\s*[)]?$",
            desc,
            re.IGNORECASE,
        )
        if m_desc:
            p_cur = int(m_desc.group(1))
            p_tot = int(m_desc.group(2))
            if 1 <= p_cur <= p_tot:
                if p_tot == 1:
                    return 1, 1, "Única"
                return p_cur, p_tot, f"Parcela {p_cur}/{p_tot}"

    return 1, 1, (text or "Única")


def infer_transaction_kind(
    tipo_raw: str,
    descricao: str,
    categoria: str,
    is_neg: bool,
    neg_is_expense: bool,
    default_kind: str = "despesa",
    has_destination: bool = False,
) -> str:
    """Inferência inteligente da natureza da movimentação (receita, despesa ou transferência)."""
    if has_destination:
        return "transferencia"

    tipo_norm = normalize_text_for_hash(tipo_raw)
    if tipo_norm in ("receita", "credito", "entrada", "income", "r", "c"):
        return "receita"
    if tipo_norm in ("despesa", "debito", "saida", "expense", "d"):
        return "despesa"
    if tipo_norm in ("transferencia", "transfer", "t"):
        return "transferencia"

    if is_neg and neg_is_expense:
        return "despesa"

    desc_norm = normalize_text_for_hash(descricao)
    cat_norm = normalize_text_for_hash(categoria)

    if cat_norm in INCOME_CATEGORIES:
        return "receita"

    for kw in INCOME_KEYWORDS:
        if kw in desc_norm:
            return "receita"

    return default_kind


CARD_INVOICE_PAYMENT_PATTERNS: Tuple[str, ...] = (
    "pagamento recebido",
    "pagamento de fatura",
    "pagamento da fatura",
    "pagamento fatura",
    "pgto de fatura",
    "pgto da fatura",
    "pgto fatura",
    "pagto de fatura",
    "pagto da fatura",
    "pagto fatura",
    "credito de pagamento",
    "debito automatico de fatura",
    "debito automatico da fatura",
    "debito automatico fatura",
)

CARD_REFUND_KEYWORDS: Tuple[str, ...] = (
    "estorno",
    "reembolso",
    "credito na fatura",
    "credito de fatura",
    "credito fatura",
    "desconto antecipacao",
    "desconto de antecipacao",
)


def is_credit_card_invoice_payment(
    descricao: str,
    *,
    is_neg: bool = False,
    is_card_context: bool = False,
) -> bool:
    """
    Detecta se uma linha de extrato representa pagamento de fatura anterior no cartão
    (ex.: 'Pagamento recebido' com valor negativo no CSV de fatura do Nubank).
    """
    desc_norm = normalize_text_for_hash(descricao).replace("_", " ")
    if not desc_norm:
        return False
    if is_card_context:
        for pat in CARD_INVOICE_PAYMENT_PATTERNS:
            if desc_norm == pat or desc_norm.startswith(f"{pat} ") or pat in desc_norm:
                return True
    elif is_neg and (
        desc_norm == "pagamento recebido"
        or desc_norm.startswith("pagamento recebido ")
    ):
        return True
    return False


def is_credit_card_refund(
    descricao: str,
    *,
    is_neg: bool = False,
    card_purchases_are_positive: bool = True,
) -> bool:
    """
    Detecta se uma linha de fatura de cartão de crédito representa estorno/crédito/reembolso
    que deve abater (valor negativo) o total da fatura.
    """
    if is_neg and card_purchases_are_positive:
        return True
    desc_norm = normalize_text_for_hash(descricao).replace("_", " ")
    for kw in CARD_REFUND_KEYWORDS:
        if kw in desc_norm:
            return True
    return False


def extract_invoice_due_date_from_filename(file_path: Path | str) -> Optional[date]:
    """
    Extrai a data de vencimento da fatura quando presente no nome do arquivo
    (ex.: 'Nubank_2026-11-09.csv' ou 'Nubank_2026-11-09 (2).csv').
    """
    stem = Path(file_path).stem
    m = re.search(
        r"(?:nubank|fatura)[_\-\s]+(\d{4}-\d{2}-\d{2})",
        stem,
        flags=re.IGNORECASE,
    )
    if m:
        return parse_flexible_date(m.group(1))
    return None


class CSVSpreadsheetHandler:
    """Leitor e escritor modular de arquivos CSV."""

    def __init__(
        self,
        external_hooks: Optional[ List[ExternalSpreadsheetFormatterHook]] = None,
    ) -> None:
        self._external_hooks: List[ExternalSpreadsheetFormatterHook] = list(
            external_hooks or []
        )

    def register_external_hook(self, hook: ExternalSpreadsheetFormatterHook) -> None:
        """Registra uma ferramenta externa de pós-processamento de planilhas."""
        self._external_hooks.append(hook)

    @staticmethod
    def _read_text_with_fallback(path: Path) -> str:
        raw_bytes = path.read_bytes()
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return raw_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="replace")

    @staticmethod
    def _detect_delimiter(sample_line: str, fallback: str = ";") -> str:
        counts = {sep: sample_line.count(sep) for sep in (";", ",", "\t")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else fallback

    @staticmethod
    def _infer_columns_from_header(headers: Sequence[str]) -> Dict[str, int]:
        """Mapeia nomes de cabeçalho comuns (PT-BR e EN) para chaves canônicas."""
        inferred: Dict[str, int] = {}
        for idx, h in enumerate(headers):
            norm = normalize_text_for_hash(h)
            if norm in ("descricao", "historico", "lancamento_descricao", "description", "memo", "titulo", "title"):
                inferred.setdefault("descricao", idx)
            elif norm in ("valor", "quantia", "amount", "value", "total"):
                inferred.setdefault("valor", idx)
            elif norm in ("vencimento", "data", "data_vencimento", "date", "dt"):
                inferred.setdefault("data_vencimento", idx)
            elif norm in ("lancamento", "data_lancamento", "compra"):
                inferred.setdefault("data_lancamento", idx)
            elif norm in ("efetivacao", "data_efetivacao", "pagamento"):
                inferred.setdefault("data_efetivacao", idx)
            elif norm in ("situacao", "status", "efetivada", "pago", "recebido"):
                inferred.setdefault("situacao", idx)
            elif norm in ("categoria", "category"):
                inferred.setdefault("categoria", idx)
            elif norm in ("subcategoria", "subcategory"):
                inferred.setdefault("subcategoria", idx)
            elif norm in ("conta_cartao", "contacartao", "conta_ou_cartao", "cartao_conta", "conta/cartao", "conta_cartao_credito"):
                inferred.setdefault("conta_cartao", idx)
                inferred.setdefault("conta", idx)
                inferred.setdefault("cartao", idx)
            elif norm in ("conta", "origem", "conta_origem", "account"):
                inferred.setdefault("conta", idx)
            elif norm in ("destino", "conta_destino"):
                inferred.setdefault("conta_destino", idx)
            elif norm in ("cartao", "cartao_credito", "card"):
                inferred.setdefault("cartao", idx)
            elif norm in ("recorrencia", "parcela", "parcelas", "frequency", "num_parcela", "num_parcelas"):
                inferred.setdefault("recorrencia", idx)
            elif norm in ("tags", "etiquetas", "tag"):
                inferred.setdefault("tags", idx)
            elif norm in ("observacoes", "obs", "notas", "notes", "observacao"):
                inferred.setdefault("observacoes", idx)
            elif norm in ("tipo", "natureza", "kind", "type"):
                inferred.setdefault("tipo", idx)
        return inferred

    def parse_file(
        self,
        file_path: Path | str,
        *,
        default_kind: str = "despesa",
        mapping: Optional[CSVColumnMapping] = None,
    ) -> List[CanonicalTransactionRow]:
        """Lê um arquivo CSV e converte em uma lista de `CanonicalTransactionRow`."""
        path = Path(file_path)
        content = self._read_text_with_fallback(path)
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if not lines:
            return []

        sep = (
            mapping.separador
            if mapping and mapping.separador
            else self._detect_delimiter(lines[0])
        )
        reader = list(csv.reader(lines, delimiter=sep))
        if not reader:
            return []

        has_header = True if mapping is None else bool(mapping.possui_cabecalho)
        header_map: Dict[str, int] = {}
        start_idx = 0
        if has_header:
            header_map = self._infer_columns_from_header(reader[0])
            # Se a primeira linha já tem uma data válida na primeira ou segunda coluna e nenhum cabeçalho foi inferido, trata como dados
            if not header_map and (
                parse_flexible_date(reader[0][0]) is not None
                or (len(reader[0]) > 1 and parse_flexible_date(reader[0][1]) is not None)
            ):
                start_idx = 0
            else:
                start_idx = 1

        def col_idx(key: str, map_attr: Optional[int], default_fallback: Optional[int] = None) -> Optional[int]:
            if map_attr is not None:
                return map_attr
            if key in header_map:
                return header_map[key]
            return default_fallback

        c_conta_cartao = header_map.get("conta_cartao")
        c_data = col_idx("data_vencimento", mapping.col_data if mapping else None, 0)
        c_desc = col_idx("descricao", mapping.col_descricao if mapping else None, 1)
        c_val = col_idx("valor", mapping.col_valor if mapping else None, 2)
        c_cat = col_idx("categoria", mapping.col_categoria if mapping else None)
        c_sub = col_idx("subcategoria", mapping.col_subcategoria if mapping else None)
        c_sit = col_idx("situacao", mapping.col_situacao if mapping else None)
        c_conta = col_idx("conta", mapping.col_conta if mapping else None, c_conta_cartao)
        c_dest = header_map.get("conta_destino")
        c_cartao = col_idx("cartao", mapping.col_cartao if mapping else None, c_conta_cartao)
        c_tags = col_idx("tags", mapping.col_tags if mapping else None)
        c_obs = col_idx("observacoes", mapping.col_observacoes if mapping else None)
        c_tipo = col_idx("tipo", mapping.col_tipo if mapping else None)
        c_lanc = header_map.get("data_lancamento")
        c_efet = header_map.get("data_efetivacao")
        c_rec = header_map.get("recorrencia")

        pref_fmt = mapping.formato_data if mapping else "dd/MM/yyyy"
        neg_is_expense = True if mapping is None else bool(mapping.valor_negativo_despesas)

        parsed_rows: List[CanonicalTransactionRow] = []
        for r_idx, row in enumerate(reader[start_idx:], start=start_idx + 1):
            if not row or all(not str(c).strip() for c in row):
                continue

            def cell(idx: Optional[int]) -> str:
                if idx is None or idx < 0 or idx >= len(row):
                    return ""
                return str(row[idx]).strip()

            raw_date = cell(c_data)
            dt_venc = parse_flexible_date(raw_date, pref_fmt)
            if dt_venc is None:
                # Tenta localizar uma data em outra coluna se o arquivo tiver ordem diferente (ex. Descrição na col 0 e Vencimento na col 6)
                for candidate_col in (c_lanc, c_efet, 0, 5, 6):
                    dt_venc = parse_flexible_date(cell(candidate_col), pref_fmt)
                    if dt_venc is not None:
                        break
            if dt_venc is None:
                continue

            desc = cell(c_desc) or "Lançamento Importado"
            val_abs, is_neg = parse_flexible_amount(cell(c_val))
            if val_abs <= 0:
                continue

            has_dest = bool(c_dest is not None and cell(c_dest))
            kind = infer_transaction_kind(
                tipo_raw=cell(c_tipo),
                descricao=desc,
                categoria=cell(c_cat),
                is_neg=is_neg,
                neg_is_expense=neg_is_expense,
                default_kind=default_kind,
                has_destination=has_dest,
            )

            sit_norm = normalize_text_for_hash(cell(c_sit))
            efetivada = sit_norm in (
                "pago",
                "paga",
                "recebido",
                "recebida",
                "efetivado",
                "efetivada",
                "confirmado",
                "confirmada",
                "pg",
                "s",
                "sim",
                "true",
                "1",
            ) or (c_sit is None)

            tags_raw = cell(c_tags)
            tags = [t.strip() for t in re.split(r"[,;|]", tags_raw) if t.strip()] if tags_raw else []

            num_parc, total_parcs, rec_val = parse_installment_info(cell(c_rec), desc)

            parsed_rows.append(
                CanonicalTransactionRow(
                    kind=kind,
                    descricao=desc,
                    valor=val_abs,
                    data_vencimento=dt_venc,
                    data_lancamento=parse_flexible_date(cell(c_lanc), pref_fmt) or dt_venc,
                    data_efetivacao=parse_flexible_date(cell(c_efet), pref_fmt)
                    or (dt_venc if efetivada else None),
                    efetivada=efetivada,
                    categoria=cell(c_cat) or "Outros",
                    subcategoria=cell(c_sub) or "Outros",
                    conta=cell(c_conta),
                    conta_destino=cell(c_dest),
                    cartao=cell(c_cartao),
                    recorrencia=rec_val,
                    tags=tags,
                    observacoes=cell(c_obs),
                    raw_row_index=r_idx,
                    num_parcela=num_parc,
                    num_parcelas=total_parcs,
                    is_negative=is_neg,
                )
            )
        return parsed_rows

    def export_transactions(
        self,
        file_path: Path | str,
        rows: Sequence[CanonicalTransactionRow],
        *,
        mode: str = "extrato",
        delimiter: str = ";",
        category_summary: Optional[Sequence[CategorySummaryRow]] = None,
        external_hooks: Optional[Sequence[ExternalSpreadsheetFormatterHook]] = None,
    ) -> ExportReport:
        """
        Exporta transações ou resumo de categorias para CSV UTF-8 com BOM (`utf-8-sig`),
        respeitando exatamente as colunas dos templates da aplicação de referência.
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode_norm = (mode or "extrato").lower()

        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=delimiter)
            if mode_norm == "categorias" and category_summary is not None:
                writer.writerow(["Categoria", "Total", "Percentual (%)", "Quantidade"])
                for cs in category_summary:
                    writer.writerow(
                        [
                            cs.categoria,
                            format_br_amount(cs.total),
                            f"{cs.percentual:.2f}".replace(".", ","),
                            cs.quantidade,
                        ]
                    )
                exported_count = len(category_summary)
            elif mode_norm == "despesas":
                writer.writerow(
                    [
                        "Descrição",
                        "Valor",
                        "Situação",
                        "Categoria",
                        "Subcategoria",
                        "Lançamento",
                        "Vencimento",
                        "Efetivação",
                        "Recorrência",
                        "Conta",
                        "Cartão",
                        "Tags",
                        "Observações",
                    ]
                )
                for r in rows:
                    writer.writerow(
                        [
                            r.descricao,
                            format_br_amount(r.valor),
                            "Pago" if r.efetivada else "Pendente",
                            r.categoria,
                            r.subcategoria,
                            (r.data_lancamento or r.data_vencimento).strftime("%d/%m/%Y"),
                            r.data_vencimento.strftime("%d/%m/%Y"),
                            r.data_efetivacao.strftime("%d/%m/%Y") if r.data_efetivacao else "",
                            r.recorrencia,
                            r.conta,
                            r.cartao,
                            ", ".join(r.tags),
                            r.observacoes,
                        ]
                    )
                exported_count = len(rows)
            elif mode_norm == "receitas":
                writer.writerow(
                    [
                        "Descrição",
                        "Valor",
                        "Situação",
                        "Categoria",
                        "Subcategoria",
                        "Lançamento",
                        "Vencimento",
                        "Efetivação",
                        "Recorrência",
                        "Conta",
                        "Tags",
                        "Observações",
                    ]
                )
                for r in rows:
                    writer.writerow(
                        [
                            r.descricao,
                            format_br_amount(r.valor),
                            "Recebido" if r.efetivada else "Pendente",
                            r.categoria,
                            r.subcategoria,
                            (r.data_lancamento or r.data_vencimento).strftime("%d/%m/%Y"),
                            r.data_vencimento.strftime("%d/%m/%Y"),
                            r.data_efetivacao.strftime("%d/%m/%Y") if r.data_efetivacao else "",
                            r.recorrencia,
                            r.conta,
                            ", ".join(r.tags),
                            r.observacoes,
                        ]
                    )
                exported_count = len(rows)
            elif mode_norm == "transferencias":
                writer.writerow(
                    [
                        "Descrição",
                        "Vencimento",
                        "Origem",
                        "Destino",
                        "Valor",
                        "Tags",
                        "Observações",
                    ]
                )
                for r in rows:
                    writer.writerow(
                        [
                            r.descricao,
                            r.data_vencimento.strftime("%d/%m/%Y"),
                            r.conta,
                            r.conta_destino,
                            format_br_amount(r.valor),
                            ", ".join(r.tags),
                            r.observacoes,
                        ]
                    )
                exported_count = len(rows)
            else:
                # Extrato completo (compatível com template_extrato_excel + colunas estendidas)
                writer.writerow(
                    [
                        "Data",
                        "Descrição",
                        "Tipo",
                        "Categoria",
                        "Subcategoria",
                        "Conta",
                        "Cartão",
                        "Situação",
                        "Valor",
                        "Tags",
                        "Observações",
                    ]
                )
                for r in rows:
                    signed_val = -abs(r.valor) if r.kind == "despesa" else abs(r.valor)
                    writer.writerow(
                        [
                            r.data_vencimento.strftime("%d/%m/%Y"),
                            r.descricao,
                            r.kind.capitalize(),
                            r.categoria,
                            r.subcategoria,
                            r.conta,
                            r.cartao,
                            "Efetivada" if r.efetivada else "Pendente",
                            format_br_amount(signed_val, signed=True),
                            ", ".join(r.tags),
                            r.observacoes,
                        ]
                    )
                exported_count = len(rows)

        applied_hooks: List[str] = []
        all_hooks = [*self._external_hooks, *(external_hooks or [])]
        for hook in all_hooks:
            hook_name = getattr(hook, "__name__", hook.__class__.__name__)
            hook(
                path,
                {
                    "format": "csv",
                    "mode": mode_norm,
                    "rows": exported_count,
                },
            )
            applied_hooks.append(hook_name)

        return ExportReport(
            target_path=str(path),
            format_type="csv",
            exported_rows=exported_count,
            template_used=None,
            external_formatters_applied=applied_hooks,
        )
