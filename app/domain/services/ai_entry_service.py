"""Catálogo local e persistência do Lançamento Rápido por IA.

Liga os rascunhos da IA (`TransactionDraft`) aos IDs reais do SQLite e grava via
`TransactionService`. Camada de serviço: sem dependência de Qt.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.domain.models import (
    KIND_DESPESA,
    KIND_RECEITA,
    KIND_TRANSFERENCIA,
    REC_PARCELADA,
    REC_UNICA,
    fixed_code_for,
)
from app.domain.services.ai_service import (
    AIContext,
    AIService,
    AIServiceError,
    BatchCategorizationItem,
    TransactionDraft,
)
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService

if TYPE_CHECKING:
    from app.io_module.contracts import CanonicalTransactionRow

IdName = Tuple[str, str]


def normalize_rule_pattern(text: str) -> str:
    """Normaliza a descrição para chave de regra local (sem acentos, pontuação ou números soltos)."""
    raw = unicodedata.normalize("NFKD", (text or "").strip())
    no_accents = "".join(ch for ch in raw if not unicodedata.combining(ch))
    lowered = no_accents.casefold()
    cleaned = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    cleaned = re.sub(r"\b\d+\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _clean_redundant_amount_suffix(description: str, amount: float) -> str:
    """Remove sufixo numérico redundante no fim da descrição quando igual ao valor inteiro."""
    clean = re.sub(r"\s+", " ", (description or "").strip())
    if not clean or amount <= 0 or abs(amount - round(amount)) > 1e-6:
        return clean
    int_val = int(round(amount))
    match = re.match(r"^(.*?)\s+(\d+)$", clean)
    if match and int(match.group(2)) == int_val and match.group(1).strip():
        return match.group(1).strip()
    return clean


@dataclass
class LearnedRule:
    """Regra local aprendida a partir de lançamentos confirmados pelo usuário."""

    padrao_normalizado: str
    tipo: str
    id_categoria: Optional[str] = None
    id_conta: Optional[str] = None
    id_cartao: Optional[str] = None
    descricao_limpa: Optional[str] = None


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
    num_parcelas: int = 1
    valor_por_parcela: bool = False
    recorrente_mensal: bool = False


@dataclass
class QuickEntryCatalog:
    contas: List[IdName] = field(default_factory=list)
    cartoes: List[IdName] = field(default_factory=list)
    cat_despesa: List[IdName] = field(default_factory=list)
    cat_receita: List[IdName] = field(default_factory=list)
    default_conta_id: Optional[str] = None
    learned_rules: Dict[Tuple[str, str], LearnedRule] = field(default_factory=dict)

    def to_context(self) -> AIContext:
        return AIContext(
            contas=[n for _, n in self.contas],
            cartoes=[n for _, n in self.cartoes],
            categorias_despesa=[n for _, n in self.cat_despesa],
            categorias_receita=[n for _, n in self.cat_receita],
        )

    @staticmethod
    def _id_by_name(items: List[IdName], name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        exact = next((i for i, n in items if n == name), None)
        if exact is not None:
            return exact
        target = name.strip().casefold()
        if not target:
            return None
        return next((i for i, n in items if n and n.strip().casefold() == target), None)

    def _find_learned_rule(self, description: str, tipo: str) -> Optional[LearnedRule]:
        pattern = normalize_rule_pattern(description)
        if not pattern or not self.learned_rules:
            return None
        direct = self.learned_rules.get((pattern, tipo))
        if direct is not None:
            return direct
        tokens = set(pattern.split())
        best_rule: Optional[LearnedRule] = None
        best_len = 0
        for (rule_pat, rule_tipo), rule in self.learned_rules.items():
            if rule_tipo != tipo or len(rule_pat) < 3:
                continue
            if (
                pattern.startswith(rule_pat + " ")
                or rule_pat.startswith(pattern + " ")
                or rule_pat in tokens
            ) and len(rule_pat) > best_len:
                best_rule = rule
                best_len = len(rule_pat)
        return best_rule

    def resolve(self, draft: TransactionDraft) -> ResolvedEntry:
        is_income = draft.tipo == KIND_RECEITA
        is_transfer = draft.tipo == KIND_TRANSFERENCIA
        fallback: Set[str] = set()
        descricao_limpa = _clean_redundant_amount_suffix(draft.descricao, draft.valor)

        if is_transfer:
            id_cartao = None
            id_conta = self._id_by_name(self.contas, draft.conta)
            id_conta_destino = self._id_by_name(self.contas, draft.conta_destino)
            resolved_cat = None
            if not id_conta:
                fallback.add("conta")
                id_conta = self.default_conta_id
            if not id_conta_destino or id_conta_destino == id_conta:
                fallback.add("destination")
                id_conta_destino = next(
                    (aid for aid, _ in self.contas if aid != id_conta), None
                )
            return ResolvedEntry(
                tipo=draft.tipo,
                descricao=descricao_limpa,
                valor=draft.valor,
                data=draft.data,
                id_conta=id_conta,
                id_cartao=None,
                id_categoria=None,
                efetivada=draft.efetivada,
                id_conta_destino=id_conta_destino,
                campos_fallback=fallback,
                num_parcelas=1,
                valor_por_parcela=False,
                recorrente_mensal=False,
            )

        id_cartao = None if is_income else self._id_by_name(self.cartoes, draft.cartao)
        id_conta = None if id_cartao else self._id_by_name(self.contas, draft.conta)
        cats = self.cat_receita if is_income else self.cat_despesa
        resolved_cat = self._id_by_name(cats, draft.categoria)

        rule = self._find_learned_rule(descricao_limpa, draft.tipo)
        if rule is not None:
            valid_cat_ids = {cid for cid, _ in cats}
            valid_acc_ids = {aid for aid, _ in self.contas}
            valid_card_ids = {cid for cid, _ in self.cartoes}
            if rule.id_categoria and rule.id_categoria in valid_cat_ids:
                resolved_cat = rule.id_categoria
            if not id_cartao and not id_conta:
                if not is_income and rule.id_cartao and rule.id_cartao in valid_card_ids:
                    id_cartao = rule.id_cartao
                elif rule.id_conta and rule.id_conta in valid_acc_ids:
                    id_conta = rule.id_conta
            if (
                rule.descricao_limpa
                and normalize_rule_pattern(descricao_limpa) == rule.padrao_normalizado
            ):
                descricao_limpa = rule.descricao_limpa

        if not id_cartao and not id_conta:
            fallback.add("conta")
            id_conta = self.default_conta_id
        if not resolved_cat:
            fallback.add("categoria")

        recorrente_mensal = bool(draft.recorrente_mensal)
        num_parcelas = 1 if recorrente_mensal else max(1, int(draft.num_parcelas or 1))
        valor_por_parcela = bool(draft.valor_por_parcela) if num_parcelas > 1 else False

        return ResolvedEntry(
            tipo=draft.tipo,
            descricao=descricao_limpa,
            valor=draft.valor,
            data=draft.data,
            id_conta=id_conta,
            id_cartao=id_cartao,
            id_categoria=resolved_cat,
            efetivada=False if id_cartao else draft.efetivada,
            campos_fallback=fallback,
            num_parcelas=num_parcelas,
            valor_por_parcela=valor_por_parcela,
            recorrente_mensal=recorrente_mensal,
        )


def load_learned_rules(
    db: ConnectionManager, profile_id: str
) -> Dict[Tuple[str, str], LearnedRule]:
    """Carrega regras de categorização aprendidas no SQLite para o perfil."""
    rules: Dict[Tuple[str, str], LearnedRule] = {}
    try:
        rows = db.execute_query(
            """
            SELECT padrao_normalizado, tipo, id_categoria, id_conta, id_cartao, descricao_limpa
            FROM regras_categorizacao_ia
            WHERE id_profile = ?
            """,
            (str(profile_id),),
        )
    except sqlite3.OperationalError:
        return rules
    for r in rows:
        pat = str(r["padrao_normalizado"] or "").strip()
        tipo = str(r["tipo"] or "").strip()
        if pat and tipo:
            rules[(pat, tipo)] = LearnedRule(
                padrao_normalizado=pat,
                tipo=tipo,
                id_categoria=r["id_categoria"],
                id_conta=r["id_conta"],
                id_cartao=r["id_cartao"],
                descricao_limpa=r["descricao_limpa"],
            )
    return rules


def save_learned_rule(
    db: ConnectionManager,
    profile_id: str,
    entry: ResolvedEntry,
    *,
    pattern_override: Optional[str] = None,
) -> None:
    """Registra ou atualiza a regra local com base no lançamento confirmado pelo usuário."""
    if entry.tipo not in (KIND_DESPESA, KIND_RECEITA):
        return
    pattern = normalize_rule_pattern(pattern_override) if pattern_override else normalize_rule_pattern(entry.descricao)
    if not pattern:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO regras_categorizacao_ia (
                    id, id_profile, padrao_normalizado, tipo,
                    id_categoria, id_conta, id_cartao, descricao_limpa, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id_profile, padrao_normalizado, tipo) DO UPDATE SET
                    id_categoria = COALESCE(excluded.id_categoria, id_categoria),
                    id_conta = COALESCE(excluded.id_conta, id_conta),
                    id_cartao = COALESCE(excluded.id_cartao, id_cartao),
                    descricao_limpa = COALESCE(excluded.descricao_limpa, descricao_limpa),
                    updated_at = excluded.updated_at
                """,
                (
                    uuid.uuid4().hex[:16],
                    str(profile_id),
                    pattern,
                    entry.tipo,
                    entry.id_categoria,
                    entry.id_conta,
                    entry.id_cartao,
                    entry.descricao.strip() or None,
                    now,
                ),
            )
    except sqlite3.OperationalError:
        return


def load_catalog(
    db: ConnectionManager, tx: TransactionService, profile_id: str
) -> QuickEntryCatalog:
    accounts = AccountRepository(db).list_accounts(profile_id)
    cats = CategoryRepository(db)
    default = next((a.id for a in accounts if a.padrao == "S"), accounts[0].id if accounts else None)
    return QuickEntryCatalog(
        contas=[(a.id, a.name) for a in accounts],
        cartoes=[(c.id, c.nome) for c in CreditCardService(db, tx).list_cards(profile_id)],
        cat_despesa=[(c.id, c.nome) for c in cats.list_expense_categories(profile_id)],
        cat_receita=[(c.id, c.nome) for c in cats.list_income_categories(profile_id)],
        default_conta_id=default,
        learned_rules=load_learned_rules(db, profile_id),
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
            data_efetivacao=efetivacao,
        )
        return

    recorrencia = (
        fixed_code_for(entry.tipo)
        if entry.recorrente_mensal
        else (REC_PARCELADA if entry.num_parcelas > 1 else REC_UNICA)
    )
    num_parcelas = 1 if entry.recorrente_mensal else max(1, int(entry.num_parcelas))
    valor_por_parcela = bool(entry.valor_por_parcela) if num_parcelas > 1 else False

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
            recorrencia=recorrencia,
            num_parcelas=num_parcelas,
            valor_por_parcela=valor_por_parcela,
            recebido=entry.efetivada,
            data_efetivacao=efetivacao,
        )
        save_learned_rule(tx.db, profile_id, entry)
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
        recorrencia=recorrencia,
        num_parcelas=num_parcelas,
        valor_por_parcela=valor_por_parcela,
        pago=entry.efetivada and not entry.id_cartao,
        data_efetivacao=efetivacao if not entry.id_cartao else None,
    )
    save_learned_rule(tx.db, profile_id, entry)


_TRANSFER_HINTS = (
    "transf",
    "pix",
    "ted",
    "doc",
    "entre contas",
    "mesma titularidade",
    "aplicacao",
    "resgate",
)


def _has_transfer_hint(text: str) -> bool:
    norm = normalize_rule_pattern(text)
    return any(hint in norm for hint in _TRANSFER_HINTS)


def reconcile_self_transfers_in_rows(rows: List[CanonicalTransactionRow]) -> int:
    """Detecta e unifica pares de transferência entre contas próprias em um lote de linhas."""
    consumed: Set[int] = set()
    reconciled = 0

    for idx_a, row_a in enumerate(rows):
        if idx_a in consumed:
            continue
        kind_a = (row_a.kind or "").strip().lower()
        if kind_a != "despesa" or (row_a.cartao or "").strip():
            continue
        acc_a = (row_a.conta or "").strip()
        if not acc_a:
            continue

        norm_acc_a = normalize_rule_pattern(acc_a)
        for idx_b, row_b in enumerate(rows):
            if idx_b == idx_a or idx_b in consumed:
                continue
            kind_b = (row_b.kind or "").strip().lower()
            if kind_b != "receita" or (row_b.cartao or "").strip():
                continue
            acc_b = (row_b.conta or "").strip()
            if not acc_b or normalize_rule_pattern(acc_b) == norm_acc_a:
                continue
            if abs(float(row_a.valor) - float(row_b.valor)) >= 0.01:
                continue
            if abs((row_a.data_vencimento - row_b.data_vencimento).days) > 1:
                continue
            if not (_has_transfer_hint(row_a.descricao) or _has_transfer_hint(row_b.descricao)):
                continue

            row_a.kind = "transferencia"
            row_a.conta_destino = acc_b
            row_a.categoria = "Outros"
            consumed.add(idx_b)
            reconciled += 1
            break

    if consumed:
        rows[:] = [r for i, r in enumerate(rows) if i not in consumed]
    return reconciled


def enrich_canonical_rows_with_rules_and_ai(
    db: ConnectionManager,
    rows: List[CanonicalTransactionRow],
    profile_id: str = "1",
    *,
    ai_service: Optional[AIService] = None,
    use_ai: bool = False,
) -> Tuple[int, int]:
    """Aplica categorização híbrida (regras locais SQLite + lote único na IA) sobre linhas sem categoria."""
    if not rows:
        return 0, 0

    catalog = load_catalog(db, TransactionService(db), profile_id)
    cat_id_to_name_desp: Dict[str, str] = dict(catalog.cat_despesa)
    cat_id_to_name_rec: Dict[str, str] = dict(catalog.cat_receita)
    cat_name_to_id_desp: Dict[str, str] = {
        name.casefold(): cid for cid, name in catalog.cat_despesa
    }
    cat_name_to_id_rec: Dict[str, str] = {
        name.casefold(): cid for cid, name in catalog.cat_receita
    }

    local_hits = 0
    pending_ai: List[Tuple[CanonicalTransactionRow, str]] = []

    for row in rows:
        kind_low = (row.kind or "").strip().lower()
        if kind_low.startswith("trans"):
            continue
        cat_low = (row.categoria or "").strip().lower()
        if cat_low not in ("", "outros"):
            continue

        tipo = KIND_RECEITA if kind_low == "receita" else KIND_DESPESA
        cat_id_to_name = (
            cat_id_to_name_rec if tipo == KIND_RECEITA else cat_id_to_name_desp
        )
        rule = catalog._find_learned_rule(row.descricao, tipo)
        if rule is not None and rule.id_categoria in cat_id_to_name:
            row.categoria = cat_id_to_name[rule.id_categoria]
            if (
                rule.descricao_limpa
                and normalize_rule_pattern(row.descricao) == rule.padrao_normalizado
            ):
                if not getattr(row, "_raw_descricao", None):
                    setattr(row, "_raw_descricao", row.descricao)
                row.descricao = rule.descricao_limpa
            local_hits += 1
        else:
            pending_ai.append((row, tipo))

    ai_hits = 0
    if use_ai and pending_ai and ai_service is not None and ai_service.is_configured:
        pairs = [(r.descricao, tipo) for r, tipo in pending_ai]
        batch_map: Dict[Tuple[str, str], BatchCategorizationItem] = {}
        try:
            batch_map = ai_service.categorize_descriptions_batch(
                pairs, catalog.to_context()
            )
        except AIServiceError:
            batch_map = {}

        for row, tipo in pending_ai:
            raw_desc = (row.descricao or "").strip()
            item = batch_map.get((raw_desc.casefold(), tipo))
            if item is None:
                continue
            if item.descricao_limpa:
                if not getattr(row, "_raw_descricao", None):
                    setattr(row, "_raw_descricao", row.descricao)
                row.descricao = item.descricao_limpa
            if item.categoria:
                row.categoria = item.categoria
                ai_hits += 1
                cat_map = (
                    cat_name_to_id_rec if tipo == KIND_RECEITA else cat_name_to_id_desp
                )
                cat_id = cat_map.get(item.categoria.casefold())
                if cat_id:
                    learned_entry = ResolvedEntry(
                        tipo=tipo,
                        descricao=row.descricao,
                        valor=row.valor,
                        data=row.data_vencimento,
                        id_categoria=cat_id,
                    )
                    save_learned_rule(
                        db, profile_id, learned_entry, pattern_override=raw_desc
                    )
                    if normalize_rule_pattern(row.descricao) != normalize_rule_pattern(raw_desc):
                        save_learned_rule(db, profile_id, learned_entry)

    return local_hits, ai_hits
