"""Catálogo local e persistência do Lançamento Rápido por IA.

Liga os rascunhos da IA (`TransactionDraft`) aos IDs reais do SQLite e grava via
`TransactionService`. Camada de serviço: sem dependência de Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA
from app.domain.services.ai_service import AIContext, TransactionDraft
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService

IdName = Tuple[str, str]


@dataclass
class ResolvedEntry:
    """Lançamento já associado a IDs reais, pronto para ser editado/gravado."""

    tipo: str
    descricao: str
    valor: float
    data: date
    id_conta: Optional[str] = None
    id_cartao: Optional[str] = None
    id_categoria: Optional[str] = None
    efetivada: bool = True
    id_conta_destino: Optional[str] = None
    campos_fallback: Set[str] = field(default_factory=set)


@dataclass
class QuickEntryCatalog:
    contas: List[IdName] = field(default_factory=list)
    cartoes: List[IdName] = field(default_factory=list)
    cat_despesa: List[IdName] = field(default_factory=list)
    cat_receita: List[IdName] = field(default_factory=list)
    default_conta_id: Optional[str] = None

    def to_context(self) -> AIContext:
        return AIContext(
            contas=[n for _, n in self.contas],
            cartoes=[n for _, n in self.cartoes],
            categorias_despesa=[n for _, n in self.cat_despesa],
            categorias_receita=[n for _, n in self.cat_receita],
        )

    @staticmethod
    def _id_by_name(items: List[IdName], name: Optional[str]) -> Optional[str]:
        return next((i for i, n in items if name and n == name), None)

    def resolve(self, draft: TransactionDraft) -> ResolvedEntry:
        is_income = draft.tipo == KIND_RECEITA
        is_transfer = draft.tipo == KIND_TRANSFERENCIA
        id_cartao = None if (is_income or is_transfer) else self._id_by_name(self.cartoes, draft.cartao)
        id_conta = None if id_cartao else self._id_by_name(self.contas, draft.conta)
        cats = self.cat_receita if is_income else self.cat_despesa
        resolved_cat = None if is_transfer else self._id_by_name(cats, draft.categoria)

        fallback: Set[str] = set()
        if not id_cartao and not id_conta:
            fallback.add("conta")
            id_conta = self.default_conta_id
        if not resolved_cat and not is_transfer:
            fallback.add("categoria")

        return ResolvedEntry(
            tipo=draft.tipo,
            descricao=draft.descricao,
            valor=draft.valor,
            data=draft.data,
            id_conta=id_conta,
            id_cartao=id_cartao,
            id_categoria=resolved_cat,
            efetivada=draft.efetivada,
            campos_fallback=fallback,
        )


def load_catalog(db: ConnectionManager, tx: TransactionService, profile_id: str) -> QuickEntryCatalog:
    accounts = AccountRepository(db).list_accounts(profile_id)
    cats = CategoryRepository(db)
    default = next((a.id for a in accounts if a.padrao == "S"), accounts[0].id if accounts else None)
    return QuickEntryCatalog(
        contas=[(a.id, a.name) for a in accounts],
        cartoes=[(c.id, c.nome) for c in CreditCardService(db, tx).list_cards(profile_id)],
        cat_despesa=[(c.id, c.nome) for c in cats.list_expense_categories(profile_id)],
        cat_receita=[(c.id, c.nome) for c in cats.list_income_categories(profile_id)],
        default_conta_id=default,
    )


def persist_entry(tx: TransactionService, entry: ResolvedEntry, profile_id: str) -> None:
    """Grava o lançamento confirmado (despesa em conta/cartão, receita ou transferência)."""
    efetivacao = entry.data if entry.efetivada else None
    if entry.tipo == KIND_TRANSFERENCIA:
        if not entry.id_conta:
            raise ValueError("Selecione a conta de origem para a transferência.")
        if not entry.id_conta_destino or entry.id_conta_destino == entry.id_conta:
            raise ValueError("Selecione uma conta de destino diferente da origem.")
        tx.create_transfer(
            descricao=entry.descricao,
            valor=entry.valor,
            data=entry.data,
            id_conta_origem=entry.id_conta,
            id_conta_destino=entry.id_conta_destino,
            profile_id=profile_id,
            efetivada=entry.efetivada,
        )
        return
    if entry.tipo == KIND_RECEITA:
        if not entry.id_conta:
            raise ValueError("Selecione uma conta para a receita.")
        tx.create_income(
            descricao=entry.descricao,
            valor=entry.valor,
            data=entry.data,
            id_conta=entry.id_conta,
            profile_id=profile_id,
            id_categoria=entry.id_categoria,
            recebido=entry.efetivada,
            data_efetivacao=efetivacao,
        )
        return
    if not entry.id_conta and not entry.id_cartao:
        raise ValueError("Selecione uma conta ou cartão para a despesa.")
    tx.create_expense(
        descricao=entry.descricao,
        valor=entry.valor,
        data_vencimento=entry.data,
        data_evento=entry.data,
        profile_id=profile_id,
        id_conta=entry.id_conta,
        id_cartao=entry.id_cartao,
        id_categoria=entry.id_categoria,
        pago=entry.efetivada and not entry.id_cartao,
        data_efetivacao=efetivacao if not entry.id_cartao else None,
    )
