"""
Serviço de Orçamentos Mensais (`orcamentos`, `orcamentos_mensal`, `orcamentos_tags`, `orcamentos_categorias`).

Regras de negócio:
- Suporta orçamentos de Despesas (`tipo = 'D'`) ou Receitas (`tipo = 'R'`).
- Calcula automaticamente os valores Efetivados e Pendentes do mês consultado
  respeitando o Modo de Data de Referência ativo e os rateios multi-categoria (`SplitDTO`).
- Permite sobrescrever a meta de um mês específico em `orcamentos_mensal`.
- Sinaliza estado de alerta quando o percentual utilizado atinge `perc_alerta` (padrão 80%)
  e estado estourado quando ultrapassa 100%.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from app.config.theme_palette import argb_int_to_hex
from app.database.connection_manager import ConnectionManager
from app.domain.models import KIND_DESPESA, KIND_RECEITA, Occurrence
from app.domain.services.transaction_service import TransactionService


@dataclass
class BudgetProgressDTO:
    id: str
    id_profile: str
    id_categoria: Optional[str]
    id_subcategoria: Optional[str]
    id_tag: Optional[str]
    nome_alvo: str
    cor_hex: str
    tipo: str  # 'D' = Despesa, 'R' = Receita
    meta_base: float
    meta_mes: float
    perc_alerta: float
    somar_sub: bool
    exibir_resumo: bool
    efetivado: float
    pendente: float

    @property
    def utilizado(self) -> float:
        return round(self.efetivado + self.pendente, 2)

    @property
    def restante(self) -> float:
        return round(self.meta_mes - self.utilizado, 2)

    @property
    def percentual(self) -> float:
        if self.meta_mes <= 0:
            return 100.0 if self.utilizado > 0 else 0.0
        return round((self.utilizado / self.meta_mes) * 100.0, 1)

    @property
    def status_label(self) -> str:
        pct = self.percentual
        if pct > 100.0:
            return "Estourado"
        if pct >= self.perc_alerta:
            return "Em Alerta"
        return "Dentro da Meta"


class BudgetService:
    """Serviço de domínio para gestão e apuração mensal de orçamentos."""

    def __init__(
        self,
        db: ConnectionManager,
        tx_service: Optional[TransactionService] = None,
    ) -> None:
        self.db = db
        self.tx_service = tx_service or TransactionService(db)

    def create_budget(
        self,
        *,
        meta: float,
        id_categoria: Optional[str] = None,
        id_subcategoria: Optional[str] = None,
        id_tag: Optional[str] = None,
        tipo: str = "D",
        perc_alerta: float = 80.0,
        somar_sub: bool = True,
        exibir_resumo: bool = True,
        profile_id: str = "1",
    ) -> str:
        if meta <= 0:
            raise ValueError("A meta do orçamento deve ser maior que zero.")
        if not id_categoria and not id_tag:
            raise ValueError("Selecione uma categoria ou tag para o orçamento.")

        budget_id = uuid.uuid4().hex[:16]
        now_str = datetime.now().strftime("%Y-%m-%d")
        tipo_code = "R" if str(tipo).upper().startswith("R") else "D"

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO orcamentos (
                    id, id_profile, id_categoria, id_subcategoria, meta, tipo,
                    exibir_resumo, notify_over, data_criacao, somar_sub,
                    perc_alerta, nao_somadas
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'S', ?, ?, ?, 'N')
                """,
                (
                    budget_id,
                    str(profile_id),
                    str(id_categoria) if id_categoria else None,
                    str(id_subcategoria) if id_subcategoria else None,
                    round(float(meta), 2),
                    tipo_code,
                    "S" if exibir_resumo else "N",
                    now_str,
                    "S" if somar_sub else "N",
                    float(perc_alerta),
                ),
            )
            if id_tag:
                cur.execute(
                    "INSERT INTO orcamentos_tags (id_orcamento, id_tag) VALUES (?, ?)",
                    (budget_id, str(id_tag)),
                )
            if id_categoria:
                cur.execute(
                    """
                    INSERT INTO orcamentos_categorias (id_orcamento, id_categoria, id_subcategoria)
                    VALUES (?, ?, ?)
                    """,
                    (
                        budget_id,
                        str(id_categoria),
                        str(id_subcategoria) if id_subcategoria else None,
                    ),
                )
        return budget_id

    def update_budget(
        self,
        budget_id: str,
        *,
        meta: float,
        perc_alerta: float = 80.0,
        exibir_resumo: bool = True,
        year: Optional[int] = None,
        month: Optional[int] = None,
        override_month_only: bool = False,
    ) -> None:
        if meta <= 0:
            raise ValueError("A meta do orçamento deve ser maior que zero.")
        with self.db.transaction() as cur:
            if override_month_only and year and month:
                dt_key = f"{int(year):04d}-{int(month):02d}-01"
                cur.execute(
                    "DELETE FROM orcamentos_mensal WHERE id_orcamento = ? AND substr(data, 1, 7) = ?",
                    (str(budget_id), dt_key[:7]),
                )
                cur.execute(
                    """
                    INSERT INTO orcamentos_mensal (id_orcamento, meta, efet, pend, data)
                    VALUES (?, ?, 0, 0, ?)
                    """,
                    (str(budget_id), round(float(meta), 2), dt_key),
                )
            else:
                cur.execute(
                    """
                    UPDATE orcamentos
                    SET meta = ?, perc_alerta = ?, exibir_resumo = ?
                    WHERE id = ?
                    """,
                    (
                        round(float(meta), 2),
                        float(perc_alerta),
                        "S" if exibir_resumo else "N",
                        str(budget_id),
                    ),
                )

    def delete_budget(self, budget_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "DELETE FROM orcamentos_mensal WHERE id_orcamento = ?",
                (str(budget_id),),
            )
            cur.execute(
                "DELETE FROM orcamentos_tags WHERE id_orcamento = ?",
                (str(budget_id),),
            )
            cur.execute(
                "DELETE FROM orcamentos_categorias WHERE id_orcamento = ?",
                (str(budget_id),),
            )
            cur.execute("DELETE FROM orcamentos WHERE id = ?", (str(budget_id),))

    def list_budgets_progress(
        self,
        year: int,
        month: int,
        profile_id: str = "1",
        mode: Optional[str] = None,
    ) -> List[BudgetProgressDTO]:
        rows = self.db.execute_query(
            """
            SELECT o.id, o.id_profile, o.id_categoria, o.id_subcategoria,
                   COALESCE(o.meta, 0) AS meta, COALESCE(o.tipo, 'D') AS tipo,
                   COALESCE(o.exibir_resumo, 'S') AS exibir_resumo,
                   COALESCE(o.somar_sub, 'S') AS somar_sub,
                   COALESCE(o.perc_alerta, 80) AS perc_alerta,
                   ot.id_tag,
                   dc.nome AS desp_cat_nome, dc.cor AS desp_cat_cor,
                   ds.nome AS desp_sub_nome,
                   rc.descricao AS rec_cat_nome, rc.cor AS rec_cat_cor,
                   rs.nome AS rec_sub_nome,
                   t.nome AS tag_nome, t.cor AS tag_cor
            FROM orcamentos o
            LEFT JOIN orcamentos_tags ot ON ot.id_orcamento = o.id
            LEFT JOIN despesas_cat dc ON dc.id = o.id_categoria
            LEFT JOIN despesas_subcat ds ON ds.id = o.id_subcategoria
            LEFT JOIN receitas_cat rc ON rc.id = o.id_categoria
            LEFT JOIN receitas_subcat rs ON rs.id = o.id_subcategoria
            LEFT JOIN tags t ON t.id = ot.id_tag
            WHERE COALESCE(o.id_profile, '1') = ?
              AND (o.data_exclusao IS NULL OR o.data_exclusao = '')
            ORDER BY o.tipo ASC, COALESCE(dc.nome, rc.descricao, t.nome, '') ASC
            """,
            (str(profile_id),),
        )
        if not rows:
            return []

        ym_prefix = f"{int(year):04d}-{int(month):02d}"
        ov_rows = self.db.execute_query(
            """
            SELECT id_orcamento, meta
            FROM orcamentos_mensal
            WHERE substr(data, 1, 7) = ?
            """,
            (ym_prefix,),
        )
        monthly_overrides = {
            str(r["id_orcamento"]): float(r["meta"] or 0.0) for r in ov_rows
        }

        occs = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            profile_id=profile_id,
            kinds=[KIND_DESPESA, KIND_RECEITA],
        )

        result: List[BudgetProgressDTO] = []
        for r in rows:
            bid = str(r["id"])
            tipo = "R" if str(r["tipo"] or "D").upper().startswith("R") else "D"
            id_cat = str(r["id_categoria"]) if r["id_categoria"] else None
            id_sub = str(r["id_subcategoria"]) if r["id_subcategoria"] else None
            id_tag = str(r["id_tag"]) if r["id_tag"] else None
            somar_sub = str(r["somar_sub"] or "S").upper() == "S"
            meta_base = round(float(r["meta"] or 0.0), 2)
            meta_mes = round(monthly_overrides.get(bid, meta_base), 2)

            if id_tag and r["tag_nome"]:
                nome_alvo = f"Tag #{r['tag_nome']}"
                cor_hex = argb_int_to_hex(
                    int(r["tag_cor"]) if r["tag_cor"] is not None else -14575885
                )
            elif tipo == "R":
                cat_n = str(r["rec_cat_nome"] or "Receitas")
                sub_n = str(r["rec_sub_nome"] or "")
                nome_alvo = f"{cat_n} ▸ {sub_n}" if (id_sub and sub_n) else cat_n
                cor_hex = argb_int_to_hex(
                    int(r["rec_cat_cor"]) if r["rec_cat_cor"] is not None else -15228834
                )
            else:
                cat_n = str(r["desp_cat_nome"] or "Despesas")
                sub_n = str(r["desp_sub_nome"] or "")
                nome_alvo = f"{cat_n} ▸ {sub_n}" if (id_sub and sub_n) else cat_n
                cor_hex = argb_int_to_hex(
                    int(r["desp_cat_cor"])
                    if r["desp_cat_cor"] is not None
                    else -14575885
                )

            efet, pend = self._compute_budget_usage(
                occs=occs,
                tipo=tipo,
                id_cat=id_cat,
                id_sub=id_sub,
                id_tag=id_tag,
                somar_sub=somar_sub,
            )

            result.append(
                BudgetProgressDTO(
                    id=bid,
                    id_profile=str(r["id_profile"] or "1"),
                    id_categoria=id_cat,
                    id_subcategoria=id_sub,
                    id_tag=id_tag,
                    nome_alvo=nome_alvo,
                    cor_hex=cor_hex,
                    tipo=tipo,
                    meta_base=meta_base,
                    meta_mes=meta_mes,
                    perc_alerta=float(r["perc_alerta"] or 80.0),
                    somar_sub=somar_sub,
                    exibir_resumo=str(r["exibir_resumo"] or "S").upper() == "S",
                    efetivado=efet,
                    pendente=pend,
                )
            )
        return result

    @staticmethod
    def _compute_budget_usage(
        *,
        occs: List[Occurrence],
        tipo: str,
        id_cat: Optional[str],
        id_sub: Optional[str],
        id_tag: Optional[str],
        somar_sub: bool,
    ) -> tuple[float, float]:
        target_kind = KIND_RECEITA if tipo == "R" else KIND_DESPESA
        efet = 0.0
        pend = 0.0

        for o in occs:
            if o.kind != target_kind or not o.contabilizar:
                continue

            if id_tag:
                if not any(tid == id_tag for tid, _, _ in o.tags):
                    continue
                val = o.total
                if o.efetivada:
                    efet += val
                else:
                    pend += val
                continue

            if id_cat:
                if o.kind == KIND_DESPESA and o.splits:
                    for s in o.splits:
                        if s.id_categoria != id_cat:
                            continue
                        if id_sub and s.id_subcategoria != id_sub:
                            continue
                        if not id_sub and not somar_sub and s.id_subcategoria:
                            continue
                        if o.efetivada:
                            efet += s.valor
                        else:
                            pend += s.valor
                else:
                    if str(o.id_categoria or "") != id_cat:
                        continue
                    if id_sub and str(o.id_subcategoria or "") != id_sub:
                        continue
                    if o.efetivada:
                        efet += o.total
                    else:
                        pend += o.total

        return round(efet, 2), round(pend, 2)
