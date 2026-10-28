"""
Orquestrador de Importação e Exportação (`DataIOOrchestrator`).

Conecta os motores modulares (`CSVSpreadsheetHandler` e `ExcelSpreadsheetHandler`) e o
motor de deduplicação (`DuplicateChecker`) ao banco de dados SQLite (`ConnectionManager`)
e aos serviços de domínio (`TransactionService`, `CategoryRepository`, `AccountRepository`,
`TagRepository`, `CreditCardService`, `AnalyticsService`).

Inclui persistência de modelos de mapeamento CSV nas tabelas `modelos_csv` e `modelos_csv_campos`.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.tag_repository import TagRepository
from app.domain.date_utils import clamp_day
from app.domain.models import (
    KIND_DESPESA,
    KIND_RECEITA,
    KIND_TRANSFERENCIA,
    REC_PARCELADA,
    REC_UNICA,
    Occurrence,
)
from app.domain.services.analytics_service import AnalyticsService
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService
from app.io_module.contracts import (
    CanonicalTransactionRow,
    CategorySummaryRow,
    CSVColumnMapping,
    ExportReport,
    ExternalSpreadsheetFormatterHook,
    ImportReport,
)
from app.io_module.csv_handler import (
    CSVSpreadsheetHandler,
    INCOME_KEYWORDS,
    extract_invoice_due_date_from_filename,
    is_credit_card_invoice_payment,
    is_credit_card_refund,
)
from app.io_module.duplicate_checker import (
    DuplicateChecker,
    compute_row_fingerprint,
    normalize_text_for_hash,
)
from app.io_module.excel_handler import ExcelSpreadsheetHandler


class DataIOOrchestrator:
    """Serviço coordenador de importação e exportação CSV/Excel."""

    def __init__(
        self,
        db: ConnectionManager,
        tx_service: Optional[TransactionService] = None,
    ) -> None:
        self.db = db
        self.tx = tx_service or TransactionService(db)
        self.categories = CategoryRepository(db)
        self.accounts = AccountRepository(db)
        self.tags = TagRepository(db)
        self.cards = CreditCardService(db, self.tx)
        self.analytics = AnalyticsService(db, self.tx)
        self.csv_handler = CSVSpreadsheetHandler()
        self.excel_handler = ExcelSpreadsheetHandler()
        self.dup_checker = DuplicateChecker(db)
        self._external_hooks: List[ExternalSpreadsheetFormatterHook] = []

    def register_external_formatter(self, hook: ExternalSpreadsheetFormatterHook) -> None:
        """Registra um formatador externo que será aplicado a todas as exportações."""
        self._external_hooks.append(hook)

    # ------------------------------------------------------------------ #
    # Persistência de Modelos CSV (`modelos_csv` / `modelos_csv_campos`)
    # ------------------------------------------------------------------ #
    def save_csv_mapping(self, mapping: CSVColumnMapping) -> str:
        """Salva um modelo de mapeamento CSV nas tabelas `modelos_csv` e `modelos_csv_campos`."""
        model_id = mapping.id.strip() or uuid.uuid4().hex[:12]
        mapping.id = model_id
        field_pairs = [
            ("data", mapping.col_data),
            ("descricao", mapping.col_descricao),
            ("valor", mapping.col_valor),
            ("categoria", mapping.col_categoria),
            ("subcategoria", mapping.col_subcategoria),
            ("tipo", mapping.col_tipo),
            ("situacao", mapping.col_situacao),
            ("conta", mapping.col_conta),
            ("cartao", mapping.col_cartao),
            ("tags", mapping.col_tags),
            ("observacoes", mapping.col_observacoes),
        ]
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT OR REPLACE INTO modelos_csv (
                    id, valor_negativo_despesas, descricao, observacoes,
                    id_conta, id_cartao, separador, possui_cabecalho, formato_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_id,
                    "S" if mapping.valor_negativo_despesas else "N",
                    mapping.descricao_modelo.strip() or "Modelo CSV",
                    mapping.observacoes,
                    mapping.id_conta,
                    mapping.id_cartao,
                    mapping.separador or ";",
                    "S" if mapping.possui_cabecalho else "N",
                    mapping.formato_data or "dd/MM/yyyy",
                ),
            )
            cur.execute("DELETE FROM modelos_csv_campos WHERE id_modelo = ?", (model_id,))
            for field_name, col_idx in field_pairs:
                if col_idx is not None:
                    cur.execute(
                        """
                        INSERT INTO modelos_csv_campos (id, coluna, id_modelo, campo)
                        VALUES (?, ?, ?, ?)
                        """,
                        (uuid.uuid4().hex[:12], int(col_idx), model_id, field_name),
                    )
        return model_id

    def list_csv_mappings(self) -> List[CSVColumnMapping]:
        """Lista todos os modelos CSV salvos no banco de dados."""
        models = self.db.execute_query("SELECT * FROM modelos_csv ORDER BY descricao ASC")
        result: List[CSVColumnMapping] = []
        for m in models:
            mid = str(m["id"])
            fields = self.db.execute_query(
                "SELECT campo, coluna FROM modelos_csv_campos WHERE id_modelo = ?",
                (mid,),
            )
            fmap = {str(f["campo"]): int(f["coluna"]) for f in fields if f["coluna"] is not None}
            result.append(
                CSVColumnMapping(
                    id=mid,
                    descricao_modelo=str(m["descricao"] or "Modelo CSV"),
                    separador=str(m["separador"] or ";"),
                    possui_cabecalho=str(m["possui_cabecalho"] or "S").upper() == "S",
                    formato_data=str(m["formato_data"] or "dd/MM/yyyy"),
                    valor_negativo_despesas=str(m["valor_negativo_despesas"] or "S").upper() == "S",
                    observacoes=str(m["observacoes"] or ""),
                    id_conta=m["id_conta"],
                    id_cartao=m["id_cartao"],
                    col_data=fmap.get("data"),
                    col_descricao=fmap.get("descricao"),
                    col_valor=fmap.get("valor"),
                    col_categoria=fmap.get("categoria"),
                    col_subcategoria=fmap.get("subcategoria"),
                    col_tipo=fmap.get("tipo"),
                    col_situacao=fmap.get("situacao"),
                    col_conta=fmap.get("conta"),
                    col_cartao=fmap.get("cartao"),
                    col_tags=fmap.get("tags"),
                    col_observacoes=fmap.get("observacoes"),
                )
            )
        return result

    def delete_csv_mapping(self, model_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM modelos_csv_campos WHERE id_modelo = ?", (model_id,))
            cur.execute("DELETE FROM modelos_csv WHERE id = ?", (model_id,))

    # ------------------------------------------------------------------ #
    # Resolução de Entidades para Importação
    # ------------------------------------------------------------------ #
    def _resolve_or_create_category(
        self, kind: str, cat_name: str, sub_name: str, profile_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        if kind == KIND_TRANSFERENCIA:
            return None, None
        repo_kind = "RECEITA" if kind == KIND_RECEITA else "DESPESA"
        cats = self.categories.list_categories(repo_kind, profile_id)
        norm_cat = normalize_text_for_hash(cat_name or "Outros")
        norm_sub = normalize_text_for_hash(sub_name or "Outros")

        matched_cat = next(
            (c for c in cats if normalize_text_for_hash(c.nome) == norm_cat),
            None,
        )
        if matched_cat is None and norm_cat and norm_cat != "outros":
            matched_cat = self.categories.create_category(
                repo_kind, cat_name.strip(), profile_id=profile_id
            )
        elif matched_cat is None and cats:
            matched_cat = next(
                (c for c in cats if normalize_text_for_hash(c.nome) == "outros"),
                cats[0],
            )
        elif matched_cat is None:
            matched_cat = self.categories.create_category(
                repo_kind, "Outros", profile_id=profile_id
            )

        matched_sub = next(
            (
                s
                for s in matched_cat.subcategories
                if normalize_text_for_hash(s.nome) == norm_sub
            ),
            None,
        )
        if matched_sub is None and norm_sub and norm_sub != "outros":
            matched_sub = self.categories.create_subcategory(
                repo_kind, matched_cat.id, sub_name.strip(), profile_id=profile_id
            )
        elif matched_sub is None and matched_cat.subcategories:
            matched_sub = matched_cat.subcategories[0]
        elif matched_sub is None:
            matched_sub = self.categories.create_subcategory(
                repo_kind, matched_cat.id, "Outros", profile_id=profile_id
            )

        return matched_cat.id, matched_sub.id

    def _resolve_account_id(
        self, account_name: str, fallback_account_id: Optional[str], profile_id: str
    ) -> Optional[str]:
        rows = self.db.execute_query(
            "SELECT id, descricao, padrao FROM contas WHERE id_profile = ? AND data_exclusao IS NULL ORDER BY sequence ASC",
            (str(profile_id),),
        )
        if account_name.strip():
            norm_target = normalize_text_for_hash(account_name)
            for r in rows:
                if normalize_text_for_hash(str(r["descricao"] or "")) == norm_target:
                    return str(r["id"])
            # Cria a conta caso tenha nome explícito na planilha e não exista
            return self.accounts.create_account(
                descricao=account_name.strip(), profile_id=profile_id
            )
        if fallback_account_id:
            return str(fallback_account_id)
        for r in rows:
            if str(r["padrao"] or "").upper() == "S":
                return str(r["id"])
        if rows:
            return str(rows[0]["id"])
        return self.accounts.create_account(
            descricao="Conta Principal", padrao="S", profile_id=profile_id
        )

    def _resolve_card_id(
        self, card_name: str, fallback_card_id: Optional[str], profile_id: str
    ) -> Optional[str]:
        if fallback_card_id:
            return str(fallback_card_id)
        if not card_name.strip():
            return None
        cards = self.cards.list_cards(profile_id=profile_id)
        norm_c = normalize_text_for_hash(card_name)
        for c in cards:
            if normalize_text_for_hash(c.nome) == norm_c:
                return c.id
        return None

    def _resolve_tag_ids(self, tag_names: Sequence[str], profile_id: str) -> List[str]:
        if not tag_names:
            return []
        existing = self.tags.list_tags(profile_id=profile_id, include_archived=True)
        by_norm = {normalize_text_for_hash(t.nome): t.id for t in existing}
        ids: List[str] = []
        for raw_name in tag_names:
            clean = raw_name.strip().lstrip("#")
            if not clean:
                continue
            norm = normalize_text_for_hash(clean)
            if norm in by_norm:
                ids.append(by_norm[norm])
            else:
                created = self.tags.create_tag(clean, profile_id=profile_id)
                by_norm[norm] = created.id
                ids.append(created.id)
        return ids

    # ------------------------------------------------------------------ #
    # IMPORTAÇÃO (CSV / XLSX -> SQLite)
    # ------------------------------------------------------------------ #
    def import_file(
        self,
        file_path: Path | str,
        *,
        profile_id: str = "1",
        target_account_id: Optional[str] = None,
        target_card_id: Optional[str] = None,
        default_kind: str = KIND_DESPESA,
        mapping: Optional[CSVColumnMapping] = None,
        skip_duplicates: bool = True,
    ) -> ImportReport:
        """
        Importa um arquivo `.csv` ou `.xlsx` para o banco SQLite, resolvendo categorias,
        contas, cartões e tags, e aplicando prevenção determinística de duplicidades.
        """
        path = Path(file_path)
        ext = path.suffix.lower().lstrip(".")
        fmt_type = "xlsx" if ext in ("xlsx", "xlsm") else "csv"

        # Limpa o cache de fingerprints em memória de importações anteriores
        self.dup_checker.clear_memory()

        if fmt_type == "xlsx":
            rows = self.excel_handler.parse_file(
                path, default_kind=default_kind, mapping=mapping
            )
        else:
            rows = self.csv_handler.parse_file(
                path, default_kind=default_kind, mapping=mapping
            )

        report = ImportReport(
            source_path=str(path),
            format_type=fmt_type,
            total_rows_read=len(rows),
        )

        series_origins: Dict[Tuple[str, str, int, float], str] = {}

        invoice_due_from_filename = extract_invoice_due_date_from_filename(path)
        pos_count = sum(1 for r in rows if not getattr(r, "is_negative", False))
        neg_count = sum(1 for r in rows if getattr(r, "is_negative", False))
        card_purchases_are_positive = pos_count >= neg_count

        income_cats = self.categories.list_categories(KIND_RECEITA, profile_id)
        EXPLICIT_INCOME_CATS = {
            "salario", "salário", "salarios", "salários", "rendimento", "rendimentos",
            "provento", "proventos", "receita", "receitas", "comissao", "comissão"
        }

        for row in rows:
            try:
                is_neg_row = bool(getattr(row, "is_negative", False))
                potential_card_id = self._resolve_card_id(row.cartao, target_card_id, profile_id)
                is_strict_card_ctx = bool(
                    target_card_id
                    or invoice_due_from_filename is not None
                    or (
                        potential_card_id
                        and (
                            not row.conta
                            or normalize_text_for_hash(row.conta)
                            != normalize_text_for_hash(row.cartao)
                        )
                    )
                )

                # Ignora pagamentos de fatura anterior em extratos de cartão (ex.: 'Pagamento recebido')
                if is_credit_card_invoice_payment(
                    row.descricao,
                    is_neg=is_neg_row,
                    is_card_context=bool(potential_card_id or is_strict_card_ctx),
                ):
                    report.skipped_invoice_payments += 1
                    continue

                kind_norm = (row.kind or default_kind).lower()
                desc_norm = normalize_text_for_hash(row.descricao)
                cat_norm = normalize_text_for_hash(row.categoria)

                is_card_refund = False
                if potential_card_id and (is_strict_card_ctx or is_neg_row) and is_credit_card_refund(
                    row.descricao,
                    is_neg=is_neg_row,
                    card_purchases_are_positive=card_purchases_are_positive,
                ):
                    kind_norm = "despesa"
                    row.kind = "despesa"
                    is_card_refund = True

                if not is_card_refund and kind_norm != "transferencia" and kind_norm != "receita":
                    if cat_norm in EXPLICIT_INCOME_CATS:
                        kind_norm = "receita"
                        row.kind = "receita"

                if kind_norm == "receita" and cat_norm in ("", "outros"):
                    if "salario" in desc_norm:
                        matched_sal = next(
                            (c.nome for c in income_cats if "salario" in normalize_text_for_hash(c.nome)),
                            None,
                        )
                        if matched_sal:
                            row.categoria = matched_sal

                # 2. Resolução inteligente de conta bancária e cartão de crédito
                card_id: Optional[str] = None
                acc_id: Optional[str] = None

                if kind_norm == "receita" and not is_card_refund:
                    # Receitas não vão para cartão de crédito
                    card_id = None
                    temp_card_id = self._resolve_card_id(row.conta or row.cartao, None, profile_id)
                    if temp_card_id:
                        c_obj = self.cards.get_card(temp_card_id)
                        c_acc = c_obj.id_conta if c_obj else None
                        acc_id = self._resolve_account_id("", c_acc or target_account_id, profile_id)
                    else:
                        acc_id = self._resolve_account_id(row.conta, target_account_id, profile_id)
                elif kind_norm.startswith("trans"):
                    card_id = None
                    acc_id = self._resolve_account_id(row.conta, target_account_id, profile_id)
                else:
                    card_id = potential_card_id
                    if card_id:
                        c_obj = self.cards.get_card(card_id)
                        c_acc = (c_obj.id_conta if c_obj else None) or target_account_id
                        acc_name_to_use = (
                            ""
                            if normalize_text_for_hash(row.conta) == normalize_text_for_hash(row.cartao)
                            else row.conta
                        )
                        acc_id = self._resolve_account_id(acc_name_to_use, c_acc, profile_id)
                    else:
                        acc_id = self._resolve_account_id(row.conta, target_account_id, profile_id)

                compute_row_fingerprint(
                    row,
                    target_account_id=acc_id or "",
                    target_card_id=card_id or "",
                    profile_id=profile_id,
                )

                if skip_duplicates and self.dup_checker.is_duplicate(
                    row,
                    target_account_id=acc_id or "",
                    target_card_id=card_id or "",
                    profile_id=profile_id,
                ):
                    report.skipped_duplicates += 1
                    continue

                tag_ids = self._resolve_tag_ids(row.tags, profile_id)
                kind_upper = (row.kind or default_kind).upper()

                if kind_upper.startswith("TRANS"):
                    dest_id = self._resolve_account_id(
                        row.conta_destino or "Conta Destino", None, profile_id
                    )
                    if dest_id == acc_id:
                        dest_id = self.accounts.create_account(
                            descricao=row.conta_destino or "Conta Destino Importada",
                            profile_id=profile_id,
                        )
                    created_ids = self.tx.create_transfer(
                        descricao=row.descricao,
                        valor=row.valor,
                        data=row.data_vencimento,
                        id_conta_origem=str(acc_id),
                        id_conta_destino=str(dest_id),
                        profile_id=profile_id,
                        efetivada=row.efetivada,
                        data_efetivacao=row.data_efetivacao,
                        obs=row.observacoes,
                        tag_ids=tag_ids,
                    )
                elif kind_upper.startswith("REC"):
                    cat_id, sub_id = self._resolve_or_create_category(
                        KIND_RECEITA, row.categoria, row.subcategoria, profile_id
                    )
                    created_ids = self.tx.create_income(
                        descricao=row.descricao,
                        valor=row.valor,
                        data=row.data_vencimento,
                        id_conta=acc_id,
                        profile_id=profile_id,
                        id_categoria=cat_id,
                        id_subcategoria=sub_id,
                        data_evento=row.data_lancamento,
                        recebido=row.efetivada,
                        data_efetivacao=row.data_efetivacao,
                        obs=row.observacoes,
                        tag_ids=tag_ids,
                    )
                else:
                    cat_id, sub_id = self._resolve_or_create_category(
                        KIND_DESPESA, row.categoria, row.subcategoria, profile_id
                    )
                    num_p = getattr(row, "num_parcela", 1) or 1
                    tot_p = getattr(row, "num_parcelas", 1) or 1
                    origin_id = None
                    if tot_p > 1 and not is_card_refund:
                        base_key = re.sub(
                            r"[-–—/(]?\s*(?:parcela\s*)?\d{1,2}\s*(?:/|de)\s*\d{1,2}\s*[)]?$",
                            "",
                            row.descricao,
                            flags=re.IGNORECASE,
                        ).strip().lower()
                        cache_key = (base_key, card_id or acc_id or "", tot_p, round(abs(row.valor), 1))
                        if cache_key in series_origins:
                            origin_id = series_origins[cache_key]
                        else:
                            found = self.db.execute_query(
                                """
                                SELECT id_origem FROM despesas
                                WHERE id_profile = ? AND num_parcelas = ?
                                  AND (id_cartao_credito = ? OR (id_cartao_credito IS NULL AND id_conta = ?))
                                  AND LOWER(descricao) LIKE ?
                                  AND ABS(COALESCE(valor, 0) - ?) < 0.05
                                LIMIT 1
                                """,
                                (
                                    str(profile_id),
                                    tot_p,
                                    card_id,
                                    acc_id,
                                    f"%{base_key[:12]}%",
                                    abs(row.valor),
                                ),
                            )
                            if found and found[0]["id_origem"]:
                                origin_id = str(found[0]["id_origem"])
                            else:
                                origin_id = uuid.uuid4().hex[:16]
                            series_origins[cache_key] = origin_id

                    exp_valor = -abs(row.valor) if (card_id and is_card_refund) else row.valor
                    exp_due_date = row.data_vencimento
                    preserve_due = False
                    if card_id and invoice_due_from_filename is not None:
                        c_obj_due = self.cards.get_card(card_id)
                        venc_day = c_obj_due.dia_venc if c_obj_due else invoice_due_from_filename.day
                        exp_due_date = date(
                            invoice_due_from_filename.year,
                            invoice_due_from_filename.month,
                            clamp_day(
                                invoice_due_from_filename.year,
                                invoice_due_from_filename.month,
                                venc_day,
                            ),
                        )
                        preserve_due = True

                    created_ids = self.tx.create_expense(
                        descricao=row.descricao,
                        valor=exp_valor,
                        data_vencimento=exp_due_date,
                        profile_id=profile_id,
                        id_conta=acc_id,
                        id_cartao=card_id,
                        data_evento=row.data_lancamento,
                        id_categoria=cat_id,
                        id_subcategoria=sub_id,
                        pago=row.efetivada and not card_id,
                        data_efetivacao=row.data_efetivacao,
                        obs=row.observacoes,
                        tag_ids=tag_ids,
                        recorrencia=REC_PARCELADA if (tot_p > 1 and not is_card_refund) else REC_UNICA,
                        num_parcela=num_p if (tot_p > 1 and not is_card_refund) else None,
                        num_parcelas=1 if is_card_refund else tot_p,
                        id_origem=origin_id,
                        preserve_due_date=preserve_due,
                    )

                tx_id = created_ids[0] if created_ids else ""
                self.dup_checker.register_imported(
                    row, tx_id, profile_id=profile_id, source_file=path.name
                )
                report.imported_count += 1
                report.imported_ids.extend(created_ids)
            except Exception as exc:
                report.error_count += 1
                report.errors.append(f"Linha {row.raw_row_index}: {exc}")

        return report

    # ------------------------------------------------------------------ #
    # EXPORTAÇÃO (SQLite -> CSV / XLSX)
    # ------------------------------------------------------------------ #
    def _occurrences_to_canonical(
        self, occurrences: Sequence[Occurrence]
    ) -> List[CanonicalTransactionRow]:
        rows: List[CanonicalTransactionRow] = []
        for occ in occurrences:
            tag_names = [str(t[1]) for t in occ.tags]
            rec_label = (
                f"Parcela {occ.num_parcela}/{occ.num_parcelas}"
                if occ.num_parcelas > 1
                else ("Fixa" if occ.is_fixed else "Única")
            )
            rows.append(
                CanonicalTransactionRow(
                    kind=occ.kind.lower(),
                    descricao=occ.descricao,
                    valor=occ.total,
                    data_vencimento=occ.data_vencimento,
                    data_lancamento=occ.data_evento or occ.data_vencimento,
                    data_efetivacao=occ.data_efetivacao,
                    efetivada=occ.efetivada,
                    categoria=occ.categoria_nome or "Outros",
                    subcategoria=occ.subcategoria_nome or "Outros",
                    conta=occ.conta_nome or "",
                    conta_destino=occ.conta_destino_nome or "",
                    cartao=occ.cartao_nome or "",
                    recorrencia=rec_label,
                    tags=tag_names,
                    observacoes=occ.obs or "",
                )
            )
        return rows

    def export_month_data(
        self,
        file_path: Path | str,
        *,
        year: int,
        month: int,
        profile_id: str = "1",
        date_mode: str = "vencimento",
        export_mode: str = "extrato",
        external_hooks: Optional[Sequence[ExternalSpreadsheetFormatterHook]] = None,
    ) -> ExportReport:
        """
        Exporta os lançamentos do mês (ou resumo por categoria) para `.csv` ou `.xlsx`.
        Suporta `export_mode` em `('extrato', 'despesas', 'receitas', 'transferencias', 'categorias', 'completo')`.
        """
        path = Path(file_path)
        ext = path.suffix.lower().lstrip(".")
        mode_norm = (export_mode or "extrato").lower()

        kinds_filter: Optional[List[str]] = None
        if mode_norm == "despesas":
            kinds_filter = [KIND_DESPESA]
        elif mode_norm == "receitas":
            kinds_filter = [KIND_RECEITA]
        elif mode_norm == "transferencias":
            kinds_filter = [KIND_TRANSFERENCIA]

        occs = self.tx.list_occurrences(
            year,
            month,
            mode=date_mode,
            profile_id=profile_id,
            kinds=kinds_filter,
        )
        canonical_rows = self._occurrences_to_canonical(occs)

        cat_summary: List[CategorySummaryRow] = []
        if mode_norm in ("categorias", "completo"):
            breakdown = self.analytics.category_breakdown(
                year,
                month,
                kind=KIND_DESPESA,
                mode=date_mode,
                profile_id=profile_id,
            )
            cat_summary = [
                CategorySummaryRow(
                    categoria=b.categoria_nome,
                    total=b.total,
                    percentual=b.percentual,
                    quantidade=b.quantidade,
                )
                for b in breakdown
            ]

        combined_hooks = [*self._external_hooks, *(external_hooks or [])]
        if ext in ("xlsx", "xlsm"):
            return self.excel_handler.export_transactions(
                path,
                canonical_rows,
                mode=mode_norm,
                category_summary=cat_summary,
                external_hooks=combined_hooks,
            )
        return self.csv_handler.export_transactions(
            path,
            canonical_rows,
            mode=mode_norm,
            category_summary=cat_summary,
            external_hooks=combined_hooks,
        )
