"""
Motor de Transações (Despesas, Receitas e Transferências).

Responsável por:
- Gerar as ocorrências mensais (únicas, parcelas e instâncias de recorrências fixas com
  exceções mensais em `*_fixas`), respeitando os modos de data de referência
  (Vencimento, Lançamento, Lançamento distribuído e Efetivação).
- Gravar transações com parcelamento, recorrência fixa, rateio multi-categoria
  (`despesas_cat_valor`), confirmação/estorno de status e exclusão por escopo.
Todas as escritas usam transações atômicas com COMMIT imediato (ConnectionManager).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.config.theme_palette import argb_int_to_hex
from app.database.connection_manager import ConnectionManager
from app.domain.date_utils import (
    add_interval,
    add_months,
    clamp_day,
    month_bounds,
    parse_date,
    split_amount,
    to_db_date,
)
from app.domain.models import (
    ALL_KINDS,
    FIXED_CODES,
    KIND_DESPESA,
    KIND_RECEITA,
    KIND_TRANSFERENCIA,
    REC_PARCELADA,
    REC_UNICA,
    Occurrence,
    SplitDTO,
    fixed_code_for,
)

MODE_SALDO = "saldo"  # modo interno usado no cálculo de saldos de contas

_TABLES = {
    KIND_DESPESA: "despesas",
    KIND_RECEITA: "receitas",
    KIND_TRANSFERENCIA: "transferencias",
}
_FIXED_TABLES = {
    KIND_DESPESA: ("despesas_fixas", "id_despesa"),
    KIND_RECEITA: ("receitas_fixas", "id_receita"),
    KIND_TRANSFERENCIA: ("transferencias_fixas", "id_transferencia"),
}
_EFFECTIVE_SQL = {
    KIND_DESPESA: "LOWER(COALESCE(d.status, 'pd')) IN ('pg', 'e', 's')",
    KIND_RECEITA: "UPPER(COALESCE(d.efetivado, 'N')) = 'S'",
    KIND_TRANSFERENCIA: "UPPER(COALESCE(d.contabilizada, 'N')) = 'S'",
}


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _chunks(items: Sequence[str], size: int = 800) -> Iterable[Sequence[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _is_effective_value(kind: str, row_value: object) -> bool:
    text = str(row_value or "").strip()
    if kind == KIND_DESPESA:
        return text.lower() in ("pg", "e", "s")
    return text.upper() == "S"


class TransactionService:
    """Serviço de domínio do motor de transações."""

    def __init__(self, db: ConnectionManager) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # LEITURA: geração de ocorrências mensais
    # ------------------------------------------------------------------ #
    def _ref_expr(self, kind: str, mode: str) -> str:
        evt = (
            "COALESCE(NULLIF(d.data_evento, ''), d.data)"
            if kind != KIND_TRANSFERENCIA
            else "d.data"
        )
        if mode == "vencimento":
            return "d.data"
        if mode == "lancamento":
            return evt
        if mode == "lancamento_distribuir":
            if kind == KIND_TRANSFERENCIA:
                return "d.data"
            return (
                "CASE WHEN COALESCE(d.num_parcelas, 1) > 1 AND NULLIF(d.data_evento, '') IS NOT NULL "
                "THEN date(d.data_evento, '+' || (COALESCE(d.num_parcela, 1) - 1) || ' months') "
                f"ELSE {evt} END"
            )
        eff = _EFFECTIVE_SQL[kind]
        base = (
            f"CASE WHEN {eff} AND NULLIF(d.data_efetivacao, '') IS NOT NULL "
            "THEN d.data_efetivacao ELSE d.data END"
        )
        if mode == MODE_SALDO and kind == KIND_DESPESA:
            return (
                "CASE WHEN COALESCE(d.id_cartao_credito, '') NOT IN ('', '-1') "
                f"THEN d.data ELSE {base} END"
            )
        return base

    def _category_sql(self, kind: str) -> Tuple[str, str]:
        if kind == KIND_DESPESA:
            return (
                ", c.nome AS cat_nome, c.cor AS cat_cor, s.nome AS sub_nome",
                "LEFT JOIN despesas_cat c ON c.id = d.id_categoria "
                "LEFT JOIN despesas_subcat s ON s.id = d.id_subcategoria",
            )
        if kind == KIND_RECEITA:
            return (
                ", c.descricao AS cat_nome, c.cor AS cat_cor, s.nome AS sub_nome",
                "LEFT JOIN receitas_cat c ON c.id = d.id_categoria "
                "LEFT JOIN receitas_subcat s ON s.id = d.id_subcategoria",
            )
        return (", NULL AS cat_nome, NULL AS cat_cor, NULL AS sub_nome", "")

    def _build_occurrence(
        self,
        kind: str,
        row,
        *,
        is_fixed: bool,
        year: int,
        month: int,
        valor: float,
        juros: float,
        efetivada: bool,
        venc: date,
        data_evento: Optional[date],
        data_efetivacao: Optional[date],
        ref_date: date,
        id_conta: Optional[str],
        id_conta_destino: Optional[str],
        id_cartao: Optional[str],
    ) -> Occurrence:
        keys = set(row.keys())

        def get(k: str, default=None):
            return row[k] if k in keys else default

        cat_cor = get("cat_cor")
        return Occurrence(
            kind=kind,
            id=str(row["id"]),
            origin_id=str(get("id_origem") or row["id"]),
            id_profile=str(get("id_profile") or "1"),
            descricao=str(get("descricao") or ""),
            valor=round(float(valor or 0.0), 2),
            juros=round(float(juros or 0.0), 2),
            efetivada=bool(efetivada),
            data_vencimento=venc,
            data_evento=data_evento,
            data_efetivacao=data_efetivacao,
            ref_date=ref_date,
            recorrencia=str(get("recorrencia") or REC_UNICA),
            num_parcela=int(get("num_parcela") or 1),
            num_parcelas=int(get("num_parcelas") or 1),
            intervalo=int(get("intervalo") or 30),
            id_conta=id_conta,
            id_conta_destino=id_conta_destino,
            id_cartao=id_cartao,
            id_categoria=get("id_categoria"),
            id_subcategoria=get("id_subcategoria"),
            categoria_nome=str(get("cat_nome") or ""),
            categoria_cor=argb_int_to_hex(int(cat_cor)) if cat_cor is not None else "#5C6BC0",
            subcategoria_nome=str(get("sub_nome") or ""),
            obs=str(get("obs") or ""),
            is_fixed=is_fixed,
            occ_year=year,
            occ_month=month,
            contabilizar=str(
                get("contabilizar")
                if "contabilizar" in keys and get("contabilizar") is not None
                else (get("considerar_estatistica") or "S")
            ).upper()
            != "N",
            id_despesa_estornada=get("id_despesa_estornada"),
        )

    @staticmethod
    def _clean_card(value: object) -> Optional[str]:
        text = str(value or "").strip()
        return None if text in ("", "-1", "None") else text

    def _load_nonfixed(
        self, kind: str, year: int, month: int, mode: str, profile_id: Optional[str]
    ) -> List[Occurrence]:
        start, end = month_bounds(year, month)
        ref = self._ref_expr(kind, mode)
        cat_cols, cat_join = self._category_sql(kind)
        codes = FIXED_CODES[kind]
        ph = ",".join("?" * len(codes))
        sql = (
            f"SELECT d.*, date({ref}) AS ref_dt {cat_cols} "
            f"FROM {_TABLES[kind]} d {cat_join} "
            f"WHERE COALESCE(d.recorrencia, 'U') NOT IN ({ph}) "
            "AND (d.data_exclusao IS NULL OR date(d.data_exclusao) >= date(?)) "
            f"AND date({ref}) BETWEEN date(?) AND date(?)"
        )
        params: list = [*codes, start.isoformat(), start.isoformat(), end.isoformat()]
        if profile_id:
            sql += " AND d.id_profile = ?"
            params.append(str(profile_id))

        result: List[Occurrence] = []
        for r in self.db.execute_query(sql, params):
            keys = set(r.keys())
            venc = parse_date(r["data"]) or start
            ref_date = parse_date(r["ref_dt"]) or venc
            if kind == KIND_DESPESA:
                eff = _is_effective_value(kind, r["status"])
                conta, destino = r["id_conta"], None
                card = self._clean_card(r["id_cartao_credito"])
                juros = float(r["juros"] or 0.0)
            elif kind == KIND_RECEITA:
                eff = _is_effective_value(kind, r["efetivado"])
                conta, destino, card, juros = r["id_conta"], None, None, 0.0
            else:
                eff = _is_effective_value(kind, r["contabilizada"])
                conta, destino, card, juros = (
                    r["id_conta_origem"],
                    r["id_conta_destino"],
                    None,
                    0.0,
                )
            result.append(
                self._build_occurrence(
                    kind,
                    r,
                    is_fixed=False,
                    year=ref_date.year,
                    month=ref_date.month,
                    valor=float(r["valor"] or 0.0),
                    juros=juros,
                    efetivada=eff,
                    venc=venc,
                    data_evento=parse_date(r["data_evento"]) if "data_evento" in keys else None,
                    data_efetivacao=parse_date(r["data_efetivacao"]) if "data_efetivacao" in keys else None,
                    ref_date=ref_date,
                    id_conta=str(conta) if conta else None,
                    id_conta_destino=str(destino) if destino else None,
                    id_cartao=card,
                )
            )
        return result

    def _load_fixed(
        self, kind: str, year: int, month: int, mode: str, profile_id: Optional[str]
    ) -> List[Occurrence]:
        start, _end = month_bounds(year, month)
        cat_cols, cat_join = self._category_sql(kind)
        codes = FIXED_CODES[kind]
        ph = ",".join("?" * len(codes))
        sql = (
            f"SELECT d.* {cat_cols} FROM {_TABLES[kind]} d {cat_join} "
            f"WHERE COALESCE(d.recorrencia, 'U') IN ({ph}) "
            "AND date(d.data, 'start of month') <= date(?) "
            "AND (d.data_exclusao IS NULL OR date(d.data_exclusao) >= date(?))"
        )
        params: list = [*codes, start.isoformat(), start.isoformat()]
        if profile_id:
            sql += " AND d.id_profile = ?"
            params.append(str(profile_id))
        base_rows = self.db.execute_query(sql, params)
        if not base_rows:
            return []

        fix_table, fk = _FIXED_TABLES[kind]
        ids = [str(r["id"]) for r in base_rows]
        overrides: Dict[str, list] = {}
        for chunk in _chunks(ids):
            ph_ids = ",".join("?" * len(chunk))
            rows = self.db.execute_query(
                f"SELECT * FROM {fix_table} WHERE {fk} IN ({ph_ids}) "
                "AND date(data, 'start of month') <= date(?) ORDER BY date(data) ASC",
                [*chunk, start.isoformat()],
            )
            for o in rows:
                overrides.setdefault(str(o[fk]), []).append(o)

        result: List[Occurrence] = []
        for r in base_rows:
            ovs = overrides.get(str(r["id"]), [])
            exact = None
            for o in ovs:
                od = parse_date(o["data"])
                if od and od.year == year and od.month == month:
                    exact = o
            if exact is not None and str(exact["excluido_mes"] or "N").upper() == "S":
                continue
            ekeys = set(exact.keys()) if exact is not None else set()

            def eval_col(col: str):
                if exact is not None and col in ekeys and exact[col] not in (None, ""):
                    return exact[col]
                return None

            base_date = parse_date(r["data"]) or start
            valor = float(
                eval_col("valor") if eval_col("valor") is not None else (r["valor"] or 0.0)
            )
            day = int(eval_col("dia_venc") or base_date.day)
            venc = date(year, month, clamp_day(year, month, day))

            if kind == KIND_DESPESA:
                eff = exact is not None and _is_effective_value(kind, exact["status"])
                conta = eval_col("id_conta") or r["id_conta"]
                destino = None
                card = self._clean_card(eval_col("id_cartao_credito") or r["id_cartao_credito"])
                juros = float(
                    exact["juros"]
                    if exact is not None and exact["juros"] is not None
                    else (r["juros"] or 0.0)
                )
            elif kind == KIND_RECEITA:
                eff = exact is not None and _is_effective_value(kind, exact["efetivado"])
                conta, destino, card, juros = eval_col("id_conta") or r["id_conta"], None, None, 0.0
            else:
                eff = exact is not None and _is_effective_value(kind, exact["contabilizada"])
                conta = eval_col("id_conta_origem") or r["id_conta_origem"]
                destino = eval_col("id_conta_destino") or r["id_conta_destino"]
                card, juros = None, 0.0

            data_efet = (
                parse_date(exact["data_efetivacao"])
                if exact is not None and "data_efetivacao" in ekeys
                else None
            )
            ref_date = venc
            if mode in ("efetivacao", MODE_SALDO) and eff and data_efet:
                if not (mode == MODE_SALDO and card):
                    ref_date = data_efet

            result.append(
                self._build_occurrence(
                    kind,
                    r,
                    is_fixed=True,
                    year=year,
                    month=month,
                    valor=valor,
                    juros=juros,
                    efetivada=eff,
                    venc=venc,
                    data_evento=venc,
                    data_efetivacao=data_efet,
                    ref_date=ref_date,
                    id_conta=str(conta) if conta else None,
                    id_conta_destino=str(destino) if destino else None,
                    id_cartao=card,
                )
            )
        return result

    def _attach_splits(self, occs: List[Occurrence]) -> None:
        desp = [o for o in occs if o.kind == KIND_DESPESA]
        if not desp:
            return
        ids = list({o.id for o in desp})
        by_id: Dict[str, List[SplitDTO]] = {}
        for chunk in _chunks(ids):
            ph = ",".join("?" * len(chunk))
            rows = self.db.execute_query(
                f"""
                SELECT dcv.id_despesa, dcv.id_categoria, dcv.id_subcategoria, dcv.valor,
                       COALESCE(dcv.obs, '') AS obs, c.nome AS cat_nome, c.cor AS cat_cor,
                       s.nome AS sub_nome
                FROM despesas_cat_valor dcv
                LEFT JOIN despesas_cat c ON c.id = dcv.id_categoria
                LEFT JOIN despesas_subcat s ON s.id = dcv.id_subcategoria
                WHERE dcv.id_despesa IN ({ph}) AND COALESCE(dcv.excluido, 'N') != 'S'
                ORDER BY dcv.valor DESC
                """,
                list(chunk),
            )
            for r in rows:
                by_id.setdefault(str(r["id_despesa"]), []).append(
                    SplitDTO(
                        id_categoria=str(r["id_categoria"]),
                        id_subcategoria=str(r["id_subcategoria"]),
                        valor=float(r["valor"] or 0.0),
                        obs=str(r["obs"]),
                        categoria_nome=str(r["cat_nome"] or ""),
                        subcategoria_nome=str(r["sub_nome"] or ""),
                        categoria_cor=argb_int_to_hex(int(r["cat_cor"]))
                        if r["cat_cor"] is not None
                        else "#5C6BC0",
                    )
                )
        for o in desp:
            splits = [SplitDTO(**vars(s)) for s in by_id.get(o.id, [])]
            total_splits = round(sum(s.valor for s in splits), 2)
            if splits and total_splits and abs(total_splits - o.valor) > 0.009:
                ratio = o.valor / total_splits
                for s in splits:
                    s.valor = round(s.valor * ratio, 2)
            o.splits = splits
            if len(splits) > 1:
                o.categoria_nome = f"Múltiplas categorias ({len(splits)})"
                o.categoria_cor = splits[0].categoria_cor
                o.subcategoria_nome = ", ".join(s.categoria_nome for s in splits)
            elif len(splits) == 1 and not o.categoria_nome:
                o.categoria_nome = splits[0].categoria_nome
                o.subcategoria_nome = splits[0].subcategoria_nome
                o.categoria_cor = splits[0].categoria_cor

    def _attach_names(self, occs: List[Occurrence]) -> None:
        if not occs:
            return
        contas = {
            str(r["id"]): str(r["descricao"] or "")
            for r in self.db.execute_query("SELECT id, descricao FROM contas")
        }
        cartoes = {
            str(r["id"]): str(r["nome"] or "")
            for r in self.db.execute_query("SELECT id, nome FROM cartoes_credito")
        }
        for o in occs:
            o.conta_nome = contas.get(o.id_conta or "", "")
            o.conta_destino_nome = contas.get(o.id_conta_destino or "", "")
            o.cartao_nome = cartoes.get(o.id_cartao or "", "")

    def _attach_tags(self, occs: List[Occurrence]) -> None:
        if not occs:
            return
        keys = list({o.id for o in occs} | {o.origin_id for o in occs})
        tag_map: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = {}
        for chunk in _chunks(keys):
            ph = ",".join("?" * len(chunk))
            rows = self.db.execute_query(
                f"""
                SELECT tt.id_transacao, tt.tipo_transacao, t.id, t.nome, COALESCE(t.cor, -14575885) AS cor
                FROM tags_transacoes tt
                JOIN tags t ON t.id = tt.id_tag
                WHERE tt.id_transacao IN ({ph})
                ORDER BY t.nome
                """,
                list(chunk),
            )
            for r in rows:
                tag_map.setdefault(
                    (str(r["id_transacao"]), str(r["tipo_transacao"]).upper()), []
                ).append((str(r["id"]), str(r["nome"]), argb_int_to_hex(int(r["cor"]))))
        for o in occs:
            own = tag_map.get((o.id, o.kind))
            o.tags = list(own) if own else list(tag_map.get((o.origin_id, o.kind), []))

    def list_occurrences(
        self,
        year: int,
        month: int,
        *,
        mode: Optional[str] = None,
        profile_id: Optional[str] = None,
        account_id: Optional[str] = None,
        id_conta: Optional[str] = None,
        card_id: Optional[str] = None,
        id_cartao: Optional[str] = None,
        kinds: Optional[Iterable[str]] = None,
        search_text: str = "",
        search: str = "",
        status: Optional[str] = None,  # 'confirmadas' | 'pendentes'
        only_effective: Optional[bool] = None,
        source: Optional[str] = None,  # 'contas' | 'cartoes'
        light: bool = False,
    ) -> List[Occurrence]:
        """Retorna todas as ocorrências do mês conforme o modo de data de referência e filtros."""
        mode = mode or self.db.settings.date_reference_mode or "vencimento"
        account_id = account_id or id_conta
        card_id = card_id or id_cartao
        search_text = search_text or search
        if only_effective is True:
            status = "confirmadas"
        elif only_effective is False:
            status = "pendentes"

        selected_kinds = tuple(kinds) if kinds else ALL_KINDS
        occs: List[Occurrence] = []
        for kind in selected_kinds:
            occs.extend(self._load_nonfixed(kind, year, month, mode, profile_id))
            occs.extend(self._load_fixed(kind, year, month, mode, profile_id))

        if account_id:
            acc = str(account_id)
            occs = [
                o
                for o in occs
                if not o.is_card
                and (
                    o.id_conta == acc
                    or (o.kind == KIND_TRANSFERENCIA and o.id_conta_destino == acc)
                )
            ]
        if card_id:
            occs = [o for o in occs if o.id_cartao == str(card_id)]
        if source == "contas":
            occs = [o for o in occs if not o.is_card]
        elif source == "cartoes":
            occs = [o for o in occs if o.is_card]
        if status == "confirmadas":
            occs = [o for o in occs if o.efetivada]
        elif status == "pendentes":
            occs = [o for o in occs if not o.efetivada]

        if not light:
            self._attach_splits(occs)
            self._attach_names(occs)
            self._attach_tags(occs)

        query = search_text.strip().lower()
        if query:
            def matches(o: Occurrence) -> bool:
                hay = " ".join(
                    [
                        o.descricao,
                        o.categoria_nome,
                        o.subcategoria_nome,
                        o.obs,
                        o.conta_nome,
                        o.conta_destino_nome,
                        o.cartao_nome,
                        " ".join(t[1] for t in o.tags),
                    ]
                ).lower()
                return query in hay

            occs = [o for o in occs if matches(o)]

        kind_order = {KIND_RECEITA: 0, KIND_DESPESA: 1, KIND_TRANSFERENCIA: 2}
        occs.sort(key=lambda o: (o.ref_date, kind_order.get(o.kind, 9), o.descricao.lower()))
        return occs

    # ------------------------------------------------------------------ #
    # ESCRITA
    # ------------------------------------------------------------------ #
    def default_category(self, kind: str, profile_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Categoria/Subcategoria padrão ('Outros') do perfil."""
        if kind == KIND_DESPESA:
            cat_table, name_col, sub_table = "despesas_cat", "nome", "despesas_subcat"
        elif kind == KIND_RECEITA:
            cat_table, name_col, sub_table = "receitas_cat", "descricao", "receitas_subcat"
        else:
            return None, None
        cat = self.db.fetch_scalar(
            f"""
            SELECT id FROM {cat_table}
            WHERE id_profile = ? AND data_exclusao IS NULL
            ORDER BY CASE WHEN LOWER({name_col}) = 'outros' THEN 0 ELSE 1 END, {name_col}
            LIMIT 1
            """,
            (str(profile_id),),
        )
        if cat is None:
            return None, None
        sub = self.default_subcategory(kind, str(cat))
        return str(cat), sub

    def default_subcategory(self, kind: str, category_id: str) -> Optional[str]:
        sub_table = "despesas_subcat" if kind == KIND_DESPESA else "receitas_subcat"
        sub = self.db.fetch_scalar(
            f"""
            SELECT id FROM {sub_table}
            WHERE id_categoria = ? AND data_exclusao IS NULL
            ORDER BY CASE WHEN LOWER(nome) = 'outros' THEN 0 ELSE 1 END, nome
            LIMIT 1
            """,
            (str(category_id),),
        )
        return str(sub) if sub is not None else None

    def _normalize_splits(
        self,
        profile_id: str,
        splits: Optional[List[SplitDTO]],
        id_categoria: Optional[str],
        id_subcategoria: Optional[str],
        total: float,
    ) -> List[SplitDTO]:
        if not splits:
            cat, sub = id_categoria, id_subcategoria
            if not cat:
                cat, sub = self.default_category(KIND_DESPESA, profile_id)
            if cat and not sub:
                sub = self.default_subcategory(KIND_DESPESA, cat)
            splits = [SplitDTO(str(cat or "-1"), str(sub or "-1"), float(total))]
        aggregated: Dict[Tuple[str, str], SplitDTO] = {}
        for s in splits:
            cat = str(s.id_categoria or "-1")
            sub = str(s.id_subcategoria or "") or (self.default_subcategory(KIND_DESPESA, cat) or "-1")
            key = (cat, sub)
            if key in aggregated:
                aggregated[key].valor = round(aggregated[key].valor + float(s.valor), 2)
            else:
                aggregated[key] = SplitDTO(cat, sub, round(float(s.valor), 2), s.obs or "")
        return list(aggregated.values())

    @staticmethod
    def _scale_splits(splits: List[SplitDTO], amount: float) -> List[Tuple[str, str, float, str]]:
        total = round(sum(s.valor for s in splits), 2)
        if not splits:
            return []
        if not total:
            return [(splits[0].id_categoria, splits[0].id_subcategoria, round(amount, 2), splits[0].obs)]
        scaled: List[Tuple[str, str, float, str]] = []
        acc = 0.0
        for i, s in enumerate(splits):
            if i == len(splits) - 1:
                val = round(amount - acc, 2)
            else:
                val = round(amount * (s.valor / total), 2)
                acc = round(acc + val, 2)
            scaled.append((s.id_categoria, s.id_subcategoria, val, s.obs))
        return scaled

    def _write_splits(
        self, cur, despesa_id: str, splits: List[SplitDTO], amount: float, data: date
    ) -> None:
        cur.execute("DELETE FROM despesas_cat_valor WHERE id_despesa = ?", (despesa_id,))
        for cat, sub, val, obs in self._scale_splits(splits, amount):
            cur.execute(
                """
                INSERT INTO despesas_cat_valor (id, id_despesa, id_categoria, id_subcategoria, valor, obs, excluido, data)
                VALUES (?, ?, ?, ?, ?, ?, 'N', ?)
                """,
                (new_id(), despesa_id, cat, sub, val, obs, data.isoformat()),
            )

    def _series_dates(
        self, first: date, count: int, intervalo: int, card_due_day: Optional[int]
    ) -> List[date]:
        if card_due_day:
            return [add_months(first, i, day=card_due_day) for i in range(count)]
        return [add_interval(first, i, intervalo) for i in range(count)]

    @staticmethod
    def _series_amounts(valor: float, count: int, valor_por_parcela: bool) -> List[float]:
        if count <= 1:
            return [round(float(valor), 2)]
        if valor_por_parcela:
            return [round(float(valor), 2)] * count
        return split_amount(valor, count)

    def create_expense(
        self,
        *,
        descricao: str,
        valor: float,
        data_vencimento: date,
        profile_id: str = "1",
        id_conta: Optional[str] = None,
        id_cartao: Optional[str] = None,
        data_evento: Optional[date] = None,
        id_categoria: Optional[str] = None,
        id_subcategoria: Optional[str] = None,
        splits: Optional[List[SplitDTO]] = None,
        recorrencia: str = REC_UNICA,
        num_parcelas: int = 1,
        intervalo: int = 30,
        valor_por_parcela: bool = False,
        pago: bool = False,
        data_efetivacao: Optional[date] = None,
        juros: float = 0.0,
        obs: str = "",
        tag_ids: Optional[List[str]] = None,
        contabilizar: bool = True,
        id_despesa_estornada: Optional[str] = None,
        terceiro_em_nome_de: Optional[str] = None,
        gerar_emprestimo_terceiro: bool = False,
        num_parcela: Optional[int] = None,
        id_origem: Optional[str] = None,
        preserve_due_date: bool = False,
    ) -> List[str]:
        """Cria despesa única, parcelada ou fixa (em conta ou cartão de crédito) com rateio e suporte a compra de terceiro."""
        if not descricao.strip():
            raise ValueError("Informe a descrição da despesa.")
        pessoa_terceiro = (terceiro_em_nome_de or "").strip()
        if gerar_emprestimo_terceiro or pessoa_terceiro:
            contabilizar = False
            pessoa_terceiro = pessoa_terceiro or "Terceiro / Familiar"
            tag_marker = f"[Terceiro: {pessoa_terceiro}]"
            if tag_marker.lower() not in (obs or "").lower():
                obs = f"{tag_marker} {obs}".strip()

        card_due_day: Optional[int] = None
        first_due = data_vencimento
        if id_cartao:
            from app.domain.services.credit_card_service import CreditCardService

            card_service = CreditCardService(self.db, self)
            card = card_service.get_card(id_cartao)
            if card is None:
                raise ValueError("Cartão de crédito não encontrado.")
            purchase = data_evento or data_vencimento
            data_evento = purchase
            if preserve_due_date and data_vencimento:
                first_due = data_vencimento
            else:
                first_due = card_service.compute_due_date(card, purchase)
            card_due_day = card.dia_venc
            id_conta = id_conta or card.id_conta
            pago = False
        data_evento = data_evento or data_vencimento

        is_fixed = recorrencia in FIXED_CODES[KIND_DESPESA] or recorrencia == "M"

        # Caso especial: criação de uma parcela individual já posicionada de uma série existente/importada
        if num_parcela is not None and int(num_parcelas) > 1 and not is_fixed:
            rec_code = REC_PARCELADA
            amounts = [valor]
            origin = id_origem or new_id()
            this_parc = int(num_parcela)
            tot_parcs = int(num_parcelas)
            dates = [first_due]
            norm_splits = self._normalize_splits(
                profile_id, splits, id_categoria, id_subcategoria, valor
            )
            single_cat = norm_splits[0] if len(norm_splits) == 1 else None
            now = _now_str()
            contab_flag = "S" if contabilizar else "N"
            with self.db.transaction() as cur:
                rid = origin if this_parc == 1 else new_id()
                paid_now = pago and not is_fixed
                cur.execute(
                    """
                    INSERT INTO despesas (
                        id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                        obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                        parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                        id_subcategoria, data_efetivacao, contabilizar, considerar_estatistica,
                        somar_total, id_despesa_estornada, data_update, ultima_modificacao
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'S', ?, ?, ?)
                    """,
                    (
                        rid,
                        str(profile_id),
                        descricao.strip(),
                        amounts[0],
                        rec_code,
                        dates[0].isoformat(),
                        to_db_date(data_evento),
                        "pg" if paid_now else "pd",
                        obs,
                        now,
                        id_conta,
                        origin,
                        this_parc,
                        tot_parcs,
                        int(intervalo or 30),
                        float(juros),
                        id_cartao,
                        single_cat.id_categoria if single_cat else None,
                        single_cat.id_subcategoria if single_cat else None,
                        to_db_date(data_efetivacao or dates[0]) if paid_now else None,
                        contab_flag,
                        contab_flag,
                        id_despesa_estornada,
                        now,
                        now,
                    ),
                )
                self._write_splits(cur, rid, norm_splits, amounts[0], dates[0])
                return [rid]

        rec_code = fixed_code_for(KIND_DESPESA) if is_fixed else (
            REC_PARCELADA if recorrencia == REC_PARCELADA and num_parcelas > 1 else REC_UNICA
        )
        count = int(num_parcelas) if rec_code == REC_PARCELADA else 1
        amounts = self._series_amounts(valor, count, valor_por_parcela)
        series_total = round(sum(amounts), 2)
        norm_splits = self._normalize_splits(
            profile_id, splits, id_categoria, id_subcategoria, series_total
        )
        single_cat = norm_splits[0] if len(norm_splits) == 1 else None
        dates = self._series_dates(first_due, count, intervalo, card_due_day)

        origin = new_id()
        ids: List[str] = []
        now = _now_str()
        contab_flag = "S" if contabilizar else "N"
        with self.db.transaction() as cur:
            for i in range(count):
                rid = origin if i == 0 else new_id()
                venc = dates[i]
                paid_now = pago and i == 0 and not is_fixed
                evt = data_evento
                cur.execute(
                    """
                    INSERT INTO despesas (
                        id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                        obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                        parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                        id_subcategoria, data_efetivacao, contabilizar, considerar_estatistica,
                        somar_total, id_despesa_estornada, data_update, ultima_modificacao
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'S', ?, ?, ?)
                    """,
                    (
                        rid,
                        str(profile_id),
                        descricao.strip(),
                        amounts[i],
                        rec_code,
                        venc.isoformat(),
                        to_db_date(evt),
                        "pg" if paid_now else "pd",
                        obs,
                        now,
                        id_conta,
                        origin,
                        i + 1,
                        count,
                        int(intervalo or 30),
                        float(juros) if i == 0 else 0.0,
                        id_cartao,
                        single_cat.id_categoria if single_cat else None,
                        single_cat.id_subcategoria if single_cat else None,
                        to_db_date(data_efetivacao or venc) if paid_now else None,
                        contab_flag,
                        contab_flag,
                        id_despesa_estornada,
                        now,
                        now,
                    ),
                )
                self._write_splits(cur, rid, norm_splits, amounts[i], venc)
                ids.append(rid)

            if gerar_emprestimo_terceiro or pessoa_terceiro:
                loan_id = new_id()
                parc_suffix = f" ({count}x)" if count > 1 else ""
                loan_desc = f"Cartão: {descricao.strip()}{parc_suffix}"
                cur.execute(
                    """
                    INSERT INTO emprestimos (
                        id, id_profile, descricao, pessoa, concedido, moeda,
                        id_conta, data, principal, saldo_historico, arquivado, observacao
                    ) VALUES (?, ?, ?, ?, 'S', 'BRL', ?, ?, ?, 0, 'N', ?)
                    """,
                    (
                        loan_id,
                        str(profile_id),
                        loan_desc,
                        pessoa_terceiro,
                        str(id_conta or ""),
                        to_db_date(data_evento),
                        series_total,
                        f"Gerado automaticamente de compra em nome de terceiro ({count}x). Origem: {origin}",
                    ),
                )
                vinc_id = new_id()
                cur.execute(
                    """
                    INSERT INTO emprestimos_vinculos (
                        id, id_profile, id_emprestimo, id_transacao,
                        tipo_transacao, papel, valor, data
                    ) VALUES (?, ?, ?, ?, 'DESPESA_CARTAO', 'ORIGEM', 0, ?)
                    """,
                    (
                        vinc_id,
                        str(profile_id),
                        loan_id,
                        origin,
                        to_db_date(data_evento),
                    ),
                )

        if is_fixed and pago:
            occ = self._first_fixed_occurrence(KIND_DESPESA, origin, first_due)
            if occ:
                self.set_effective(occ, True, data_efetivacao or first_due)
        if tag_ids:
            self._set_tags(origin, KIND_DESPESA, tag_ids)
        return ids

    def create_income(
        self,
        *,
        descricao: str,
        valor: float,
        data: date,
        id_conta: Optional[str],
        profile_id: str = "1",
        id_categoria: Optional[str] = None,
        id_subcategoria: Optional[str] = None,
        data_evento: Optional[date] = None,
        recorrencia: str = REC_UNICA,
        num_parcelas: int = 1,
        intervalo: int = 30,
        valor_por_parcela: bool = False,
        recebido: bool = False,
        data_efetivacao: Optional[date] = None,
        obs: str = "",
        tag_ids: Optional[List[str]] = None,
        contabilizar: bool = True,
    ) -> List[str]:
        """Cria receita única, parcelada ou fixa mensal."""
        if not descricao.strip():
            raise ValueError("Informe a descrição da receita.")
        if not id_categoria:
            id_categoria, id_subcategoria = self.default_category(KIND_RECEITA, profile_id)
        elif not id_subcategoria:
            id_subcategoria = self.default_subcategory(KIND_RECEITA, id_categoria)

        is_fixed = recorrencia in FIXED_CODES[KIND_RECEITA]
        rec_code = fixed_code_for(KIND_RECEITA) if is_fixed else (
            REC_PARCELADA if recorrencia == REC_PARCELADA and num_parcelas > 1 else REC_UNICA
        )
        count = int(num_parcelas) if rec_code == REC_PARCELADA else 1
        amounts = self._series_amounts(valor, count, valor_por_parcela)
        dates = self._series_dates(data, count, intervalo, None)
        origin = new_id()
        ids: List[str] = []
        now = _now_str()
        contab_flag = "S" if contabilizar else "N"
        with self.db.transaction() as cur:
            for i in range(count):
                rid = origin if i == 0 else new_id()
                received_now = recebido and i == 0 and not is_fixed
                cur.execute(
                    """
                    INSERT INTO receitas (
                        id, id_profile, descricao, valor, recorrencia, data, data_evento, efetivado,
                        obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas, intervalo,
                        id_categoria, id_subcategoria, data_efetivacao, somar_total,
                        considerar_estatistica, data_update, ultima_modificacao
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'S', ?, ?, ?)
                    """,
                    (
                        rid,
                        str(profile_id),
                        descricao.strip(),
                        amounts[i],
                        rec_code,
                        dates[i].isoformat(),
                        to_db_date(data_evento or data),
                        "S" if received_now else "N",
                        obs,
                        now,
                        id_conta,
                        origin,
                        i + 1,
                        count,
                        int(intervalo or 30),
                        id_categoria,
                        id_subcategoria,
                        to_db_date(data_efetivacao or dates[i]) if received_now else None,
                        contab_flag,
                        now,
                        now,
                    ),
                )
                ids.append(rid)
        if is_fixed and recebido:
            occ = self._first_fixed_occurrence(KIND_RECEITA, origin, data)
            if occ:
                self.set_effective(occ, True, data_efetivacao or data)
        if tag_ids:
            self._set_tags(origin, KIND_RECEITA, tag_ids)
        return ids

    def create_transfer(
        self,
        *,
        descricao: str,
        valor: float,
        data: date,
        id_conta_origem: str,
        id_conta_destino: str,
        profile_id: str = "1",
        recorrencia: str = REC_UNICA,
        num_parcelas: int = 1,
        intervalo: int = 30,
        valor_por_parcela: bool = False,
        efetivada: bool = False,
        data_efetivacao: Optional[date] = None,
        obs: str = "",
        tag_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Cria transferência entre contas (única, parcelada ou fixa mensal)."""
        if not id_conta_origem or not id_conta_destino:
            raise ValueError("Informe as contas de origem e destino.")
        if str(id_conta_origem) == str(id_conta_destino):
            raise ValueError("A conta de origem deve ser diferente da conta de destino.")
        is_fixed = recorrencia in FIXED_CODES[KIND_TRANSFERENCIA]
        rec_code = fixed_code_for(KIND_TRANSFERENCIA) if is_fixed else (
            REC_PARCELADA if recorrencia == REC_PARCELADA and num_parcelas > 1 else REC_UNICA
        )
        count = int(num_parcelas) if rec_code == REC_PARCELADA else 1
        amounts = self._series_amounts(valor, count, valor_por_parcela)
        dates = self._series_dates(data, count, intervalo, None)
        origin = new_id()
        ids: List[str] = []
        now = _now_str()
        desc = descricao.strip() or "Transferência entre contas"
        with self.db.transaction() as cur:
            for i in range(count):
                rid = origin if i == 0 else new_id()
                eff_now = efetivada and i == 0 and not is_fixed
                cur.execute(
                    """
                    INSERT INTO transferencias (
                        id, id_profile, id_origem, id_conta_origem, id_conta_destino, data, valor,
                        contabilizada, descricao, obs, data_update, recorrencia, intervalo,
                        num_parcela, num_parcelas, data_cadastro, data_efetivacao, ultima_modificacao
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rid,
                        str(profile_id),
                        origin,
                        str(id_conta_origem),
                        str(id_conta_destino),
                        dates[i].isoformat(),
                        amounts[i],
                        "S" if eff_now else "N",
                        desc,
                        obs,
                        now,
                        rec_code,
                        int(intervalo or 30),
                        i + 1,
                        count,
                        now,
                        to_db_date(data_efetivacao or dates[i]) if eff_now else None,
                        now,
                    ),
                )
                ids.append(rid)
        if is_fixed and efetivada:
            occ = self._first_fixed_occurrence(KIND_TRANSFERENCIA, origin, data)
            if occ:
                self.set_effective(occ, True, data_efetivacao or data)
        if tag_ids:
            self._set_tags(origin, KIND_TRANSFERENCIA, tag_ids)
        return ids

    def _first_fixed_occurrence(self, kind: str, base_id: str, when: date) -> Optional[Occurrence]:
        for o in self._load_fixed(kind, when.year, when.month, "vencimento", None):
            if o.id == base_id:
                return o
        return None

    def get_occurrence(
        self, kind: str, base_id: str, year: int, month: int
    ) -> Optional[Occurrence]:
        """Localiza a ocorrência (por vencimento) de uma transação em um mês."""
        for o in self.list_occurrences(year, month, mode="vencimento", kinds=[kind]):
            if o.id == base_id:
                return o
        return None

    def _set_tags(self, transaction_id: str, kind: str, tag_ids: List[str]) -> None:
        from app.database.repositories.tag_repository import TagRepository

        TagRepository(self.db).set_transaction_tags(transaction_id, kind, tag_ids)

    def set_tags_for(self, occ: Occurrence, tag_ids: List[str]) -> None:
        self._set_tags(occ.origin_id, occ.kind, tag_ids)

    def _write_fixed_override(
        self,
        cur,
        occ: Occurrence,
        *,
        valor: Optional[float] = None,
        efetivada: Optional[bool] = None,
        data_efetivacao: Optional[date] = None,
        id_conta: Optional[str] = None,
        id_conta_destino: Optional[str] = None,
        excluido: bool = False,
        juros: Optional[float] = None,
    ) -> None:
        """Grava a exceção mensal (`*_fixas`) de uma recorrência fixa (substitui a do mesmo mês)."""
        fix_table, fk = _FIXED_TABLES[occ.kind]
        eff = occ.efetivada if efetivada is None else efetivada
        val = occ.valor if valor is None else float(valor)
        efet_date = to_db_date(data_efetivacao or (occ.data_efetivacao if eff else None)) if eff else None
        day = occ.data_vencimento.day
        excl = "S" if excluido else "N"
        if occ.kind == KIND_DESPESA:
            cur.execute(
                """
                INSERT INTO despesas_fixas (
                    id, id_despesa, data, valor, status, obs, id_conta, id_cartao_credito,
                    contabilizar, excluido_mes, juros, dia_venc, data_efetivacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'S', ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    occ.id,
                    occ.data_vencimento.isoformat(),
                    val,
                    "pg" if eff else "pd",
                    occ.obs,
                    id_conta or occ.id_conta,
                    occ.id_cartao,
                    excl,
                    occ.juros if juros is None else float(juros),
                    day,
                    efet_date,
                ),
            )
        elif occ.kind == KIND_RECEITA:
            cur.execute(
                """
                INSERT INTO receitas_fixas (
                    id, id_receita, data, excluido_mes, valor, obs, efetivado, id_conta,
                    dia_venc, data_efetivacao
                ) VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM receitas_fixas), ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    occ.id,
                    occ.data_vencimento.isoformat(),
                    excl,
                    val,
                    occ.obs,
                    "S" if eff else "N",
                    id_conta or occ.id_conta,
                    day,
                    efet_date,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO transferencias_fixas (
                    id, id_transferencia, id_conta_origem, id_conta_destino, data, excluido_mes,
                    valor, dia_venc, contabilizada, obs, data_efetivacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    occ.id,
                    id_conta or occ.id_conta,
                    id_conta_destino or occ.id_conta_destino,
                    occ.data_vencimento.isoformat(),
                    excl,
                    val,
                    day,
                    "S" if eff else "N",
                    occ.obs,
                    efet_date,
                ),
            )

    def set_effective(
        self,
        occ: Occurrence,
        effective: bool,
        data_efetivacao: Optional[date] = None,
        valor: Optional[float] = None,
        id_conta: Optional[str] = None,
    ) -> None:
        """Confirma (paga/recebe/efetiva) ou desfaz a confirmação de uma ocorrência."""
        efet_date = (data_efetivacao or occ.data_vencimento) if effective else None
        with self.db.transaction() as cur:
            if occ.is_fixed:
                self._write_fixed_override(
                    cur,
                    occ,
                    valor=valor,
                    efetivada=effective,
                    data_efetivacao=efet_date,
                    id_conta=id_conta,
                )
                return
            table = _TABLES[occ.kind]
            new_val = occ.valor if valor is None else float(valor)
            if occ.kind == KIND_DESPESA:
                cur.execute(
                    """
                    UPDATE despesas SET status = ?, data_efetivacao = ?, valor = ?,
                        id_conta = COALESCE(?, id_conta), ultima_modificacao = ?
                    WHERE id = ?
                    """,
                    ("pg" if effective else "pd", to_db_date(efet_date), new_val, id_conta, _now_str(), occ.id),
                )
                if valor is not None and abs(new_val - occ.valor) > 0.004:
                    splits = occ.splits or self._load_splits(occ.id)
                    self._write_splits(cur, occ.id, splits, new_val, occ.data_vencimento)
            elif occ.kind == KIND_RECEITA:
                cur.execute(
                    f"UPDATE {table} SET efetivado = ?, data_efetivacao = ?, valor = ?, "
                    "id_conta = COALESCE(?, id_conta), ultima_modificacao = ? WHERE id = ?",
                    ("S" if effective else "N", to_db_date(efet_date), new_val, id_conta, _now_str(), occ.id),
                )
            else:
                cur.execute(
                    f"UPDATE {table} SET contabilizada = ?, data_efetivacao = ?, valor = ?, "
                    "ultima_modificacao = ? WHERE id = ?",
                    ("S" if effective else "N", to_db_date(efet_date), new_val, _now_str(), occ.id),
                )

    def _load_splits(self, despesa_id: str) -> List[SplitDTO]:
        rows = self.db.execute_query(
            "SELECT id_categoria, id_subcategoria, valor, COALESCE(obs, '') AS obs "
            "FROM despesas_cat_valor WHERE id_despesa = ? AND COALESCE(excluido, 'N') != 'S'",
            (despesa_id,),
        )
        return [
            SplitDTO(str(r["id_categoria"]), str(r["id_subcategoria"]), float(r["valor"] or 0), r["obs"])
            for r in rows
        ]

    def delete_occurrence(self, occ: Occurrence, scope: str = "this") -> None:
        """
        Exclui uma ocorrência conforme o escopo:
        - 'this': somente esta ocorrência (fixas: exceção do mês `excluido_mes='S'`).
        - 'future': esta e as próximas (parcelas >= atual / encerra a recorrência fixa).
        - 'all': toda a série.
        """
        table = _TABLES[occ.kind]
        with self.db.transaction() as cur:
            if occ.is_fixed:
                base_row = cur.execute(f"SELECT data FROM {table} WHERE id = ?", (occ.id,)).fetchone()
                base_date = parse_date(base_row[0]) if base_row else occ.data_vencimento
                starts_now = base_date is None or (
                    (occ.occ_year, occ.occ_month) <= (base_date.year, base_date.month)
                )
                if scope == "all" or (scope == "future" and starts_now):
                    cur.execute(f"DELETE FROM {table} WHERE id = ?", (occ.id,))
                    cur.execute(
                        "DELETE FROM tags_transacoes WHERE id_transacao = ? AND tipo_transacao = ?",
                        (occ.id, occ.kind),
                    )
                elif scope == "future":
                    prev_month_end = add_months(date(occ.occ_year, occ.occ_month, 1), 0) 
                    prev_month_end = date(occ.occ_year, occ.occ_month, 1).fromordinal(
                        date(occ.occ_year, occ.occ_month, 1).toordinal() - 1
                    )
                    cur.execute(
                        f"UPDATE {table} SET data_exclusao = ? WHERE id = ?",
                        (prev_month_end.isoformat(), occ.id),
                    )
                else:
                    self._write_fixed_override(cur, occ, excluido=True)
                return

            if occ.num_parcelas > 1 and scope in ("future", "all"):
                if scope == "all":
                    rows = cur.execute(
                        f"SELECT id FROM {table} WHERE COALESCE(NULLIF(id_origem, ''), id) = ?",
                        (occ.origin_id,),
                    ).fetchall()
                else:
                    rows = cur.execute(
                        f"SELECT id FROM {table} WHERE COALESCE(NULLIF(id_origem, ''), id) = ? "
                        "AND COALESCE(num_parcela, 1) >= ?",
                        (occ.origin_id, occ.num_parcela),
                    ).fetchall()
                ids = [str(r[0]) for r in rows]
            else:
                ids = [occ.id]
            for rid in ids:
                cur.execute(f"DELETE FROM {table} WHERE id = ?", (rid,))
                cur.execute(
                    "DELETE FROM tags_transacoes WHERE id_transacao = ? AND tipo_transacao = ?",
                    (rid, occ.kind),
                )

    def _convert_occurrence_kind(
        self,
        occ: Occurrence,
        new_kind: str,
        *,
        scope: str = "this",
        descricao: Optional[str] = None,
        valor: Optional[float] = None,
        data_vencimento: Optional[date] = None,
        data_evento: Optional[date] = None,
        id_conta: Optional[str] = None,
        id_cartao: Optional[str] = None,
        id_categoria: Optional[str] = None,
        id_subcategoria: Optional[str] = None,
        splits: Optional[List[SplitDTO]] = None,
        obs: Optional[str] = None,
        efetivada: Optional[bool] = None,
        data_efetivacao: Optional[date] = None,
        tag_ids: Optional[List[str]] = None,
    ) -> None:
        """
        Converte atomicamente uma ocorrência entre DESPESA e RECEITA.
        - 'despesa' -> 'receita': limpa splits em despesas_cat_valor, remove de despesas/despesas_fixas,
          insere em receitas/receitas_fixas e atualiza tipo em tags_transacoes.
        - 'receita' -> 'despesa': remove de receitas/receitas_fixas, insere em despesas/despesas_fixas,
          grava splits em despesas_cat_valor e atualiza tags_transacoes.
        Suporta escopos:
        - 'this': converte apenas a ocorrência atual (em fixas, grava exceção de exclusão no mês de origem).
        - 'all': converte toda a série parcelada ou recorrência fixa.
        """
        old_kind = occ.kind
        target_kind = new_kind.upper()
        if old_kind == target_kind or old_kind not in (KIND_DESPESA, KIND_RECEITA) or target_kind not in (KIND_DESPESA, KIND_RECEITA):
            return

        now = _now_str()
        new_desc = (descricao if descricao is not None else occ.descricao).strip() or (
            "Receita convertida" if target_kind == KIND_RECEITA else "Despesa convertida"
        )
        new_val = occ.valor if valor is None else round(float(valor), 2)
        new_due = data_vencimento or occ.data_vencimento
        new_evt = data_evento or occ.data_evento or new_due
        new_obs = occ.obs if obs is None else obs
        new_eff = occ.efetivada if efetivada is None else efetivada
        new_eff_date = (data_efetivacao or (occ.data_efetivacao if new_eff else None) or new_due) if new_eff else None

        with self.db.transaction() as cur:
            # 1. Determinação da conta bancária / cartão
            target_account: Optional[str] = None
            target_card: Optional[str] = None
            if target_kind == KIND_RECEITA:
                target_account = id_conta or (occ.id_conta if not occ.is_card else None)
                if not target_account:
                    acc_row = cur.execute(
                        "SELECT id FROM contas WHERE id_profile = ? AND data_exclusao IS NULL ORDER BY nome LIMIT 1",
                        (str(occ.id_profile),),
                    ).fetchone()
                    target_account = str(acc_row[0]) if acc_row else "1"
            else:
                target_card = id_cartao
                target_account = id_conta if not target_card else (id_conta or occ.id_conta)
                if not target_account and not target_card:
                    target_account = occ.id_conta or "1"

            # 2. Determinação de categoria e rateios
            norm_splits: Optional[List[SplitDTO]] = None
            single_cat: Optional[SplitDTO] = None
            if target_kind == KIND_RECEITA:
                cat_valid = False
                if id_categoria:
                    cat_valid = bool(
                        cur.execute(
                            "SELECT 1 FROM receitas_cat WHERE id = ? AND data_exclusao IS NULL",
                            (str(id_categoria),),
                        ).fetchone()
                    )
                if not cat_valid:
                    id_categoria, id_subcategoria = self.default_category(KIND_RECEITA, occ.id_profile)
                elif not id_subcategoria:
                    id_subcategoria = self.default_subcategory(KIND_RECEITA, str(id_categoria))
            else:
                cat_valid = False
                if id_categoria:
                    cat_valid = bool(
                        cur.execute(
                            "SELECT 1 FROM despesas_cat WHERE id = ? AND data_exclusao IS NULL",
                            (str(id_categoria),),
                        ).fetchone()
                    )
                if not cat_valid and not splits:
                    id_categoria, id_subcategoria = self.default_category(KIND_DESPESA, occ.id_profile)
                norm_splits = self._normalize_splits(
                    occ.id_profile, splits, id_categoria, id_subcategoria, new_val
                )
                single_cat = norm_splits[0] if len(norm_splits) == 1 else None

            # 3. Conversão por escopo / tipo de série
            converted_tx_ids: List[str] = []

            # A) FIXA
            if occ.is_fixed:
                if scope == "all":
                    if old_kind == KIND_DESPESA:
                        cur.execute("DELETE FROM despesas_fixas WHERE id_despesa = ?", (occ.id,))
                        cur.execute("DELETE FROM despesas_cat_valor WHERE id_despesa = ?", (occ.id,))
                        cur.execute("DELETE FROM despesas WHERE id = ?", (occ.id,))
                    else:
                        cur.execute("DELETE FROM receitas_fixas WHERE id_receita = ?", (occ.id,))
                        cur.execute("DELETE FROM receitas WHERE id = ?", (occ.id,))

                    if target_kind == KIND_RECEITA:
                        rec_code = fixed_code_for(KIND_RECEITA)
                        cur.execute(
                            """
                            INSERT INTO receitas (
                                id, id_profile, descricao, valor, recorrencia, data, data_evento, efetivado,
                                obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas, intervalo,
                                id_categoria, id_subcategoria, data_efetivacao, somar_total,
                                considerar_estatistica, data_update, ultima_modificacao
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 30, ?, ?, ?, 'S', 'S', ?, ?)
                            """,
                            (
                                occ.id,
                                str(occ.id_profile),
                                new_desc,
                                new_val,
                                rec_code,
                                new_due.isoformat(),
                                to_db_date(new_evt),
                                "S" if new_eff else "N",
                                new_obs,
                                now,
                                target_account,
                                occ.id,
                                id_categoria,
                                id_subcategoria,
                                to_db_date(new_eff_date) if new_eff else None,
                                now,
                                now,
                            ),
                        )
                        if new_eff:
                            cur.execute(
                                """
                                INSERT INTO receitas_fixas (
                                    id, id_receita, data, excluido_mes, valor, obs, efetivado, id_conta,
                                    dia_venc, data_efetivacao
                                ) VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM receitas_fixas), ?, ?, 'N', ?, ?, 'S', ?, ?, ?)
                                """,
                                (
                                    occ.id,
                                    new_due.isoformat(),
                                    new_val,
                                    new_obs,
                                    target_account,
                                    new_due.day,
                                    to_db_date(new_eff_date),
                                ),
                            )
                    else:
                        rec_code = fixed_code_for(KIND_DESPESA)
                        cur.execute(
                            """
                            INSERT INTO despesas (
                                id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                                obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                                parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                                id_subcategoria, data_efetivacao, contabilizar, considerar_estatistica,
                                somar_total, data_update, ultima_modificacao
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 30, 0, ?, ?, ?, ?, 'S', 'S', 'S', ?, ?)
                            """,
                            (
                                occ.id,
                                str(occ.id_profile),
                                new_desc,
                                new_val,
                                rec_code,
                                new_due.isoformat(),
                                to_db_date(new_evt),
                                "pg" if (new_eff and not target_card) else "pd",
                                new_obs,
                                now,
                                target_account if not target_card else None,
                                occ.id,
                                target_card,
                                single_cat.id_categoria if single_cat else None,
                                single_cat.id_subcategoria if single_cat else None,
                                to_db_date(new_eff_date) if (new_eff and not target_card) else None,
                                now,
                                now,
                            ),
                        )
                        if norm_splits:
                            self._write_splits(cur, occ.id, norm_splits, new_val, new_due)
                        if new_eff and not target_card:
                            cur.execute(
                                """
                                INSERT INTO despesas_fixas (
                                    id, id_despesa, data, valor, status, obs, id_conta, id_cartao_credito,
                                    contabilizar, excluido_mes, juros, dia_venc, data_efetivacao
                                ) VALUES (?, ?, ?, ?, 'pg', ?, ?, NULL, 'S', 'N', 0, ?, ?)
                                """,
                                (
                                    new_id(),
                                    occ.id,
                                    new_due.isoformat(),
                                    new_val,
                                    new_obs,
                                    target_account,
                                    new_due.day,
                                    to_db_date(new_eff_date),
                                ),
                            )
                    cur.execute(
                        "UPDATE tags_transacoes SET tipo_transacao = ? WHERE id_transacao = ?",
                        (target_kind, occ.id),
                    )
                    converted_tx_ids.append(occ.id)
                else:
                    # scope == "this": mantém a série original e exclui este mês nela
                    self._write_fixed_override(cur, occ, excluido=True)
                    new_item_id = new_id()
                    if target_kind == KIND_RECEITA:
                        cur.execute(
                            """
                            INSERT INTO receitas (
                                id, id_profile, descricao, valor, recorrencia, data, data_evento, efetivado,
                                obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas, intervalo,
                                id_categoria, id_subcategoria, data_efetivacao, somar_total,
                                considerar_estatistica, data_update, ultima_modificacao
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 30, ?, ?, ?, 'S', 'S', ?, ?)
                            """,
                            (
                                new_item_id,
                                str(occ.id_profile),
                                new_desc,
                                new_val,
                                REC_UNICA,
                                new_due.isoformat(),
                                to_db_date(new_evt),
                                "S" if new_eff else "N",
                                new_obs,
                                now,
                                target_account,
                                new_item_id,
                                id_categoria,
                                id_subcategoria,
                                to_db_date(new_eff_date) if new_eff else None,
                                now,
                                now,
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO despesas (
                                id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                                obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                                parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                                id_subcategoria, data_efetivacao, contabilizar, considerar_estatistica,
                                somar_total, data_update, ultima_modificacao
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 30, 0, ?, ?, ?, ?, 'S', 'S', 'S', ?, ?)
                            """,
                            (
                                new_item_id,
                                str(occ.id_profile),
                                new_desc,
                                new_val,
                                REC_UNICA,
                                new_due.isoformat(),
                                to_db_date(new_evt),
                                "pg" if (new_eff and not target_card) else "pd",
                                new_obs,
                                now,
                                target_account if not target_card else None,
                                new_item_id,
                                target_card,
                                single_cat.id_categoria if single_cat else None,
                                single_cat.id_subcategoria if single_cat else None,
                                to_db_date(new_eff_date) if (new_eff and not target_card) else None,
                                now,
                                now,
                            ),
                        )
                        if norm_splits:
                            self._write_splits(cur, new_item_id, norm_splits, new_val, new_due)
                    inherited_tags = tag_ids if tag_ids is not None else [t[0] for t in occ.tags]
                    for tid in inherited_tags:
                        cur.execute(
                            "INSERT INTO tags_transacoes (id_transacao, tipo_transacao, id_tag, id_transacao_origem) VALUES (?, ?, ?, ?)",
                            (new_item_id, target_kind, str(tid), new_item_id),
                        )
                    converted_tx_ids.append(new_item_id)

            # B) PARCELADA
            elif occ.num_parcelas > 1 and scope == "all":
                src_table = _TABLES[old_kind]
                rows = cur.execute(
                    f"""
                    SELECT id, num_parcela, num_parcelas, data, data_evento, valor, obs, id_conta
                    FROM {src_table}
                    WHERE COALESCE(NULLIF(id_origem, ''), id) = ?
                    ORDER BY num_parcela
                    """,
                    (occ.origin_id,),
                ).fetchall()

                for r in rows:
                    rid = str(r[0])
                    r_num_parc = int(r[1] or 1)
                    r_tot_parcs = int(r[2] or occ.num_parcelas)
                    is_current = rid == occ.id
                    r_val = new_val if is_current else float(r[5] or 0.0)
                    r_date = new_due if is_current else (parse_date(r[3]) or new_due)
                    r_evt = new_evt if is_current else (parse_date(r[4]) or r_date)
                    r_obs = new_obs if is_current else (r[6] or "")

                    if old_kind == KIND_DESPESA:
                        cur.execute("DELETE FROM despesas_cat_valor WHERE id_despesa = ?", (rid,))
                        cur.execute("DELETE FROM despesas WHERE id = ?", (rid,))
                    else:
                        cur.execute("DELETE FROM receitas WHERE id = ?", (rid,))

                    if target_kind == KIND_RECEITA:
                        cur.execute(
                            """
                            INSERT INTO receitas (
                                id, id_profile, descricao, valor, recorrencia, data, data_evento, efetivado,
                                obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas, intervalo,
                                id_categoria, id_subcategoria, data_efetivacao, somar_total,
                                considerar_estatistica, data_update, ultima_modificacao
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 30, ?, ?, ?, 'S', 'S', ?, ?)
                            """,
                            (
                                rid,
                                str(occ.id_profile),
                                new_desc,
                                r_val,
                                REC_PARCELADA,
                                r_date.isoformat(),
                                to_db_date(r_evt),
                                "S" if (new_eff if is_current else False) else "N",
                                r_obs,
                                now,
                                target_account,
                                occ.origin_id,
                                r_num_parc,
                                r_tot_parcs,
                                id_categoria,
                                id_subcategoria,
                                to_db_date(new_eff_date) if (is_current and new_eff) else None,
                                now,
                                now,
                            ),
                        )
                    else:
                        r_norm_splits = self._normalize_splits(
                            occ.id_profile, splits if is_current else None, id_categoria, id_subcategoria, r_val
                        )
                        r_single = r_norm_splits[0] if len(r_norm_splits) == 1 else None
                        cur.execute(
                            """
                            INSERT INTO despesas (
                                id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                                obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                                parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                                id_subcategoria, data_efetivacao, contabilizar, considerar_estatistica,
                                somar_total, data_update, ultima_modificacao
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 30, 0, ?, ?, ?, ?, 'S', 'S', 'S', ?, ?)
                            """,
                            (
                                rid,
                                str(occ.id_profile),
                                new_desc,
                                r_val,
                                REC_PARCELADA,
                                r_date.isoformat(),
                                to_db_date(r_evt),
                                "pg" if (is_current and new_eff and not target_card) else "pd",
                                r_obs,
                                now,
                                target_account if not target_card else None,
                                occ.origin_id,
                                r_num_parc,
                                r_tot_parcs,
                                target_card,
                                r_single.id_categoria if r_single else None,
                                r_single.id_subcategoria if r_single else None,
                                to_db_date(new_eff_date) if (is_current and new_eff and not target_card) else None,
                                now,
                                now,
                            ),
                        )
                        self._write_splits(cur, rid, r_norm_splits, r_val, r_date)

                    cur.execute(
                        "UPDATE tags_transacoes SET tipo_transacao = ? WHERE id_transacao = ?",
                        (target_kind, rid),
                    )
                    converted_tx_ids.append(rid)

            # C) ÚNICA OU PARCELA AVULSA (scope == "this")
            else:
                if old_kind == KIND_DESPESA:
                    cur.execute("DELETE FROM despesas_cat_valor WHERE id_despesa = ?", (occ.id,))
                    cur.execute("DELETE FROM despesas WHERE id = ?", (occ.id,))
                else:
                    cur.execute("DELETE FROM receitas WHERE id = ?", (occ.id,))

                if target_kind == KIND_RECEITA:
                    cur.execute(
                        """
                        INSERT INTO receitas (
                            id, id_profile, descricao, valor, recorrencia, data, data_evento, efetivado,
                            obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas, intervalo,
                            id_categoria, id_subcategoria, data_efetivacao, somar_total,
                            considerar_estatistica, data_update, ultima_modificacao
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 30, ?, ?, ?, 'S', 'S', ?, ?)
                        """,
                        (
                            occ.id,
                            str(occ.id_profile),
                            new_desc,
                            new_val,
                            REC_UNICA,
                            new_due.isoformat(),
                            to_db_date(new_evt),
                            "S" if new_eff else "N",
                            new_obs,
                            now,
                            target_account,
                            occ.id,
                            id_categoria,
                            id_subcategoria,
                            to_db_date(new_eff_date) if new_eff else None,
                            now,
                            now,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO despesas (
                            id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                            obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                            parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                            id_subcategoria, data_efetivacao, contabilizar, considerar_estatistica,
                            somar_total, data_update, ultima_modificacao
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 30, 0, ?, ?, ?, ?, 'S', 'S', 'S', ?, ?)
                        """,
                        (
                            occ.id,
                            str(occ.id_profile),
                            new_desc,
                            new_val,
                            REC_UNICA,
                            new_due.isoformat(),
                            to_db_date(new_evt),
                            "pg" if (new_eff and not target_card) else "pd",
                            new_obs,
                            now,
                            target_account if not target_card else None,
                            occ.id,
                            target_card,
                            single_cat.id_categoria if single_cat else None,
                            single_cat.id_subcategoria if single_cat else None,
                            to_db_date(new_eff_date) if (new_eff and not target_card) else None,
                            now,
                            now,
                        ),
                    )
                    if norm_splits:
                        self._write_splits(cur, occ.id, norm_splits, new_val, new_due)

                cur.execute(
                    "UPDATE tags_transacoes SET tipo_transacao = ? WHERE id_transacao = ?",
                    (target_kind, occ.id),
                )
                converted_tx_ids.append(occ.id)

            for cid in converted_tx_ids:
                cur.execute(
                    "UPDATE import_fingerprints SET kind = ? WHERE id_transacao = ?",
                    (target_kind.lower(), cid),
                )

        if tag_ids is not None:
            for cid in converted_tx_ids:
                self._set_tags(cid, target_kind, tag_ids)

    def update_occurrence(
        self,
        occ: Occurrence,
        *,
        scope: str = "this",
        new_kind: Optional[str] = None,
        descricao: Optional[str] = None,
        valor: Optional[float] = None,
        data_vencimento: Optional[date] = None,
        data_evento: Optional[date] = None,
        id_conta: Optional[str] = None,
        id_cartao: Optional[str] = None,
        id_conta_destino: Optional[str] = None,
        id_categoria: Optional[str] = None,
        id_subcategoria: Optional[str] = None,
        splits: Optional[List[SplitDTO]] = None,
        obs: Optional[str] = None,
        efetivada: Optional[bool] = None,
        data_efetivacao: Optional[date] = None,
        tag_ids: Optional[List[str]] = None,
        recorrencia: Optional[str] = None,
    ) -> None:
        """
        Edita uma ocorrência.
        - Conversão de Tipo (Despesa <-> Receita): migra as linhas de tabela atomicamente.
        - Únicas: atualiza a própria linha.
        - Parceladas: scope='this' altera apenas a parcela; scope='all' replica descrição,
          conta, categoria/rateio e observações para todas as parcelas (valor/data só na atual).
        - Fixas: scope='this' grava exceção do mês (valor, conta, status); scope='all'
          altera a série (descrição, valor base, conta, categoria, dia de vencimento).
        """
        if new_kind is not None and new_kind.upper() != occ.kind.upper():
            self._convert_occurrence_kind(
                occ,
                new_kind=new_kind.upper(),
                scope=scope,
                descricao=descricao,
                valor=valor,
                data_vencimento=data_vencimento,
                data_evento=data_evento,
                id_conta=id_conta,
                id_cartao=id_cartao,
                id_categoria=id_categoria,
                id_subcategoria=id_subcategoria,
                splits=splits,
                obs=obs,
                efetivada=efetivada,
                data_efetivacao=data_efetivacao,
                tag_ids=tag_ids,
            )
            return

        table = _TABLES[occ.kind]
        now = _now_str()
        new_desc = (descricao if descricao is not None else occ.descricao).strip()
        new_val = occ.valor if valor is None else round(float(valor), 2)
        new_obs = occ.obs if obs is None else obs
        new_eff = occ.efetivada if efetivada is None else efetivada
        norm_splits: Optional[List[SplitDTO]] = None
        if occ.kind == KIND_DESPESA and (splits is not None or id_categoria is not None):
            norm_splits = self._normalize_splits(
                occ.id_profile, splits, id_categoria, id_subcategoria, new_val
            )
        if occ.kind == KIND_RECEITA and id_categoria and not id_subcategoria:
            id_subcategoria = self.default_subcategory(KIND_RECEITA, id_categoria)

        with self.db.transaction() as cur:
            if occ.is_fixed:
                fix_table, fk = _FIXED_TABLES[occ.kind]
                if recorrencia == REC_UNICA:
                    # Converte de Fixa Recorrente para Única (à vista)
                    cur.execute(f"DELETE FROM {fix_table} WHERE {fk} = ?", (occ.id,))
                    cur.execute(
                        f"UPDATE {table} SET recorrencia = 'U', data = ?, ultima_modificacao = ? WHERE id = ?",
                        (to_db_date(data_vencimento or occ.data_vencimento), now, occ.id),
                    )

                if scope == "all":
                    sets = ["descricao = ?", "obs = ?", "ultima_modificacao = ?"]
                    params: list = [new_desc, new_obs, now]
                    if valor is not None:
                        sets.append("valor = ?")
                        params.append(new_val)
                    if data_vencimento is not None and recorrencia != REC_UNICA:
                        sets.append(
                            "data = date(data, 'start of month', '+' || (? - 1) || ' days')"
                        )
                        params.append(data_vencimento.day)
                    if occ.kind == KIND_TRANSFERENCIA:
                        if id_conta:
                            sets.append("id_conta_origem = ?")
                            params.append(id_conta)
                        if id_conta_destino:
                            sets.append("id_conta_destino = ?")
                            params.append(id_conta_destino)
                    elif occ.kind == KIND_DESPESA:
                        if id_cartao:
                            sets.append("id_cartao_credito = ?, id_conta = NULL")
                            params.append(id_cartao)
                        elif id_conta:
                            sets.append("id_conta = ?, id_cartao_credito = NULL")
                            params.append(id_conta)
                    elif id_conta:
                        sets.append("id_conta = ?")
                        params.append(id_conta)
                    if occ.kind != KIND_TRANSFERENCIA and id_categoria is not None:
                        single = norm_splits[0] if norm_splits and len(norm_splits) == 1 else None
                        sets.append("id_categoria = ?")
                        sets.append("id_subcategoria = ?")
                        if occ.kind == KIND_DESPESA:
                            params.extend([single.id_categoria if single else None, single.id_subcategoria if single else None])
                        else:
                            params.extend([id_categoria, id_subcategoria])
                    params.append(occ.id)
                    cur.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", params)
                    if norm_splits is not None:
                        base_date = parse_date(
                            cur.execute(f"SELECT data FROM {table} WHERE id = ?", (occ.id,)).fetchone()[0]
                        ) or occ.data_vencimento
                        self._write_splits(cur, occ.id, norm_splits, new_val, base_date)
                    # Remove sobrescritas de valor/conta futuras para a série refletir a edição
                    fix_table, fk = _FIXED_TABLES[occ.kind]
                    if valor is not None or id_conta or id_cartao:
                        cur.execute(
                            f"DELETE FROM {fix_table} WHERE {fk} = ? AND date(data, 'start of month') >= date(?) "
                            "AND COALESCE(excluido_mes, 'N') != 'S'",
                            (occ.id, date(occ.occ_year, occ.occ_month, 1).isoformat()),
                        )
                    if efetivada is not None and efetivada:
                        refreshed = Occurrence(**{**vars(occ), "valor": new_val, "descricao": new_desc})
                        self._write_fixed_override(
                            cur, refreshed, valor=new_val, efetivada=True,
                            data_efetivacao=data_efetivacao or occ.data_vencimento,
                            id_conta=id_conta, id_conta_destino=id_conta_destino,
                        )
                else:
                    if new_desc != occ.descricao or id_categoria is not None:
                        f_sets = ["descricao = ?", "ultima_modificacao = ?"]
                        f_params: list = [new_desc, now]
                        if occ.kind != KIND_TRANSFERENCIA and id_categoria is not None:
                            single = norm_splits[0] if norm_splits and len(norm_splits) == 1 else None
                            f_sets.extend(["id_categoria = ?", "id_subcategoria = ?"])
                            if occ.kind == KIND_DESPESA:
                                f_params.extend([single.id_categoria if single else None, single.id_subcategoria if single else None])
                            else:
                                f_params.extend([id_categoria, id_subcategoria])
                        f_params.append(occ.id)
                        cur.execute(f"UPDATE {table} SET {', '.join(f_sets)} WHERE id = ?", f_params)
                        if occ.kind == KIND_DESPESA and norm_splits is not None:
                            base_date = parse_date(
                                cur.execute(f"SELECT data FROM {table} WHERE id = ?", (occ.id,)).fetchone()[0]
                            ) or occ.data_vencimento
                            self._write_splits(cur, occ.id, norm_splits, new_val, base_date)
                    self._write_fixed_override(
                        cur,
                        occ,
                        valor=new_val,
                        efetivada=new_eff,
                        data_efetivacao=data_efetivacao or (occ.data_efetivacao or occ.data_vencimento),
                        id_conta=id_conta,
                        id_conta_destino=id_conta_destino,
                    )
            else:
                target_ids = [occ.id]
                if occ.num_parcelas > 1 and scope == "all":
                    target_ids = [
                        str(r[0])
                        for r in cur.execute(
                            f"SELECT id FROM {table} WHERE COALESCE(NULLIF(id_origem, ''), id) = ?",
                            (occ.origin_id,),
                        ).fetchall()
                    ]
                    if not target_ids:
                        target_ids = [occ.id]
                value_changed = valor is not None and abs(new_val - occ.valor) > 0.001
                for rid in target_ids:
                    is_current = rid == occ.id
                    sets = ["descricao = ?", "obs = ?", "ultima_modificacao = ?", "data_update = ?"]
                    params = [new_desc, new_obs, now, now]
                    if occ.kind == KIND_TRANSFERENCIA:
                        if id_conta:
                            sets.append("id_conta_origem = ?")
                            params.append(id_conta)
                        if id_conta_destino:
                            sets.append("id_conta_destino = ?")
                            params.append(id_conta_destino)
                    elif occ.kind == KIND_DESPESA:
                        if id_cartao:
                            sets.append("id_cartao_credito = ?, id_conta = NULL")
                            params.append(id_cartao)
                        elif id_conta:
                            sets.append("id_conta = ?, id_cartao_credito = NULL")
                            params.append(id_conta)
                    elif id_conta:
                        sets.append("id_conta = ?")
                        params.append(id_conta)
                    if occ.kind == KIND_RECEITA and id_categoria is not None:
                        sets.extend(["id_categoria = ?", "id_subcategoria = ?"])
                        params.extend([id_categoria, id_subcategoria])
                    if occ.kind == KIND_DESPESA and norm_splits is not None:
                        single = norm_splits[0] if len(norm_splits) == 1 else None
                        sets.extend(["id_categoria = ?", "id_subcategoria = ?"])
                        params.extend([single.id_categoria if single else None, single.id_subcategoria if single else None])
                    if is_current or (scope == "all" and value_changed):
                        sets.append("valor = ?")
                        params.append(new_val)
                    if occ.num_parcelas <= 1 and recorrencia:
                        if recorrencia in FIXED_CODES[occ.kind] or recorrencia == "M":
                            sets.append("recorrencia = ?")
                            params.append(fixed_code_for(occ.kind))
                            sets.append("id_origem = ?")
                            params.append(rid)
                        elif recorrencia == REC_UNICA:
                            sets.append("recorrencia = 'U'")
                    if data_evento is not None and occ.kind != KIND_TRANSFERENCIA:
                        if is_current or (scope == "all" and data_evento != occ.data_evento):
                            sets.append("data_evento = ?")
                            params.append(data_evento.isoformat())
                    if is_current:
                        is_card_tx = bool(id_cartao or (occ.is_card and not id_conta))
                        if is_card_tx:
                            if data_vencimento is not None and data_vencimento != occ.data_vencimento:
                                sets.append("data = ?")
                                params.append(data_vencimento.isoformat())
                            elif (
                                occ.num_parcelas <= 1
                                and data_evento is not None
                                and data_evento != occ.data_evento
                            ):
                                from app.domain.services.credit_card_service import CreditCardService

                                eff_card_id = str(id_cartao or occ.id_cartao or "")
                                card_obj = CreditCardService(self.db, self).get_card(eff_card_id)
                                if card_obj is not None:
                                    new_due = CreditCardService.compute_due_date(card_obj, data_evento)
                                    sets.append("data = ?")
                                    params.append(new_due.isoformat())
                        elif data_vencimento is not None:
                            sets.append("data = ?")
                            params.append(data_vencimento.isoformat())
                        efet_date = (data_efetivacao or occ.data_efetivacao or (data_vencimento or occ.data_vencimento)) if new_eff else None
                        if occ.kind == KIND_DESPESA:
                            sets.append("status = ?")
                            params.append("pg" if new_eff else "pd")
                        elif occ.kind == KIND_RECEITA:
                            sets.append("efetivado = ?")
                            params.append("S" if new_eff else "N")
                        else:
                            sets.append("contabilizada = ?")
                            params.append("S" if new_eff else "N")
                        sets.append("data_efetivacao = ?")
                        params.append(to_db_date(efet_date))
                    params.append(rid)
                    cur.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?", params)

                    if occ.kind == KIND_DESPESA and (
                        norm_splits is not None
                        or ((is_current or (scope == "all" and value_changed)) and valor is not None)
                    ):
                        row = cur.execute("SELECT valor, data FROM despesas WHERE id = ?", (rid,)).fetchone()
                        row_val = float(row[0] or 0.0)
                        row_date = parse_date(row[1]) or occ.data_vencimento
                        use_splits = norm_splits if norm_splits is not None else self._load_splits(rid)
                        self._write_splits(cur, rid, use_splits, row_val, row_date)
        if tag_ids is not None:
            self.set_tags_for(occ, tag_ids)

    # ------------------------------------------------------------------ #
    # Totais consolidados
    # ------------------------------------------------------------------ #
    @staticmethod
    def summarize(
        occs: List[Occurrence], *, include_non_accountable: bool = False
    ) -> Dict[str, float]:
        has_card_items = any(o.is_card for o in occs)

        def _is_dup_inv_pay(o: Occurrence) -> bool:
            return has_card_items and "[Pagamento Fatura:" in (o.obs or "")

        rec_ef = sum(
            o.total
            for o in occs
            if o.kind == KIND_RECEITA
            and o.efetivada
            and (include_non_accountable or o.contabilizar)
        )
        rec_pd = sum(
            o.total
            for o in occs
            if o.kind == KIND_RECEITA
            and not o.efetivada
            and (include_non_accountable or o.contabilizar)
        )
        desp_ef = sum(
            o.total
            for o in occs
            if o.kind == KIND_DESPESA
            and o.efetivada
            and not _is_dup_inv_pay(o)
            and (include_non_accountable or o.contabilizar)
        )
        desp_pd = sum(
            o.total
            for o in occs
            if o.kind == KIND_DESPESA
            and not o.efetivada
            and not _is_dup_inv_pay(o)
            and (include_non_accountable or o.contabilizar)
        )
        terc_desp = sum(
            o.total
            for o in occs
            if o.kind == KIND_DESPESA and not o.contabilizar
        )
        transf = sum(o.total for o in occs if o.kind == KIND_TRANSFERENCIA)
        return {
            "receitas": round(rec_ef + rec_pd, 2),
            "receitas_efetivadas": round(rec_ef, 2),
            "receitas_pendentes": round(rec_pd, 2),
            "despesas": round(desp_ef + desp_pd, 2),
            "despesas_pagas": round(desp_ef, 2),
            "despesas_pendentes": round(desp_pd, 2),
            "terceiros_despesas": round(terc_desp, 2),
            "transferencias": round(transf, 2),
            "resultado": round((rec_ef + rec_pd) - (desp_ef + desp_pd), 2),
            "resultado_confirmado": round(rec_ef - desp_ef, 2),
        }
