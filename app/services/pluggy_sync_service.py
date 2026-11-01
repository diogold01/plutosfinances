"""Serviço de Mapeamento, Normalização e Sincronização Open Finance (Pluggy).

Converte dados brutos da API Pluggy em entidades do Plutos:
- Contas correntes e poupanças -> Contas Plutos (`contas`)
- Investimentos (CDB, Caixinhas, Ações) -> Contas Plutos de Investimento independentes (Abordagem 1)
- Lançamentos bancários -> CanonicalTransactionRow (`app/io_module/contracts.py`)
- Deduplicação determinística via SHA-256 (`app/io_module/duplicate_checker.py`)
- Persistência atômica no SQLite com reconciliação opcional de saldos e investimentos
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService
from app.io_module.contracts import CanonicalTransactionRow
from app.io_module.csv_handler import is_credit_card_invoice_payment
from app.io_module.duplicate_checker import (
    DuplicateChecker,
    compute_row_fingerprint,
    normalize_text_for_hash,
)
from app.services.pluggy_client import PluggyClient, PluggyConnectedItem


@dataclass
class MappedAccountDTO:
    """Representação de uma conta ou investimento normalizado pronto para o Plutos."""

    external_id: str
    nome: str
    tipo_plutos: str  # 'CONTA' ou 'INVESTIMENTO' ou 'CARTAO'
    saldo_atual: float
    moeda: str = "BRL"
    instituicao_nome: str = ""
    detalhes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncBatchResult:
    """Resultado da normalização e checagem de duplicidade de um lote de transações."""

    account: MappedAccountDTO
    novas_transacoes: List[CanonicalTransactionRow] = field(default_factory=list)
    duplicadas_ignoradas: List[CanonicalTransactionRow] = field(default_factory=list)

    @property
    def total_novas(self) -> int:
        return len(self.novas_transacoes)

    @property
    def total_duplicadas(self) -> int:
        return len(self.duplicadas_ignoradas)


@dataclass
class SyncApplySummary:
    """Resumo consolidado após efetivação da sincronização no banco SQLite."""

    contas_criadas: int = 0
    contas_atualizadas: int = 0
    investimentos_atualizados: int = 0
    cartoes_sincronizados: int = 0
    transacoes_importadas: int = 0
    duplicadas_ignoradas: int = 0


class PluggySyncService:
    """Serviço responsável por traduzir e persistir dados da Pluggy no modelo de domínio do Plutos."""

    def __init__(self, client: PluggyClient, db: Optional[ConnectionManager] = None) -> None:
        self.client = client
        self.db = db
        self.duplicate_checker = DuplicateChecker(db)

    # ------------------------------------------------------------------ #
    # 1. Mapeamento de Contas e Múltiplos Investimentos (Abordagem 1)
    # ------------------------------------------------------------------ #
    def map_bank_accounts(
        self, raw_accounts: List[Dict[str, Any]], institution_name: str = ""
    ) -> List[MappedAccountDTO]:
        """Mapeia contas correntes, poupanças e cartões."""
        mapped = []
        for acc in raw_accounts:
            acc_id = str(acc.get("id") or "")
            acc_type = str(acc.get("type") or "BANK").upper()
            acc_name = acc.get("marketingName") or acc.get("name") or "Conta Bancária"
            balance = float(acc.get("balance") or 0.0)

            full_name = f"{institution_name} - {acc_name}" if institution_name else acc_name

            tipo_plutos = "CARTAO" if acc_type == "CREDIT" else "CONTA"
            mapped.append(
                MappedAccountDTO(
                    external_id=acc_id,
                    nome=full_name,
                    tipo_plutos=tipo_plutos,
                    saldo_atual=balance,
                    moeda=acc.get("currencyCode") or "BRL",
                    instituicao_nome=institution_name,
                    detalhes=acc,
                )
            )
        return mapped

    def map_investments_to_accounts(
        self, raw_investments: List[Dict[str, Any]], institution_name: str = ""
    ) -> List[MappedAccountDTO]:
        """
        Aplica a Abordagem 1 aprovada:
        Transforma cada investimento retornado (CDB 100% CDI, Caixinha Nubank, etc.)
        em uma conta independente do tipo INVESTIMENTO no Plutos.
        """
        mapped = []
        for inv in raw_investments:
            inv_id = str(inv.get("id") or "")
            inv_name = inv.get("name") or inv.get("subtype") or "Investimento"
            balance = float(inv.get("balance") or inv.get("amount") or inv.get("value") or 0.0)

            full_name = f"{institution_name} - {inv_name}" if institution_name else inv_name

            mapped.append(
                MappedAccountDTO(
                    external_id=inv_id,
                    nome=full_name,
                    tipo_plutos="INVESTIMENTO",
                    saldo_atual=balance,
                    moeda=inv.get("currencyCode") or "BRL",
                    instituicao_nome=institution_name,
                    detalhes=inv,
                )
            )
        return mapped

    # ------------------------------------------------------------------ #
    # 2. Normalização de Transações para CanonicalTransactionRow
    # ------------------------------------------------------------------ #
    def normalize_transaction(
        self,
        raw_tx: Dict[str, Any],
        account_name: str = "",
        is_credit_card: bool = False,
    ) -> Optional[CanonicalTransactionRow]:
        """Converte um objeto de transação da Pluggy em CanonicalTransactionRow."""
        desc = (raw_tx.get("description") or raw_tx.get("descriptionRaw") or "Lançamento sem descrição").strip()
        raw_val = float(raw_tx.get("amount") or 0.0)
        if raw_val == 0.0:
            return None

        # Ignora pagamentos de fatura em extratos de cartão de crédito para não duplicar saldo
        if is_credit_card and is_credit_card_invoice_payment(
            desc, is_neg=(raw_val < 0), is_card_context=True
        ):
            return None

        # Data do lançamento
        dt_str = raw_tx.get("date") or ""
        try:
            tx_date = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).date()
        except Exception:
            try:
                tx_date = datetime.strptime(dt_str[:10], "%Y-%m-%d").date()
            except Exception:
                tx_date = date.today()

        tx_type = str(raw_tx.get("type") or "").upper()
        if is_credit_card:
            kind = "despesa"
            val = abs(raw_val)
        elif raw_val < 0 or tx_type == "DEBIT":
            kind = "despesa"
            val = abs(raw_val)
        else:
            kind = "receita"
            val = abs(raw_val)

        category = raw_tx.get("category") or "Outros"
        external_id = raw_tx.get("id") or ""
        obs = f"Pluggy ID: {external_id}" if external_id else ""

        return CanonicalTransactionRow(
            kind=kind,
            descricao=desc,
            valor=round(val, 2),
            data_vencimento=tx_date,
            data_lancamento=tx_date,
            data_efetivacao=tx_date if (raw_tx.get("status") == "POSTED" and not is_credit_card) else None,
            efetivada=(raw_tx.get("status") == "POSTED" and not is_credit_card),
            categoria=category,
            subcategoria="Outros",
            conta="" if is_credit_card else account_name,
            cartao=account_name if is_credit_card else "",
            observacoes=obs,
        )

    # ------------------------------------------------------------------ #
    # 3. Motor de Deduplicação & Processamento em Lote
    # ------------------------------------------------------------------ #
    def process_transactions_batch(
        self,
        account: MappedAccountDTO,
        raw_transactions: List[Dict[str, Any]],
        *,
        target_account_id: str = "",
        target_card_id: str = "",
        profile_id: str = "1",
        persist_fingerprints: bool = False,
    ) -> SyncBatchResult:
        """
        Normaliza a lista de transações e separa as novas das duplicadas
        utilizando o DuplicateChecker canônico do Plutos.
        """
        result = SyncBatchResult(account=account)
        is_card = account.tipo_plutos == "CARTAO"

        for raw_tx in raw_transactions:
            row = self.normalize_transaction(
                raw_tx, account_name=account.nome, is_credit_card=is_card
            )
            if not row:
                continue

            eff_acc_id = "" if is_card else (target_account_id or account.external_id)
            eff_card_id = (target_card_id or account.external_id) if is_card else ""

            fp = compute_row_fingerprint(
                row,
                target_account_id=eff_acc_id,
                target_card_id=eff_card_id,
                profile_id=profile_id,
            )

            if self.duplicate_checker.is_duplicate(
                row,
                target_account_id=eff_acc_id,
                target_card_id=eff_card_id,
                profile_id=profile_id,
            ):
                result.duplicadas_ignoradas.append(row)
            else:
                if persist_fingerprints:
                    self.duplicate_checker.register_imported(
                        row,
                        transaction_id=raw_tx.get("id") or "",
                        profile_id=profile_id,
                        source_file="pluggy_open_finance",
                    )
                else:
                    self.duplicate_checker._memory_seen.add(fp)
                result.novas_transacoes.append(row)

        return result

    # ------------------------------------------------------------------ #
    # 4. Coleta Completa de Pré-visualização (Preview Assíncrono)
    # ------------------------------------------------------------------ #
    def _find_existing_account_id(self, name: str, profile_id: str) -> str:
        if self.db is None or not name.strip():
            return ""
        norm_target = normalize_text_for_hash(name)
        rows = self.db.execute_query(
            "SELECT id, descricao FROM contas WHERE id_profile = ? AND data_exclusao IS NULL",
            (str(profile_id),),
        )
        for r in rows:
            if normalize_text_for_hash(str(r["descricao"] or "")) == norm_target:
                return str(r["id"])
        return ""

    def _find_existing_card_id(self, name: str, profile_id: str) -> str:
        if self.db is None or not name.strip():
            return ""
        cards = CreditCardService(self.db).list_cards(profile_id=profile_id)
        norm_target = normalize_text_for_hash(name)
        for c in cards:
            if normalize_text_for_hash(c.nome) == norm_target:
                return c.id
        return ""

    def fetch_full_preview(
        self,
        items: List[PluggyConnectedItem],
        *,
        profile_id: str = "1",
        from_date: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> List[SyncBatchResult]:
        """
        Consulta na API da Pluggy todas as contas, cartões, investimentos e transações
        das instituições conectadas e devolve a prévia pronta para revisão na UI.
        """
        self.duplicate_checker.clear_memory()
        batches: List[SyncBatchResult] = []
        total_items = max(1, len(items))

        for idx, item in enumerate(items):
            base_pct = int((idx / total_items) * 85)
            inst_name = item.connector_name or "Instituição"
            if progress_callback:
                progress_callback(base_pct + 5, f"Consultando contas de {inst_name}...")

            raw_accounts = self.client.fetch_accounts(item.item_id)
            mapped_accounts = self.map_bank_accounts(raw_accounts, institution_name=inst_name)

            for acc in mapped_accounts:
                if progress_callback:
                    progress_callback(base_pct + 15, f"Baixando lançamentos de {acc.nome}...")
                raw_txs = self.client.fetch_transactions(acc.external_id, from_date=from_date)
                existing_acc_id = (
                    self._find_existing_account_id(acc.nome, profile_id)
                    if acc.tipo_plutos != "CARTAO"
                    else ""
                )
                existing_card_id = (
                    self._find_existing_card_id(acc.nome, profile_id)
                    if acc.tipo_plutos == "CARTAO"
                    else ""
                )
                batch = self.process_transactions_batch(
                    acc,
                    raw_txs,
                    target_account_id=existing_acc_id,
                    target_card_id=existing_card_id,
                    profile_id=profile_id,
                    persist_fingerprints=False,
                )
                batches.append(batch)

            if progress_callback:
                progress_callback(base_pct + 20, f"Consultando investimentos de {inst_name}...")

            raw_investments = self.client.fetch_investments(item.item_id)
            mapped_investments = self.map_investments_to_accounts(
                raw_investments, institution_name=inst_name
            )
            for inv in mapped_investments:
                batches.append(SyncBatchResult(account=inv))

        if progress_callback:
            progress_callback(100, "Pré-visualização concluída!")
        return batches

    # ------------------------------------------------------------------ #
    # 5. Efetivação Atômica no Banco SQLite
    # ------------------------------------------------------------------ #
    def _resolve_or_create_category(
        self,
        cat_repo: CategoryRepository,
        kind: str,
        cat_name: str,
        sub_name: str,
        profile_id: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        repo_kind = "RECEITA" if kind == KIND_RECEITA else "DESPESA"
        cats = cat_repo.list_categories(repo_kind, profile_id)
        norm_cat = normalize_text_for_hash(cat_name or "Outros")
        norm_sub = normalize_text_for_hash(sub_name or "Outros")

        matched_cat = next(
            (c for c in cats if normalize_text_for_hash(c.nome) == norm_cat),
            None,
        )
        if matched_cat is None and norm_cat and norm_cat != "outros":
            matched_cat = cat_repo.create_category(
                repo_kind, cat_name.strip(), profile_id=profile_id
            )
        elif matched_cat is None and cats:
            matched_cat = next(
                (c for c in cats if normalize_text_for_hash(c.nome) == "outros"),
                cats[0],
            )
        elif matched_cat is None:
            matched_cat = cat_repo.create_category(
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
        if matched_sub is None and matched_cat.subcategories:
            matched_sub = matched_cat.subcategories[0]
        elif matched_sub is None:
            matched_sub = cat_repo.create_subcategory(
                repo_kind, matched_cat.id, "Outros", profile_id=profile_id
            )

        return matched_cat.id, matched_sub.id

    def apply_sync_results(
        self,
        batches: List[SyncBatchResult],
        *,
        profile_id: str = "1",
        mes: Optional[int] = None,
        ano: Optional[int] = None,
        reconcile_balances: bool = True,
    ) -> SyncApplySummary:
        """
        Persiste as contas, cartões, investimentos e novas transações aprovadas pelo usuário
        no banco de dados SQLite local.
        """
        if self.db is None:
            raise RuntimeError("ConnectionManager (db) é obrigatório para aplicar sincronização.")

        today = date.today()
        target_mes = mes or today.month
        target_ano = ano or today.year

        acc_repo = AccountRepository(self.db)
        cat_repo = CategoryRepository(self.db)
        tx_service = TransactionService(self.db)
        card_service = CreditCardService(self.db, tx_service)

        summary = SyncApplySummary()

        for batch in batches:
            acc = batch.account
            summary.duplicadas_ignoradas += batch.total_duplicadas

            if acc.tipo_plutos == "CARTAO":
                card_id = self._find_existing_card_id(acc.nome, profile_id)
                if not card_id:
                    credit_data = acc.detalhes.get("creditData") or {}
                    limite = float(credit_data.get("creditLimit") or 5000.0)
                    dia_f = 1
                    dia_v = 10
                    close_str = str(credit_data.get("balanceCloseDate") or "")
                    due_str = str(credit_data.get("balanceDueDate") or "")
                    if len(close_str) >= 10:
                        try:
                            dia_f = int(close_str[8:10])
                        except ValueError:
                            pass
                    if len(due_str) >= 10:
                        try:
                            dia_v = int(due_str[8:10])
                        except ValueError:
                            pass
                    created_card = card_service.create_card(
                        nome=acc.nome,
                        limite=limite,
                        dia_fecha=dia_f,
                        dia_venc=dia_v,
                        profile_id=profile_id,
                        color_hex="#E5603D",
                    )
                    card_id = created_card.id

                summary.cartoes_sincronizados += 1

                for row in batch.novas_transacoes:
                    cat_id, sub_id = self._resolve_or_create_category(
                        cat_repo, KIND_DESPESA, row.categoria, row.subcategoria, profile_id
                    )
                    compute_row_fingerprint(
                        row,
                        target_account_id="",
                        target_card_id=card_id,
                        profile_id=profile_id,
                    )
                    if self.duplicate_checker.is_duplicate(
                        row,
                        target_account_id="",
                        target_card_id=card_id,
                        profile_id=profile_id,
                    ):
                        summary.duplicadas_ignoradas += 1
                        continue

                    created_ids = tx_service.create_expense(
                        descricao=row.descricao,
                        valor=row.valor,
                        data_vencimento=row.data_vencimento,
                        profile_id=profile_id,
                        id_cartao=card_id,
                        data_evento=row.data_lancamento,
                        id_categoria=cat_id,
                        id_subcategoria=sub_id,
                        pago=False,
                        obs=row.observacoes,
                    )
                    tx_id = created_ids[0] if created_ids else ""
                    self.duplicate_checker.register_imported(
                        row,
                        tx_id,
                        profile_id=profile_id,
                        source_file="pluggy_open_finance",
                    )
                    summary.transacoes_importadas += 1

            else:
                is_inv = "S" if acc.tipo_plutos == "INVESTIMENTO" else "N"
                acc_id = self._find_existing_account_id(acc.nome, profile_id)
                if not acc_id:
                    from app.ui.bank_icons import resolve_bank_image_key

                    img_key = (
                        resolve_bank_image_key(acc.instituicao_nome, acc.nome)
                        or "ic_banco_default.png"
                    )
                    acc_id = acc_repo.create_account(
                        descricao=acc.nome,
                        saldo_inicial=acc.saldo_atual if not batch.novas_transacoes else 0.0,
                        investimento=is_inv,
                        image_key=img_key,
                        profile_id=profile_id,
                        currency=acc.moeda or "BRL",
                        mes_inicial=target_mes,
                        ano_inicial=target_ano,
                    )
                    if is_inv == "S":
                        summary.investimentos_atualizados += 1
                    else:
                        summary.contas_criadas += 1
                else:
                    if is_inv == "S":
                        summary.investimentos_atualizados += 1
                    else:
                        summary.contas_atualizadas += 1

                for row in batch.novas_transacoes:
                    compute_row_fingerprint(
                        row,
                        target_account_id=acc_id,
                        target_card_id="",
                        profile_id=profile_id,
                    )
                    if self.duplicate_checker.is_duplicate(
                        row,
                        target_account_id=acc_id,
                        target_card_id="",
                        profile_id=profile_id,
                    ):
                        summary.duplicadas_ignoradas += 1
                        continue

                    if row.kind == "receita":
                        cat_id, sub_id = self._resolve_or_create_category(
                            cat_repo, KIND_RECEITA, row.categoria, row.subcategoria, profile_id
                        )
                        created_ids = tx_service.create_income(
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
                        )
                    else:
                        cat_id, sub_id = self._resolve_or_create_category(
                            cat_repo, KIND_DESPESA, row.categoria, row.subcategoria, profile_id
                        )
                        created_ids = tx_service.create_expense(
                            descricao=row.descricao,
                            valor=row.valor,
                            data_vencimento=row.data_vencimento,
                            profile_id=profile_id,
                            id_conta=acc_id,
                            data_evento=row.data_lancamento,
                            id_categoria=cat_id,
                            id_subcategoria=sub_id,
                            pago=row.efetivada,
                            data_efetivacao=row.data_efetivacao,
                            obs=row.observacoes,
                        )

                    tx_id = created_ids[0] if created_ids else ""
                    self.duplicate_checker.register_imported(
                        row,
                        tx_id,
                        profile_id=profile_id,
                        source_file="pluggy_open_finance",
                    )
                    summary.transacoes_importadas += 1

                if reconcile_balances:
                    acc_repo.reconcile_account_balance(
                        acc_id, target_mes, target_ano, acc.saldo_atual
                    )

        return summary
