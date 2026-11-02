"""
Serviço Analítico de Relatórios, Gráficos, Calendário Financeiro e Ferramentas Complementares
(Empréstimos `emprestimos` e Notas `notas`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
import unicodedata
from typing import Any, Dict, List, Optional

from app.config.theme_palette import argb_int_to_hex, hex_to_argb_int
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.domain.date_utils import add_months, parse_date
from app.domain.models import (
    ALL_KINDS,
    KIND_DESPESA,
    KIND_RECEITA,
    KIND_TRANSFERENCIA,
    Occurrence,
)
from app.domain.services.transaction_service import TransactionService


@dataclass
class CategoryBreakdownRow:
    id_categoria: str
    categoria_nome: str
    subcategoria_nome: str
    cor_hex: str
    efetivado: float
    pendente: float
    total: float
    percentual: float
    quantidade: int


@dataclass
class CategoryHealthMetric:
    categoria_nome: str
    total: float
    percentual_despesas: float
    media_anterior_2m: float
    variacao_percentual: float  # Ex.: +35.2% ou -10.0%
    tipo_regra: str  # "ESSENCIAL" | "ESTILO_DE_VIDA"
    cor_hex: str = "#5C6BC0"


@dataclass
class FinancialHealthData:
    ano: int
    mes: int
    total_receitas: float
    total_despesas: float
    resultado_liquido: float
    saldo_contas: float
    saldo_investimentos: float
    despesas_essenciais: float
    despesas_estilo_vida: float
    percentual_essenciais: float
    percentual_estilo_vida: float
    percentual_poupanca: float
    categorias: List[CategoryHealthMetric] = field(default_factory=list)
    historico_recente: List[Dict[str, Any]] = field(default_factory=list)

    def to_ai_payload(self) -> Dict[str, Any]:
        """Gera payload 100% anonimizado e estruturado para prompt da IA."""
        return {
            "periodo": f"{self.mes:02d}/{self.ano}",
            "totais": {
                "receitas": self.total_receitas,
                "despesas": self.total_despesas,
                "resultado_liquido": self.resultado_liquido,
                "saldo_patrimonial": self.saldo_contas,
                "saldo_investimentos_reserva": self.saldo_investimentos,
            },
            "regra_50_30_20_calculada": {
                "essenciais": {
                    "total": self.despesas_essenciais,
                    "percentual_real": self.percentual_essenciais,
                    "meta_percentual": 50.0,
                },
                "estilo_de_vida": {
                    "total": self.despesas_estilo_vida,
                    "percentual_real": self.percentual_estilo_vida,
                    "meta_percentual": 30.0,
                },
                "poupanca_investimentos": {
                    "total": max(0.0, self.resultado_liquido),
                    "percentual_real": self.percentual_poupanca,
                    "meta_percentual": 20.0,
                },
            },
            "detalhamento_categorias": [
                {
                    "categoria": c.categoria_nome,
                    "total": c.total,
                    "participacao_despesas_pct": c.percentual_despesas,
                    "media_2m_anteriores": c.media_anterior_2m,
                    "variacao_vs_media_pct": c.variacao_percentual,
                    "classificacao": c.tipo_regra,
                }
                for c in self.categorias
            ],
            "historico_2_meses_anteriores": self.historico_recente,
        }


@dataclass
class MonthlyFlowPoint:
    ano: int
    mes: int
    label: str
    receitas: float
    despesas: float
    resultado: float
    saldo_contas: float


@dataclass
class DayCalendarSummary:
    dia: date
    receitas: float = 0.0
    despesas: float = 0.0
    transferencias: float = 0.0
    occurrences: List[Occurrence] = field(default_factory=list)

    @property
    def saldo_dia(self) -> float:
        return round(self.receitas - self.despesas, 2)


@dataclass
class LoanDTO:
    id: str
    id_profile: str
    descricao: str
    pessoa: str
    concedido: bool  # True = Emprestei (a receber), False = Tomei emprestado (a pagar)
    principal: float
    amortizado: float
    data_inicio: date
    id_conta: Optional[str]
    arquivado: bool
    observacao: str = ""

    @property
    def saldo_aberto(self) -> float:
        return max(0.0, round(self.principal - self.amortizado, 2))


@dataclass
class NoteDTO:
    id: str
    id_profile: str
    titulo: str
    conteudo: str
    color_hex: str
    arquivada: bool
    atualizado_em: str


class AnalyticsService:
    """Motor analítico central para Dashboard, Relatórios, Gráficos, Calendário e Ferramentas."""

    def __init__(
        self,
        db: ConnectionManager,
        tx_service: Optional[TransactionService] = None,
    ) -> None:
        self.db = db
        self.tx_service = tx_service or TransactionService(db)
        self.account_repo = AccountRepository(db)

    # ------------------------------------------------------------------ #
    # 1. Agrupamentos por Categoria / Subcategoria (com Rateio)
    # ------------------------------------------------------------------ #
    def category_breakdown(
        self,
        year: int,
        month: int,
        *,
        kind: str = KIND_DESPESA,
        profile_id: str = "1",
        mode: Optional[str] = None,
        group_by_subcategory: bool = False,
    ) -> List[CategoryBreakdownRow]:
        occs = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            profile_id=profile_id,
            kinds=[kind],
        )
        buckets: Dict[str, CategoryBreakdownRow] = {}
        grand_total = 0.0
        has_card_items = any(o.is_card for o in occs)

        for o in occs:
            if not o.contabilizar:
                continue
            if has_card_items and not o.is_card and "[Pagamento Fatura:" in (o.obs or ""):
                continue
            if kind == KIND_DESPESA and len(o.splits) > 1:
                for s in o.splits:
                    key = (
                        f"{s.id_categoria}:{s.id_subcategoria}"
                        if group_by_subcategory
                        else s.id_categoria
                    )
                    val = round(float(s.valor), 2)
                    grand_total += val
                    row = buckets.get(key)
                    if row is None:
                        row = CategoryBreakdownRow(
                            id_categoria=s.id_categoria,
                            categoria_nome=s.categoria_nome or "Outros",
                            subcategoria_nome=(
                                s.subcategoria_nome if group_by_subcategory else ""
                            ),
                            cor_hex=s.categoria_cor or "#5C6BC0",
                            efetivado=0.0,
                            pendente=0.0,
                            total=0.0,
                            percentual=0.0,
                            quantidade=0,
                        )
                        buckets[key] = row
                    if o.efetivada:
                        row.efetivado = round(row.efetivado + val, 2)
                    else:
                        row.pendente = round(row.pendente + val, 2)
                    row.total = round(row.efetivado + row.pendente, 2)
                    row.quantidade += 1
            else:
                cid = str(o.id_categoria or "outros")
                sid = str(o.id_subcategoria or "")
                key = f"{cid}:{sid}" if group_by_subcategory else cid
                val = o.total
                grand_total += val
                row = buckets.get(key)
                if row is None:
                    row = CategoryBreakdownRow(
                        id_categoria=cid,
                        categoria_nome=o.categoria_nome or "Outros",
                        subcategoria_nome=(
                            o.subcategoria_nome if group_by_subcategory else ""
                        ),
                        cor_hex=o.categoria_cor or "#5C6BC0",
                        efetivado=0.0,
                        pendente=0.0,
                        total=0.0,
                        percentual=0.0,
                        quantidade=0,
                    )
                    buckets[key] = row
                if o.efetivada:
                    row.efetivado = round(row.efetivado + val, 2)
                else:
                    row.pendente = round(row.pendente + val, 2)
                row.total = round(row.efetivado + row.pendente, 2)
                row.quantidade += 1

        rows = sorted(buckets.values(), key=lambda r: abs(r.total), reverse=True)
        for r in rows:
            r.percentual = (
                round((abs(r.total) / abs(grand_total)) * 100.0, 1)
                if abs(grand_total) > 0.001
                else 0.0
            )
        return rows

    # ------------------------------------------------------------------ #
    # 2. Agrupamentos por Tag e por Conta / Cartão
    # ------------------------------------------------------------------ #
    def tag_breakdown(
        self,
        year: int,
        month: int,
        *,
        profile_id: str = "1",
        mode: Optional[str] = None,
    ) -> List[CategoryBreakdownRow]:
        occs = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            profile_id=profile_id,
            kinds=[KIND_DESPESA, KIND_RECEITA],
        )
        buckets: Dict[str, CategoryBreakdownRow] = {}
        total_abs = 0.0
        for o in occs:
            if not o.tags:
                continue
            for tid, tname, tcolor in o.tags:
                val = o.total
                total_abs += abs(val)
                row = buckets.get(tid)
                if row is None:
                    row = CategoryBreakdownRow(
                        id_categoria=tid,
                        categoria_nome=f"#{tname}",
                        subcategoria_nome=o.kind,
                        cor_hex=tcolor,
                        efetivado=0.0,
                        pendente=0.0,
                        total=0.0,
                        percentual=0.0,
                        quantidade=0,
                    )
                    buckets[tid] = row
                if o.efetivada:
                    row.efetivado = round(row.efetivado + val, 2)
                else:
                    row.pendente = round(row.pendente + val, 2)
                row.total = round(row.efetivado + row.pendente, 2)
                row.quantidade += 1

        rows = sorted(buckets.values(), key=lambda r: abs(r.total), reverse=True)
        for r in rows:
            r.percentual = (
                round((abs(r.total) / total_abs) * 100.0, 1)
                if total_abs > 0.001
                else 0.0
            )
        return rows

    def source_breakdown(
        self,
        year: int,
        month: int,
        *,
        profile_id: str = "1",
        mode: Optional[str] = None,
    ) -> List[CategoryBreakdownRow]:
        occs = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            profile_id=profile_id,
            kinds=[KIND_DESPESA, KIND_RECEITA],
        )
        buckets: Dict[str, CategoryBreakdownRow] = {}
        total_abs = 0.0
        for o in occs:
            if o.is_card:
                key = f"CARD:{o.id_cartao}"
                name = f"💳 {o.cartao_nome or 'Cartão'}"
                sub = "Cartão de Crédito"
                cor = "#EF5350"
            else:
                key = f"ACC:{o.id_conta}"
                name = f"🏦 {o.conta_nome or 'Conta'}"
                sub = "Conta Bancária"
                cor = "#2196F3"
            val = o.total
            total_abs += abs(val)
            row = buckets.get(key)
            if row is None:
                row = CategoryBreakdownRow(
                    id_categoria=key,
                    categoria_nome=name,
                    subcategoria_nome=sub,
                    cor_hex=cor,
                    efetivado=0.0,
                    pendente=0.0,
                    total=0.0,
                    percentual=0.0,
                    quantidade=0,
                )
                buckets[key] = row
            if o.efetivada:
                row.efetivado = round(row.efetivado + val, 2)
            else:
                row.pendente = round(row.pendente + val, 2)
            row.total = round(row.efetivado + row.pendente, 2)
            row.quantidade += 1

        rows = sorted(buckets.values(), key=lambda r: abs(r.total), reverse=True)
        for r in rows:
            r.percentual = (
                round((abs(r.total) / total_abs) * 100.0, 1)
                if total_abs > 0.001
                else 0.0
            )
        return rows

    # ------------------------------------------------------------------ #
    # 3. Fluxo de Caixa e Evolução Mensal
    # ------------------------------------------------------------------ #
    def monthly_evolution(
        self,
        end_year: int,
        end_month: int,
        *,
        months_count: int = 6,
        profile_id: str = "1",
        mode: Optional[str] = None,
    ) -> List[MonthlyFlowPoint]:
        anchor = date(int(end_year), int(end_month), 1)
        points: List[MonthlyFlowPoint] = []
        for offset in range(-(max(1, months_count) - 1), 1):
            dt = add_months(anchor, offset)
            y, m = dt.year, dt.month
            occs = self.tx_service.list_occurrences(
                y,
                m,
                mode=mode,
                profile_id=profile_id,
                kinds=[KIND_RECEITA, KIND_DESPESA],
                light=True,
            )
            summ = self.tx_service.summarize(occs)
            acc_totals = self.account_repo.get_consolidated_totals(
                profile_id=profile_id, mes=m, ano=y
            )
            points.append(
                MonthlyFlowPoint(
                    ano=y,
                    mes=m,
                    label=f"{m:02d}/{y}",
                    receitas=summ["receitas"],
                    despesas=summ["despesas"],
                    resultado=summ["resultado"],
                    saldo_contas=acc_totals["saldo_previsto"],
                )
            )
        return points

    # ------------------------------------------------------------------ #
    # 4. Calendário Financeiro Diário
    # ------------------------------------------------------------------ #
    def daily_calendar_summary(
        self,
        year: int,
        month: int,
        *,
        profile_id: str = "1",
        mode: Optional[str] = None,
    ) -> Dict[int, DayCalendarSummary]:
        occs = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            profile_id=profile_id,
            kinds=ALL_KINDS,
        )
        by_day: Dict[int, DayCalendarSummary] = {}
        for o in occs:
            d = o.ref_date.day
            summary = by_day.get(d)
            if summary is None:
                summary = DayCalendarSummary(dia=o.ref_date)
                by_day[d] = summary
            if o.kind == KIND_RECEITA:
                summary.receitas = round(summary.receitas + o.total, 2)
            elif o.kind == KIND_DESPESA:
                summary.despesas = round(summary.despesas + o.total, 2)
            else:
                summary.transferencias = round(summary.transferencias + o.total, 2)
            summary.occurrences.append(o)
        return by_day

    def third_party_breakdown(
        self,
        year: int,
        month: int,
        *,
        profile_id: str = "1",
        mode: Optional[str] = None,
    ) -> List[CategoryBreakdownRow]:
        """Agrupa as compras/despesas em nome de terceiros (`not o.contabilizar`) no mês."""
        occs = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            profile_id=profile_id,
            kinds=[KIND_DESPESA],
        )
        buckets: Dict[str, CategoryBreakdownRow] = {}
        grand_total = 0.0
        for o in occs:
            if o.contabilizar:
                continue
            pessoa_label = "Terceiro / Familiar"
            if "[terceiro:" in (o.obs or "").lower():
                raw_obs = o.obs
                start_i = raw_obs.lower().find("[terceiro:") + len("[terceiro:")
                end_i = raw_obs.find("]", start_i)
                if end_i > start_i:
                    pessoa_label = raw_obs[start_i:end_i].strip() or pessoa_label
            key = f"TERC:{pessoa_label}:{o.descricao}"
            val = o.total
            grand_total += val
            row = buckets.get(key)
            if row is None:
                row = CategoryBreakdownRow(
                    id_categoria=key,
                    categoria_nome=f"👤 {pessoa_label} — {o.descricao}",
                    subcategoria_nome=o.cartao_nome or o.conta_nome or "Cartão",
                    cor_hex="#C27D38",
                    efetivado=0.0,
                    pendente=0.0,
                    total=0.0,
                    percentual=0.0,
                    quantidade=0,
                )
                buckets[key] = row
            if o.efetivada:
                row.efetivado = round(row.efetivado + val, 2)
            else:
                row.pendente = round(row.pendente + val, 2)
            row.total = round(row.efetivado + row.pendente, 2)
            row.quantidade += 1

        rows = sorted(buckets.values(), key=lambda r: abs(r.total), reverse=True)
        for r in rows:
            r.percentual = (
                round((abs(r.total) / abs(grand_total)) * 100.0, 1)
                if abs(grand_total) > 0.001
                else 0.0
            )
        return rows

    # ------------------------------------------------------------------ #
    # 5. Empréstimos (`emprestimos` e `emprestimos_vinculos`)
    # ------------------------------------------------------------------ #
    def create_loan(
        self,
        *,
        descricao: str,
        pessoa: str,
        principal: float,
        concedido: bool = True,
        data_inicio: Optional[date] = None,
        id_conta: Optional[str] = None,
        movimentar_conta: bool = False,
        observacao: str = "",
        profile_id: str = "1",
    ) -> LoanDTO:
        if not descricao.strip():
            raise ValueError("Informe a descrição do empréstimo.")
        if principal <= 0:
            raise ValueError("O valor principal deve ser maior que zero.")
        lid = uuid.uuid4().hex[:16]
        dt_obj = data_inicio or date.today()
        dt_str = dt_obj.isoformat()
        eff_conta = str(id_conta or "")
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO emprestimos (
                    id, id_profile, descricao, pessoa, concedido, moeda,
                    id_conta, data, principal, saldo_historico, arquivado, observacao
                ) VALUES (?, ?, ?, ?, ?, 'BRL', ?, ?, ?, 0, 'N', ?)
                """,
                (
                    lid,
                    str(profile_id),
                    descricao.strip(),
                    pessoa.strip() or "Terceiro",
                    "S" if concedido else "N",
                    eff_conta,
                    dt_str,
                    round(float(principal), 2),
                    observacao.strip(),
                ),
            )
        if movimentar_conta and eff_conta:
            if concedido:
                self.tx_service.create_expense(
                    descricao=f"Concessão Empréstimo: {descricao.strip()} ({pessoa.strip() or 'Terceiro'})",
                    valor=round(float(principal), 2),
                    data_vencimento=dt_obj,
                    id_conta=eff_conta,
                    profile_id=str(profile_id),
                    pago=True,
                    contabilizar=False,
                    obs="Saída de caixa referente a empréstimo concedido",
                )
            else:
                self.tx_service.create_income(
                    descricao=f"Entrada Empréstimo: {descricao.strip()} ({pessoa.strip() or 'Terceiro'})",
                    valor=round(float(principal), 2),
                    data=dt_obj,
                    id_conta=eff_conta,
                    profile_id=str(profile_id),
                    recebido=True,
                    contabilizar=False,
                    obs="Entrada de caixa referente a empréstimo tomado",
                )
        loans = [x for x in self.list_loans(profile_id) if x.id == lid]
        return loans[0]

    def register_loan_payment(
        self,
        loan_id: str,
        valor: float,
        data_pag: Optional[date] = None,
        profile_id: str = "1",
        *,
        data_pagamento: Optional[date] = None,
        id_conta: Optional[str] = None,
        movimentar_conta: bool = False,
        obs: str = "",
    ) -> str:
        if valor <= 0:
            raise ValueError("O valor amortizado deve ser maior que zero.")
        vid = uuid.uuid4().hex[:16]
        dt_obj = data_pag or data_pagamento or date.today()
        dt_str = dt_obj.isoformat()

        loan_row = self.db.fetch_one(
            "SELECT descricao, pessoa, COALESCE(concedido, 'S') AS concedido FROM emprestimos WHERE id = ?",
            (str(loan_id),),
        )
        is_concedido = True
        desc_loan = "Empréstimo"
        pessoa_loan = "Terceiro"
        if loan_row is not None:
            is_concedido = str(loan_row["concedido"] or "S").upper() == "S"
            desc_loan = str(loan_row["descricao"] or "Empréstimo")
            pessoa_loan = str(loan_row["pessoa"] or "Terceiro")

        tx_id = vid
        tx_kind_code = "AMORTIZACAO"
        if movimentar_conta and id_conta:
            if is_concedido:
                created_ids = self.tx_service.create_income(
                    descricao=f"Recebimento Empréstimo: {desc_loan} ({pessoa_loan})",
                    valor=round(float(valor), 2),
                    data=dt_obj,
                    id_conta=str(id_conta),
                    profile_id=str(profile_id),
                    recebido=True,
                    data_efetivacao=dt_obj,
                    contabilizar=False,
                    obs=obs or f"Amortização recebida de {pessoa_loan}",
                )
                if created_ids:
                    tx_id = created_ids[0]
                    tx_kind_code = "RECEITA"
            else:
                created_ids = self.tx_service.create_expense(
                    descricao=f"Pagamento Empréstimo: {desc_loan} ({pessoa_loan})",
                    valor=round(float(valor), 2),
                    data_vencimento=dt_obj,
                    id_conta=str(id_conta),
                    profile_id=str(profile_id),
                    pago=True,
                    data_efetivacao=dt_obj,
                    contabilizar=False,
                    obs=obs or f"Amortização paga a {pessoa_loan}",
                )
                if created_ids:
                    tx_id = created_ids[0]
                    tx_kind_code = "DESPESA"

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO emprestimos_vinculos (
                    id, id_profile, id_emprestimo, id_transacao,
                    tipo_transacao, papel, valor, data
                ) VALUES (?, ?, ?, ?, ?, 'PAGAMENTO', ?, ?)
                """,
                (
                    vid,
                    str(profile_id),
                    str(loan_id),
                    str(tx_id),
                    tx_kind_code,
                    round(float(valor), 2),
                    dt_str,
                ),
            )
        return vid

    def delete_loan(self, loan_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "DELETE FROM emprestimos_vinculos WHERE id_emprestimo = ?",
                (str(loan_id),),
            )
            cur.execute("DELETE FROM emprestimos WHERE id = ?", (str(loan_id),))

    def list_loans(self, profile_id: str = "1") -> List[LoanDTO]:
        rows = self.db.execute_query(
            """
            SELECT e.id, e.id_profile, e.descricao, COALESCE(e.pessoa, '') AS pessoa,
                   COALESCE(e.concedido, 'S') AS concedido,
                   COALESCE(e.principal, 0) AS principal,
                   e.data, e.id_conta,
                   COALESCE(e.arquivado, 'N') AS arquivado,
                   COALESCE(e.observacao, '') AS observacao,
                   COALESCE((
                       SELECT SUM(COALESCE(v.valor, 0))
                       FROM emprestimos_vinculos v
                       WHERE v.id_emprestimo = e.id
                         AND COALESCE(v.papel, 'PAGAMENTO') = 'PAGAMENTO'
                   ), 0) AS amortizado
            FROM emprestimos e
            WHERE COALESCE(e.id_profile, '1') = ?
            ORDER BY date(COALESCE(e.data, '2000-01-01')) DESC
            """,
            (str(profile_id),),
        )
        return [
            LoanDTO(
                id=str(r["id"]),
                id_profile=str(r["id_profile"] or "1"),
                descricao=str(r["descricao"] or ""),
                pessoa=str(r["pessoa"] or ""),
                concedido=str(r["concedido"] or "S").upper() == "S",
                principal=round(float(r["principal"] or 0.0), 2),
                amortizado=round(float(r["amortizado"] or 0.0), 2),
                data_inicio=parse_date(r["data"]) or date.today(),
                id_conta=str(r["id_conta"]) if r["id_conta"] else None,
                arquivado=str(r["arquivado"] or "N").upper() == "S",
                observacao=str(r["observacao"] or ""),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # 6. Notas Financeiras (`notas`)
    # ------------------------------------------------------------------ #
    def create_note(
        self,
        *,
        titulo: str,
        conteudo: str,
        color_hex: str = "#2196F3",
        profile_id: str = "1",
    ) -> NoteDTO:
        if not titulo.strip():
            raise ValueError("Informe o título da nota.")
        nid = uuid.uuid4().hex[:16]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color_int = hex_to_argb_int(color_hex)
        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO notas (
                    id, id_profile, titulo, conteudo, cor, arquivada,
                    criado_em, atualizado_em
                ) VALUES (?, ?, ?, ?, ?, 'N', ?, ?)
                """,
                (
                    nid,
                    str(profile_id),
                    titulo.strip(),
                    conteudo.strip(),
                    color_int,
                    now_str,
                    now_str,
                ),
            )
        notes = [n for n in self.list_notes(profile_id) if n.id == nid]
        return notes[0]

    def delete_note(self, note_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM notas WHERE id = ?", (str(note_id),))

    def list_notes(self, profile_id: str = "1") -> List[NoteDTO]:
        rows = self.db.execute_query(
            """
            SELECT id, id_profile, COALESCE(titulo, '') AS titulo,
                   COALESCE(conteudo, '') AS conteudo,
                   COALESCE(cor, -14575885) AS cor,
                   COALESCE(arquivada, 'N') AS arquivada,
                   COALESCE(atualizado_em, criado_em, '') AS atualizado_em
            FROM notas
            WHERE COALESCE(id_profile, '1') = ?
            ORDER BY atualizado_em DESC, id DESC
            """,
            (str(profile_id),),
        )
        return [
            NoteDTO(
                id=str(r["id"]),
                id_profile=str(r["id_profile"] or "1"),
                titulo=str(r["titulo"] or ""),
                conteudo=str(r["conteudo"] or ""),
                color_hex=argb_int_to_hex(int(r["cor"] or -14575885)),
                arquivada=str(r["arquivada"] or "N").upper() == "S",
                atualizado_em=str(r["atualizado_em"] or ""),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ #
    # 7. Diagnóstico e Inteligência de Saúde Financeira
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_essential_category(cat_name: str) -> bool:
        """Determina se uma categoria enquadra-se como Gasto Essencial (Regra 50-30-20)."""
        raw = unicodedata.normalize("NFKD", (cat_name or "").lower())
        norm = "".join([c for c in raw if not unicodedata.combining(c)])
        essential_keywords = (
            "moradia", "aluguel", "condominio", "energia", "luz", "agua", "gas",
            "internet", "alimentacao", "mercado", "supermercado", "feira", "saude",
            "farmacia", "medico", "hospital", "plano de saude", "educacao", "escola",
            "faculdade", "curso", "transporte", "combustivel", "gasolina", "onibus",
            "metro", "seguro", "imposto", "iptu", "ipva", "telefone"
        )
        return any(k in norm for k in essential_keywords)

    def get_financial_health_summary(
        self,
        year: int,
        month: int,
        *,
        profile_id: str = "1",
    ) -> FinancialHealthData:
        """
        Gera métricas financeiras consolidadas do mês ativo e calcula desvios
        em relação à média dos últimos 2 meses anteriores para enriquecer o diagnóstico da IA.
        """
        # 1. Totais do mês ativo
        curr_occs = self.tx_service.list_occurrences(
            year,
            month,
            profile_id=profile_id,
            kinds=[KIND_RECEITA, KIND_DESPESA],
            light=True,
        )
        curr_summ = self.tx_service.summarize(curr_occs)
        tot_receitas = round(float(curr_summ["receitas"]), 2)
        tot_despesas = round(float(curr_summ["despesas"]), 2)
        resultado = round(tot_receitas - tot_despesas, 2)

        # Saldos consolidados de contas e investimentos
        acc_totals = self.account_repo.get_consolidated_totals(
            profile_id=profile_id, mes=month, ano=year
        )
        saldo_contas = round(float(acc_totals.get("saldo_previsto", 0.0)), 2)
        saldo_investimentos = round(float(acc_totals.get("investimentos", 0.0)), 2)

        # 2. Despesas por categoria do mês atual
        curr_cats = self.category_breakdown(
            year,
            month,
            kind=KIND_DESPESA,
            profile_id=profile_id,
            group_by_subcategory=False,
        )

        # 3. Histórico dos 2 meses anteriores para detecção de anomalias
        anchor = date(int(year), int(month), 1)
        prev1_dt = add_months(anchor, -1)
        prev2_dt = add_months(anchor, -2)

        prev1_cats = {
            c.categoria_nome: c.total
            for c in self.category_breakdown(
                prev1_dt.year,
                prev1_dt.month,
                kind=KIND_DESPESA,
                profile_id=profile_id,
                group_by_subcategory=False,
            )
        }
        prev2_cats = {
            c.categoria_nome: c.total
            for c in self.category_breakdown(
                prev2_dt.year,
                prev2_dt.month,
                kind=KIND_DESPESA,
                profile_id=profile_id,
                group_by_subcategory=False,
            )
        }

        # Totais dos 2 meses anteriores para histórico recente
        historico: List[Dict[str, Any]] = []
        for p_dt in (prev2_dt, prev1_dt):
            p_occs = self.tx_service.list_occurrences(
                p_dt.year,
                p_dt.month,
                profile_id=profile_id,
                kinds=[KIND_RECEITA, KIND_DESPESA],
                light=True,
            )
            p_summ = self.tx_service.summarize(p_occs)
            historico.append({
                "periodo": f"{p_dt.month:02d}/{p_dt.year}",
                "receitas": round(float(p_summ["receitas"]), 2),
                "despesas": round(float(p_summ["despesas"]), 2),
                "resultado": round(float(p_summ["resultado"]), 2),
            })

        # 4. Detalhamento e classificação (Essencial vs Estilo de Vida)
        cat_metrics: List[CategoryHealthMetric] = []
        tot_essenciais = 0.0
        tot_estilo_vida = 0.0

        for c in curr_cats:
            val = round(float(c.total), 2)
            c_name = c.categoria_nome
            is_ess = self._is_essential_category(c_name)
            tipo_regra = "ESSENCIAL" if is_ess else "ESTILO_DE_VIDA"

            if is_ess:
                tot_essenciais += val
            else:
                tot_estilo_vida += val

            # Média dos últimos 2 meses
            p1_val = prev1_cats.get(c_name, 0.0)
            p2_val = prev2_cats.get(c_name, 0.0)
            media_2m = round((p1_val + p2_val) / 2.0, 2)

            if media_2m > 0:
                var_pct = round(((val - media_2m) / media_2m) * 100.0, 1)
            else:
                var_pct = 0.0

            pct_despesas = round((val / tot_despesas) * 100.0, 1) if tot_despesas > 0 else 0.0

            cat_metrics.append(
                CategoryHealthMetric(
                    categoria_nome=c_name,
                    total=val,
                    percentual_despesas=pct_despesas,
                    media_anterior_2m=media_2m,
                    variacao_percentual=var_pct,
                    tipo_regra=tipo_regra,
                    cor_hex=c.cor_hex or "#5C6BC0",
                )
            )

        tot_essenciais = round(tot_essenciais, 2)
        tot_estilo_vida = round(tot_estilo_vida, 2)

        # 5. Cálculo dos percentuais da Regra 50-30-20
        base_calc = tot_receitas if tot_receitas > 0 else tot_despesas
        if base_calc > 0:
            pct_ess = round((tot_essenciais / base_calc) * 100.0, 1)
            pct_est = round((tot_estilo_vida / base_calc) * 100.0, 1)
            pct_pou = round(max(0.0, (tot_receitas - tot_despesas) / base_calc) * 100.0, 1) if tot_receitas > 0 else 0.0
        else:
            pct_ess, pct_est, pct_pou = 0.0, 0.0, 0.0

        return FinancialHealthData(
            ano=year,
            mes=month,
            total_receitas=tot_receitas,
            total_despesas=tot_despesas,
            resultado_liquido=resultado,
            saldo_contas=saldo_contas,
            saldo_investimentos=saldo_investimentos,
            despesas_essenciais=tot_essenciais,
            despesas_estilo_vida=tot_estilo_vida,
            percentual_essenciais=pct_ess,
            percentual_estilo_vida=pct_est,
            percentual_poupanca=pct_pou,
            categorias=cat_metrics,
            historico_recente=historico,
        )
