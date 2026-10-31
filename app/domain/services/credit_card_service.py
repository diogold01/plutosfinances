"""
Serviço de Cartões de Crédito e Faturas Mensais (`cartoes_credito` e `cartoes_credito_mes`).

Regras de negócio implementadas:
- Cálculo automático do mês/ano de vencimento da fatura a partir da data da compra (`data_evento`),
  do dia de fechamento (`dia_fecha`) e do dia de vencimento (`dia_venc`).
- Ciclo mensal da fatura (`cartoes_credito_mes`): permite sobrescrever limite, conta de débito,
  dia de fechamento e dia de vencimento naquele mês e registra `fatura_paga = 'S'/'N'`.
- Cálculo do limite total, limite comprometido (despesas de cartão não pagas em faturas abertas/futuras)
  e limite disponível.
- Pagamento total de fatura (marca todas as despesas da fatura como pagas e `fatura_paga = 'S'`),
  reabertura de fatura, adiantamento de fatura (`adiantamento_fatura = 'S'`) e estorno de compra
  no cartão (`id_despesa_estornada`).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from app.config.theme_palette import argb_int_to_hex, hex_to_argb_int
from app.database.connection_manager import ConnectionManager
from app.domain.date_utils import add_months, clamp_day, parse_date, to_db_date
from app.domain.models import (
    FIXED_CODES,
    KIND_DESPESA,
    REC_UNICA,
    CardDTO,
    InvoiceDTO,
    Occurrence,
)
from app.domain.services.transaction_service import (
    TransactionService,
    _chunks,
    _is_effective_value,
)

CARD_BRANDS: List[Tuple[str, str, str]] = [
    ("master", "Mastercard", "ic_master_card.png"),
    ("visa", "Visa", "ic_visa.png"),
    ("elo", "Elo", "ic_card_elo.png"),
    ("amex", "American Express", "ic_credit_amex.png"),
    ("dinners", "Diners Club", "ic_card_diners_club.png"),
    ("other", "Outra Bandeira", "ic_credit_card.png"),
]

_BRAND_TO_IMG_ID = {
    "master": 2,
    "visa": 1,
    "elo": 3,
    "amex": 4,
    "dinners": 5,
    "other": 0,
}
_IMG_ID_TO_BRAND = {v: k for k, v in _BRAND_TO_IMG_ID.items()}


def detect_brand_key(nome: str, explicit_key: str = "") -> str:
    """Identifica a chave da bandeira a partir de chave explícita ou heurística pelo nome do cartão."""
    candidate = explicit_key.lower().strip() if explicit_key else ""
    if candidate in _BRAND_TO_IMG_ID and candidate != "other":
        return candidate
    low = (nome or "").lower()
    if "master" in low or "nubank" in low:
        return "master"
    if "visa" in low:
        return "visa"
    if "elo" in low:
        return "elo"
    if "amex" in low or "american" in low:
        return "amex"
    if "diners" in low or "dinners" in low:
        return "dinners"
    return candidate if candidate in _BRAND_TO_IMG_ID else "other"


def brand_icon_filename(brand_key: str) -> str:
    key = (brand_key or "other").lower()
    for b_key, _label, fname in CARD_BRANDS:
        if b_key == key:
            return fname
    return "ic_credit_card.png"


class CreditCardService:
    """Serviço de domínio para gestão de cartões de crédito e faturas mensais."""

    def __init__(
        self,
        db: ConnectionManager,
        tx_service: Optional[TransactionService] = None,
    ) -> None:
        self.db = db
        self.tx_service = tx_service or TransactionService(db)

    # ------------------------------------------------------------------ #
    # CRUD de Cartões (`cartoes_credito`)
    # ------------------------------------------------------------------ #
    def list_cards(
        self, profile_id: str = "1", include_archived: bool = False
    ) -> List[CardDTO]:
        where_arch = (
            ""
            if include_archived
            else "AND (cc.data_exclusao IS NULL OR cc.data_exclusao = '')"
        )
        rows = self.db.execute_query(
            f"""
            SELECT cc.id, cc.id_profile, cc.nome, COALESCE(cc.limite, 0) AS limite,
                   COALESCE(cc.dia_fecha, 1) AS dia_fecha,
                   COALESCE(cc.dia_venc, 10) AS dia_venc,
                   cc.id_conta, COALESCE(ct.descricao, '') AS conta_nome,
                   COALESCE(cc.cor, -14575885) AS cor,
                   COALESCE(cc.img_id, 1) AS img_id,
                   COALESCE(cc.tipo, '') AS tipo,
                   COALESCE(cc.padrao, 'N') AS padrao,
                   cc.data_exclusao
            FROM cartoes_credito cc
            LEFT JOIN contas ct ON ct.id = cc.id_conta
            WHERE COALESCE(cc.id_profile, '1') = ? {where_arch}
            ORDER BY COALESCE(cc.sequence, 0) ASC, cc.nome COLLATE NOCASE ASC
            """,
            (str(profile_id),),
        )
        result: List[CardDTO] = []
        for r in rows:
            result.append(self._row_to_card(r))
        return result

    def get_card(self, card_id: str) -> Optional[CardDTO]:
        rows = self.db.execute_query(
            """
            SELECT cc.id, cc.id_profile, cc.nome, COALESCE(cc.limite, 0) AS limite,
                   COALESCE(cc.dia_fecha, 1) AS dia_fecha,
                   COALESCE(cc.dia_venc, 10) AS dia_venc,
                   cc.id_conta, COALESCE(ct.descricao, '') AS conta_nome,
                   COALESCE(cc.cor, -14575885) AS cor,
                   COALESCE(cc.img_id, 1) AS img_id,
                   COALESCE(cc.tipo, '') AS tipo,
                   COALESCE(cc.padrao, 'N') AS padrao,
                   cc.data_exclusao
            FROM cartoes_credito cc
            LEFT JOIN contas ct ON ct.id = cc.id_conta
            WHERE cc.id = ?
            """,
            (str(card_id),),
        )
        if not rows:
            return None
        return self._row_to_card(rows[0])

    def _row_to_card(self, r: object) -> CardDTO:
        color_int = int(r["cor"] if r["cor"] is not None else -14575885)
        tipo_raw = str(r["tipo"] or "").strip().lower()
        img_id = int(r["img_id"] or 0)
        nome = str(r["nome"] or "Cartão")
        if tipo_raw in _BRAND_TO_IMG_ID and tipo_raw != "other":
            brand_key = tipo_raw
        elif img_id in _IMG_ID_TO_BRAND and _IMG_ID_TO_BRAND[img_id] != "other":
            brand_key = _IMG_ID_TO_BRAND[img_id]
        else:
            brand_key = detect_brand_key(nome, explicit_key=tipo_raw)
        return CardDTO(
            id=str(r["id"]),
            id_profile=str(r["id_profile"] or "1"),
            nome=nome,
            limite=round(float(r["limite"] or 0.0), 2),
            dia_fecha=max(1, min(31, int(r["dia_fecha"] or 1))),
            dia_venc=max(1, min(31, int(r["dia_venc"] or 10))),
            id_conta=str(r["id_conta"]) if r["id_conta"] else None,
            conta_nome=str(r["conta_nome"] or ""),
            color_int=color_int,
            color_hex=argb_int_to_hex(color_int),
            brand_key=brand_key,
            padrao="S" if str(r["padrao"] or "N").upper() == "S" else "N",
            archived=bool(r["data_exclusao"]),
        )

    def create_card(
        self,
        *,
        nome: str,
        limite: float,
        dia_fecha: int,
        dia_venc: int,
        id_conta: Optional[str] = None,
        profile_id: str = "1",
        color_hex: str = "#1E88E5",
        brand_key: str = "",
        padrao: bool = False,
    ) -> CardDTO:
        clean_name = nome.strip()
        if not clean_name:
            raise ValueError("O nome do cartão não pode estar vazio.")
        dia_f = max(1, min(31, int(dia_fecha)))
        dia_v = max(1, min(31, int(dia_venc)))
        card_id = uuid.uuid4().hex[:16]
        color_int = hex_to_argb_int(color_hex)
        b_key = detect_brand_key(clean_name, brand_key)
        img_id = _BRAND_TO_IMG_ID.get(b_key, 0)

        with self.db.transaction() as cur:
            if padrao:
                cur.execute(
                    "UPDATE cartoes_credito SET padrao = 'N' WHERE COALESCE(id_profile, '1') = ?",
                    (str(profile_id),),
                )
            cur.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM cartoes_credito WHERE COALESCE(id_profile, '1') = ?",
                (str(profile_id),),
            )
            seq = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO cartoes_credito (
                    id, id_profile, nome, cor, img_id, limite, id_conta,
                    dia_venc, dia_fecha, conta_vinculada, padrao, tipo, sequence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    str(profile_id),
                    clean_name,
                    color_int,
                    img_id,
                    round(float(limite), 2),
                    id_conta,
                    dia_v,
                    dia_f,
                    "S" if id_conta else "N",
                    "S" if padrao else "N",
                    b_key,
                    seq,
                ),
            )
        card = self.get_card(card_id)
        assert card is not None
        return card

    def update_card(
        self,
        card_id: str,
        *,
        nome: str,
        limite: float,
        dia_fecha: int,
        dia_venc: int,
        id_conta: Optional[str] = None,
        color_hex: str = "#1E88E5",
        brand_key: str = "visa",
        padrao: bool = False,
    ) -> None:
        clean_name = nome.strip()
        if not clean_name:
            raise ValueError("O nome do cartão não pode estar vazio.")
        card = self.get_card(card_id)
        if card is None:
            raise ValueError("Cartão de crédito não encontrado.")
        dia_f = max(1, min(31, int(dia_fecha)))
        dia_v = max(1, min(31, int(dia_venc)))
        color_int = hex_to_argb_int(color_hex)
        b_key = detect_brand_key(clean_name, brand_key)
        img_id = _BRAND_TO_IMG_ID.get(b_key, 0)

        with self.db.transaction() as cur:
            if padrao:
                cur.execute(
                    "UPDATE cartoes_credito SET padrao = 'N' WHERE COALESCE(id_profile, '1') = ?",
                    (card.id_profile,),
                )
            cur.execute(
                """
                UPDATE cartoes_credito
                SET nome = ?, cor = ?, img_id = ?, limite = ?, id_conta = ?,
                    dia_venc = ?, dia_fecha = ?, conta_vinculada = ?, padrao = ?, tipo = ?
                WHERE id = ?
                """,
                (
                    clean_name,
                    color_int,
                    img_id,
                    round(float(limite), 2),
                    id_conta,
                    dia_v,
                    dia_f,
                    "S" if id_conta else "N",
                    "S" if padrao else "N",
                    b_key,
                    str(card_id),
                ),
            )
            if dia_v != card.dia_venc:
                cur.execute(
                    "SELECT id, data FROM despesas WHERE id_cartao_credito = ? AND LOWER(COALESCE(status, 'pd')) NOT IN ('pg', 'e', 's')",
                    (str(card_id),),
                )
                for r_id, r_data in cur.fetchall():
                    if r_data and len(r_data) >= 10:
                        try:
                            parts = r_data.split("-")
                            yr, mo = int(parts[0]), int(parts[1])
                            new_d = f"{yr:04d}-{mo:02d}-{clamp_day(yr, mo, dia_v):02d}"
                            cur.execute("UPDATE despesas SET data = ? WHERE id = ?", (new_d, r_id))
                        except Exception:
                            pass

    def archive_card(self, card_id: str, archived: bool = True) -> None:
        val = datetime.now().strftime("%Y-%m-%d") if archived else None
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE cartoes_credito SET data_exclusao = ? WHERE id = ?",
                (val, str(card_id)),
            )

    def delete_card(self, card_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "DELETE FROM cartoes_credito_mes WHERE id_cartao = ?",
                (str(card_id),),
            )
            cur.execute(
                "DELETE FROM despesas WHERE id_cartao_credito = ?",
                (str(card_id),),
            )
            cur.execute(
                "DELETE FROM cartoes_credito WHERE id = ?",
                (str(card_id),),
            )

    # ------------------------------------------------------------------ #
    # Cálculo de Fechamento e Vencimento de Faturas
    # ------------------------------------------------------------------ #
    @staticmethod
    def compute_closing_date(card: CardDTO, year: int, month: int) -> date:
        """
        Retorna a data de fechamento da fatura de competência (year, month).
        O fechamento ocorre no próprio mês (year, month) no dia 'card.dia_fecha'.
        """
        return date(year, month, clamp_day(year, month, card.dia_fecha))

    @staticmethod
    def compute_due_date_for_invoice(card: CardDTO, year: int, month: int) -> date:
        """
        Retorna a data de vencimento (pagamento) da fatura do mês (year, month).
        - Quando dia_fecha >= dia_venc: o pagamento vence no mês SEGUINTE ao fechamento.
        - Quando dia_fecha < dia_venc: o pagamento vence no PRÓPRIO mês do fechamento.
        """
        if card.dia_fecha >= card.dia_venc:
            nxt = add_months(date(year, month, 1), 1)
            return date(
                nxt.year, nxt.month, clamp_day(nxt.year, nxt.month, card.dia_venc)
            )
        return date(year, month, clamp_day(year, month, card.dia_venc))

    @classmethod
    def compute_due_date(cls, card: CardDTO, purchase_date: date) -> date:
        """
        Calcula a data de vencimento da fatura para uma compra realizada em 'purchase_date'.
        - Se purchase_date.day < card.dia_fecha: pertence à fatura deste mês (purchase_date.year, purchase_date.month).
        - Se purchase_date.day >= card.dia_fecha: pertence à fatura do mês seguinte (add_months(1)),
          pois no dia do fechamento ('melhor dia de compra') a fatura anterior já está fechada.
        """
        if purchase_date.day < card.dia_fecha:
            inv_date = date(purchase_date.year, purchase_date.month, 1)
        else:
            inv_date = add_months(date(purchase_date.year, purchase_date.month, 1), 1)
        return cls.compute_due_date_for_invoice(card, inv_date.year, inv_date.month)

    def _list_invoice_items(self, card: CardDTO, due_date: date) -> List[Occurrence]:
        """Carrega todas as ocorrências de compras vinculadas à fatura pelo seu vencimento exato (não-fixas + fixas recorrentes)."""
        cat_cols, cat_join = self.tx_service._category_sql(KIND_DESPESA)
        due_str = to_db_date(due_date)
        fix_codes = list(FIXED_CODES[KIND_DESPESA])
        ph = ",".join("?" * len(fix_codes))
        sql = (
            f"SELECT d.*, date(d.data) AS ref_dt {cat_cols} "
            f"FROM despesas d {cat_join} "
            f"WHERE d.id_cartao_credito = ? "
            f"  AND (d.data_exclusao IS NULL OR d.data_exclusao = '') "
            f"  AND COALESCE(d.recorrencia, 'U') NOT IN ({ph}) "
            f"  AND d.data = ? "
            f"ORDER BY d.data_evento, d.data, d.descricao"
        )
        rows = self.db.execute_query(sql, (str(card.id), *fix_codes, due_str))
        items: List[Occurrence] = []
        for r in rows:
            keys = set(r.keys())
            venc = parse_date(r["data"]) or due_date
            eff = _is_effective_value(KIND_DESPESA, r["status"])
            juros = float(r["juros"] or 0.0)
            items.append(
                self.tx_service._build_occurrence(
                    KIND_DESPESA,
                    r,
                    is_fixed=False,
                    year=due_date.year,
                    month=due_date.month,
                    valor=float(r["valor"] or 0.0),
                    juros=juros,
                    efetivada=eff,
                    venc=venc,
                    data_evento=parse_date(r["data_evento"]) if "data_evento" in keys else None,
                    data_efetivacao=parse_date(r["data_efetivacao"]) if "data_efetivacao" in keys else None,
                    ref_date=venc,
                    id_conta=str(r["id_conta"]) if r["id_conta"] else None,
                    id_conta_destino=None,
                    id_cartao=str(card.id),
                )
            )

        # Carrega despesas fixas recorrentes vinculadas ao cartão para este mês de fatura
        fixed_items = [
            o
            for o in self.tx_service._load_fixed(
                KIND_DESPESA,
                due_date.year,
                due_date.month,
                mode="vencimento",
                profile_id=card.id_profile,
            )
            if str(o.id_cartao or "") == str(card.id)
        ]
        for f in fixed_items:
            f.data_vencimento = due_date
            f.ref_date = due_date
            items.append(f)

        if items:
            self.tx_service._attach_splits(items)
            self.tx_service._attach_names(items)
            self.tx_service._attach_tags(items)
            items.sort(key=lambda o: (o.data_evento or o.data_vencimento, o.descricao.lower()))
        return items

    # ------------------------------------------------------------------ #
    # Fatura Mensal (`cartoes_credito_mes` + ocorrências de despesas)
    # ------------------------------------------------------------------ #
    def get_invoice(
        self,
        card_id: str,
        year: int,
        month: int,
        ref: Optional[date] = None,
    ) -> InvoiceDTO:
        card = self.get_card(card_id)
        if card is None:
            raise ValueError(f"Cartão '{card_id}' não encontrado.")

        mes_rows = self.db.execute_query(
            """
            SELECT limite, id_conta, dia_venc, dia_fecha, fatura_paga,
                   data_fecha_manual, data_venc_manual, status_manual
            FROM cartoes_credito_mes
            WHERE id_cartao = ? AND ano = ? AND mes = ?
            """,
            (str(card_id), int(year), int(month)),
        )
        limite_mes = card.limite
        id_conta_pag = card.id_conta
        dia_v = card.dia_venc
        dia_f = card.dia_fecha
        fatura_paga_flag = False
        manual_fecha: Optional[date] = None
        manual_venc: Optional[date] = None
        manual_status = ""

        if mes_rows:
            mr = mes_rows[0]
            if mr["limite"] is not None:
                limite_mes = float(mr["limite"])
            if mr["id_conta"]:
                id_conta_pag = str(mr["id_conta"])
            if mr["dia_venc"]:
                dia_v = int(mr["dia_venc"])
            if mr["dia_fecha"]:
                dia_f = int(mr["dia_fecha"])
            fatura_paga_flag = str(mr["fatura_paga"] or "N").upper() == "S"
            manual_fecha = parse_date(mr["data_fecha_manual"])
            manual_venc = parse_date(mr["data_venc_manual"])
            manual_status = str(mr["status_manual"] or "").strip()

        eff_card = CardDTO(
            **{
                **vars(card),
                "limite": limite_mes,
                "id_conta": id_conta_pag,
                "dia_venc": dia_v,
                "dia_fecha": dia_f,
            }
        )
        data_fecha = manual_fecha or self.compute_closing_date(eff_card, year, month)
        data_venc = manual_venc or self.compute_due_date_for_invoice(eff_card, year, month)

        items = self._list_invoice_items(eff_card, data_venc)
        total = round(sum(o.total for o in items), 2)
        all_items_paid = bool(items) and all(o.efetivada for o in items)
        paga = fatura_paga_flag or all_items_paid or manual_status == "Paga"

        today = ref or date.today()
        if manual_status in ("Aberta", "Fechada", "Paga"):
            status = manual_status
        elif paga:
            status = "Paga"
        elif today > data_venc and total > 0:
            status = "Vencida"
        elif today >= data_fecha:
            status = "Fechada"
        else:
            status = "Aberta"

        usado = self._compute_used_limit(
            card.id, year=int(year), month=int(month), profile_id=eff_card.id_profile
        )
        disponivel = round(limite_mes - usado, 2)

        return InvoiceDTO(
            card=eff_card,
            ano=int(year),
            mes=int(month),
            data_fechamento=data_fecha,
            data_vencimento=data_venc,
            limite=round(limite_mes, 2),
            items=items,
            total=total,
            paga=paga,
            status=status,
            id_conta_pagamento=id_conta_pag,
            usado=usado,
            disponivel=disponivel,
        )

    def _compute_used_limit(
        self,
        card_id: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
        profile_id: str = "1",
    ) -> float:
        """Soma todas as despesas de cartão não pagas (únicas, parcelas pendentes e fixas do mês)."""
        rows = self.db.execute_query(
            """
            SELECT COALESCE(SUM(COALESCE(valor, 0) + COALESCE(juros, 0)), 0) AS usado
            FROM despesas
            WHERE id_cartao_credito = ?
              AND (data_exclusao IS NULL OR data_exclusao = '')
              AND COALESCE(recorrencia, 'U') NOT IN ('F', 'M')
              AND LOWER(COALESCE(status, 'pd')) NOT IN ('pg', 'e', 's')
            """,
            (str(card_id),),
        )
        non_fixed = float(rows[0]["usado"] or 0.0) if rows else 0.0
        fixed_unpaid = 0.0
        if year is not None and month is not None:
            fixed_unpaid = sum(
                o.total
                for o in self.tx_service._load_fixed(
                    KIND_DESPESA, year, month, mode="vencimento", profile_id=profile_id
                )
                if str(o.id_cartao or "") == str(card_id) and not o.efetivada
            )
        return round(non_fixed + fixed_unpaid, 2)

    def list_cards_with_invoices(
        self,
        year: int,
        month: int,
        profile_id: str = "1",
        include_archived: bool = False,
    ) -> List[InvoiceDTO]:
        cards = self.list_cards(profile_id=profile_id, include_archived=include_archived)
        return [self.get_invoice(c.id, year, month) for c in cards]

    # ------------------------------------------------------------------ #
    # Pagamento, Reabertura, Adiantamento e Estorno de Fatura
    # ------------------------------------------------------------------ #
    @staticmethod
    def _invoice_payment_marker(card_id: str, year: int, month: int) -> str:
        return f"[Pagamento Fatura:{card_id}:{int(year):04d}-{int(month):02d}]"

    def _resolve_invoice_payment_category(
        self, profile_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
        cat_rows = self.db.execute_query(
            """
            SELECT id FROM despesas_cat
            WHERE id_profile = ? AND data_exclusao IS NULL
            ORDER BY CASE
                WHEN LOWER(nome) IN ('pagamentos', 'cartão de crédito', 'cartao de credito', 'fatura') THEN 0
                WHEN LOWER(nome) = 'outros' THEN 1
                ELSE 2
            END, nome
            LIMIT 1
            """,
            (str(profile_id),),
        )
        if cat_rows:
            c_id = str(cat_rows[0]["id"])
            return c_id, self.tx_service.default_subcategory(KIND_DESPESA, c_id)
        return self.tx_service.default_category(KIND_DESPESA, profile_id)

    def _remove_invoice_payment_expense(
        self, card_id: str, year: int, month: int
    ) -> int:
        """Remove (soft-delete) a despesa de quitação de fatura gerada na conta corrente."""
        marker = self._invoice_payment_marker(card_id, year, month)
        rows = self.db.execute_query(
            """
            SELECT id FROM despesas
            WHERE (data_exclusao IS NULL OR data_exclusao = '')
              AND COALESCE(id_cartao_credito, '') IN ('', '-1')
              AND obs LIKE ?
            """,
            (f"%{marker}%",),
        )
        if not rows:
            return 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction() as cur:
            for r in rows:
                rid = str(r["id"])
                cur.execute(
                    "UPDATE despesas SET data_exclusao = ?, ultima_modificacao = ? WHERE id = ?",
                    (now_str, now_str, rid),
                )
                cur.execute(
                    "UPDATE despesas_cat_valor SET excluido = 'S' WHERE id_despesa = ?",
                    (rid,),
                )
        return len(rows)

    def pay_invoice(
        self,
        card_id: str,
        year: int,
        month: int,
        *,
        id_conta: Optional[str] = None,
        data_pagamento: Optional[date] = None,
    ) -> int:
        """
        Marca todos os lançamentos da fatura `(year, month)` como pagos, registra
        `fatura_paga = 'S'` em `cartoes_credito_mes` e debita automaticamente o valor
        da fatura na conta corrente vinculada (criando lançamento em Transações).
        Retorna a quantidade de itens baixados.
        """
        invoice = self.get_invoice(card_id, year, month)
        pay_date = data_pagamento or invoice.data_vencimento
        target_account = id_conta or invoice.id_conta_pagamento or invoice.card.id_conta
        if not target_account:
            acc_rows = self.db.execute_query(
                """
                SELECT id FROM contas
                WHERE id_profile = ? AND data_exclusao IS NULL
                ORDER BY CASE WHEN UPPER(COALESCE(padrao, 'N')) = 'S' THEN 0 ELSE 1 END, sequence ASC
                LIMIT 1
                """,
                (str(invoice.card.id_profile),),
            )
            if acc_rows:
                target_account = str(acc_rows[0]["id"])

        count = 0
        for occ in invoice.items:
            if not occ.efetivada:
                self.tx_service.set_effective(
                    occ,
                    True,
                    data_efetivacao=pay_date,
                    id_conta=target_account,
                )
                count += 1

        # Remove eventual lançamento anterior desta mesma fatura e cria o débito na conta corrente
        self._remove_invoice_payment_expense(card_id, year, month)
        paid_amount = round(float(invoice.total), 2)
        if target_account and paid_amount > 0:
            cat_id, sub_id = self._resolve_invoice_payment_category(
                invoice.card.id_profile
            )
            marker = self._invoice_payment_marker(card_id, year, month)
            self.tx_service.create_expense(
                descricao=f"Pagamento Fatura {invoice.card.nome} - {int(month):02d}/{int(year):04d}",
                valor=paid_amount,
                data_vencimento=pay_date,
                data_evento=pay_date,
                data_efetivacao=pay_date,
                profile_id=invoice.card.id_profile,
                id_conta=target_account,
                id_cartao=None,
                id_categoria=cat_id,
                id_subcategoria=sub_id,
                recorrencia=REC_UNICA,
                pago=True,
                obs=f"{marker} Quitação da fatura {int(month):02d}/{int(year):04d} do cartão {invoice.card.nome}",
            )

        self._upsert_invoice_month(
            card=invoice.card,
            year=year,
            month=month,
            fatura_paga=True,
            id_conta=target_account,
        )
        return count

    def reopen_invoice(self, card_id: str, year: int, month: int) -> int:
        """
        Reabre uma fatura paga, voltando seus lançamentos para pendente (`pd`)
        e estornando/removendo o débito correspondente na conta corrente.
        """
        invoice = self.get_invoice(card_id, year, month)
        count = 0
        for occ in invoice.items:
            if occ.efetivada:
                self.tx_service.set_effective(occ, False)
                count += 1
        self._remove_invoice_payment_expense(card_id, year, month)
        self._upsert_invoice_month(
            card=invoice.card,
            year=year,
            month=month,
            fatura_paga=False,
            id_conta=invoice.id_conta_pagamento,
        )
        return count

    def _upsert_invoice_month(
        self,
        *,
        card: CardDTO,
        year: int,
        month: int,
        fatura_paga: bool,
        id_conta: Optional[str] = None,
    ) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT data_fecha_manual, data_venc_manual, status_manual
                FROM cartoes_credito_mes
                WHERE id_cartao = ? AND ano = ? AND mes = ?
                """,
                (card.id, int(year), int(month)),
            )
            prev = cur.fetchone()
            keep_fecha = prev[0] if prev else None
            keep_venc = prev[1] if prev else None
            keep_status = prev[2] if prev else None
            cur.execute(
                """
                DELETE FROM cartoes_credito_mes
                WHERE id_cartao = ? AND ano = ? AND mes = ?
                """,
                (card.id, int(year), int(month)),
            )
            cur.execute(
                """
                INSERT INTO cartoes_credito_mes (
                    id_cartao, mes, ano, limite, id_conta, dia_venc, dia_fecha,
                    fatura_paga, conta_vinculada,
                    data_fecha_manual, data_venc_manual, status_manual
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.id,
                    int(month),
                    int(year),
                    card.limite,
                    id_conta or card.id_conta,
                    card.dia_venc,
                    card.dia_fecha,
                    "S" if fatura_paga else "N",
                    "S" if (id_conta or card.id_conta) else "N",
                    keep_fecha,
                    keep_venc,
                    keep_status,
                ),
            )

    def get_invoice_manual_overrides(
        self, card_id: str, year: int, month: int
    ) -> Tuple[Optional[date], Optional[date], str]:
        """Retorna `(data_fechamento_manual, data_vencimento_manual, status_manual)` do mês."""
        rows = self.db.execute_query(
            """
            SELECT data_fecha_manual, data_venc_manual, status_manual
            FROM cartoes_credito_mes
            WHERE id_cartao = ? AND ano = ? AND mes = ?
            """,
            (str(card_id), int(year), int(month)),
        )
        if not rows:
            return None, None, ""
        r = rows[0]
        return (
            parse_date(r["data_fecha_manual"]),
            parse_date(r["data_venc_manual"]),
            str(r["status_manual"] or "").strip(),
        )

    def update_invoice_month(
        self,
        card_id: str,
        year: int,
        month: int,
        *,
        dia_fecha: Optional[int] = None,
        dia_venc: Optional[int] = None,
        limite: Optional[float] = None,
        id_conta: Optional[str] = None,
        data_fechamento: Optional[date] = None,
        data_vencimento: Optional[date] = None,
        status_manual: Optional[str] = None,
    ) -> InvoiceDTO:
        """
        Permite alterar pontualmente os dados da fatura de um mês específico
        em `cartoes_credito_mes`.

        - `dia_fecha`/`dia_venc`/`limite`/`id_conta`: `None` mantém o valor atual.
        - `data_fechamento`/`data_vencimento`: datas exatas manuais; `None` volta ao
          cálculo automático pelo ciclo (limpa a data manual).
        - `status_manual`: 'Aberta', 'Fechada' ou 'Paga'; `None`/vazio = automático.
        Quando há data de vencimento manual, as datas das despesas NÃO são alteradas.
        """
        card = self.get_card(card_id)
        if card is None:
            raise ValueError(f"Cartão '{card_id}' não encontrado.")
        if status_manual not in (None, "", "Aberta", "Fechada", "Paga"):
            raise ValueError("Status manual inválido. Use Aberta, Fechada ou Paga.")
        if (
            data_fechamento is not None
            and data_vencimento is not None
            and data_vencimento < data_fechamento
        ):
            raise ValueError(
                "A data de vencimento não pode ser anterior à data de fechamento."
            )

        existing = self.db.execute_query(
            """
            SELECT limite, id_conta, dia_venc, dia_fecha, fatura_paga
            FROM cartoes_credito_mes
            WHERE id_cartao = ? AND ano = ? AND mes = ?
            """,
            (str(card_id), int(year), int(month)),
        )
        paga = False
        cur_limite = card.limite
        cur_conta = card.id_conta
        cur_venc = card.dia_venc
        cur_fecha = card.dia_fecha

        if existing:
            paga = str(existing[0]["fatura_paga"] or "N").upper() == "S"
            if existing[0]["limite"] is not None:
                cur_limite = float(existing[0]["limite"])
            if existing[0]["id_conta"]:
                cur_conta = str(existing[0]["id_conta"])
            if existing[0]["dia_venc"]:
                cur_venc = int(existing[0]["dia_venc"])
            if existing[0]["dia_fecha"]:
                cur_fecha = int(existing[0]["dia_fecha"])

        new_fecha = max(1, min(31, int(dia_fecha if dia_fecha is not None else cur_fecha)))
        new_venc = max(1, min(31, int(dia_venc if dia_venc is not None else cur_venc)))
        new_limite = round(float(limite if limite is not None else cur_limite), 2)
        new_conta = id_conta if id_conta is not None else cur_conta

        with self.db.transaction() as cur:
            cur.execute(
                """
                DELETE FROM cartoes_credito_mes
                WHERE id_cartao = ? AND ano = ? AND mes = ?
                """,
                (str(card_id), int(year), int(month)),
            )
            cur.execute(
                """
                INSERT INTO cartoes_credito_mes (
                    id_cartao, mes, ano, limite, id_conta, dia_venc, dia_fecha,
                    fatura_paga, conta_vinculada,
                    data_fecha_manual, data_venc_manual, status_manual
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(card_id),
                    int(month),
                    int(year),
                    new_limite,
                    new_conta,
                    new_venc,
                    new_fecha,
                    "S" if paga else "N",
                    "S" if new_conta else "N",
                    to_db_date(data_fechamento),
                    to_db_date(data_vencimento),
                    status_manual or None,
                ),
            )
            orig_due = self.compute_due_date_for_invoice(card, year, month)
            eff_card_new = CardDTO(**{**vars(card), "dia_fecha": new_fecha, "dia_venc": new_venc})
            target_due = data_vencimento or self.compute_due_date_for_invoice(eff_card_new, year, month)
            if target_due != orig_due:
                cur.execute(
                    """
                    UPDATE despesas
                    SET data = ?
                    WHERE id_cartao_credito = ?
                      AND data = ?
                      AND LOWER(COALESCE(status, 'pd')) NOT IN ('pg', 'e', 's')
                    """,
                    (to_db_date(target_due), str(card_id), to_db_date(orig_due)),
                )
        return self.get_invoice(card_id, year, month)

    def reset_invoice_month(self, card_id: str, year: int, month: int) -> InvoiceDTO:
        """Restaura o ciclo e configurações originais do cartão para o mês especificado."""
        card = self.get_card(card_id)
        if card is None:
            raise ValueError(f"Cartão '{card_id}' não encontrado.")
        orig_due = self.compute_due_date_for_invoice(card, year, month)
        with self.db.transaction() as cur:
            cur.execute(
                """
                SELECT data_venc_manual, dia_venc, dia_fecha FROM cartoes_credito_mes
                WHERE id_cartao = ? AND ano = ? AND mes = ?
                """,
                (str(card_id), int(year), int(month)),
            )
            row_prev = cur.fetchone()
            cur_due = orig_due
            if row_prev:
                m_venc, d_v, d_f = row_prev[0], row_prev[1], row_prev[2]
                if m_venc:
                    cur_due = parse_date(m_venc) or orig_due
                elif d_v or d_f:
                    dummy = CardDTO(
                        **{
                            **vars(card),
                            "dia_venc": d_v or card.dia_venc,
                            "dia_fecha": d_f or card.dia_fecha,
                        }
                    )
                    cur_due = self.compute_due_date_for_invoice(dummy, year, month)

            cur.execute(
                """
                DELETE FROM cartoes_credito_mes
                WHERE id_cartao = ? AND ano = ? AND mes = ?
                """,
                (str(card_id), int(year), int(month)),
            )
            if cur_due != orig_due:
                cur.execute(
                    """
                    UPDATE despesas
                    SET data = ?
                    WHERE id_cartao_credito = ?
                      AND data = ?
                      AND LOWER(COALESCE(status, 'pd')) NOT IN ('pg', 'e', 's')
                    """,
                    (to_db_date(orig_due), str(card_id), to_db_date(cur_due)),
                )
        return self.get_invoice(card_id, year, month)

    # ------------------------------------------------------------------ #
    # Fatura vigente (aberta) — lógica de app de banco (ex.: Nubank)
    # ------------------------------------------------------------------ #
    def get_open_invoice(
        self, card_id: str, ref: Optional[date] = None
    ) -> InvoiceDTO:
        """
        Retorna a fatura ABERTA na data `ref` (hoje por padrão): a primeira fatura
        (por mês de vencimento) ainda não paga cujo fechamento é posterior a `ref`
        ou cujo status manual é 'Aberta'. É nela que as compras de hoje se acumulam.
        Se nenhuma estiver aberta, devolve a próxima fatura não paga e, por fim, a do
        mês de `ref`.
        """
        ref = ref or date.today()
        base = date(ref.year, ref.month, 1)
        candidates: List[InvoiceDTO] = []
        for offset in (-1, 0, 1, 2):
            m = add_months(base, offset)
            candidates.append(self.get_invoice(card_id, m.year, m.month, ref=ref))

        for inv in candidates:
            if inv.paga:
                continue
            if inv.status == "Aberta" and inv.data_fechamento > ref:
                return inv
        for inv in candidates:
            if not inv.paga and inv.status == "Aberta":
                return inv
        for inv in candidates:
            if not inv.paga and inv.data_fechamento > ref:
                return inv
        return self.get_invoice(card_id, ref.year, ref.month, ref=ref)

    def resolve_invoice_for_context(
        self,
        card_id: str,
        year: int,
        month: int,
        ref: Optional[date] = None,
    ) -> InvoiceDTO:
        """
        Resolve a fatura correspondente ao mês `(year, month)` selecionado no cabeçalho global:
        Quando a fatura do mês corrente já fechou (`today >= data_fechamento`) e está paga
        ou sem saldo pendente, o ciclo ativo de compras do mês já pertence à fatura do
        mês seguinte (`+1 mês`), mantendo Transações (mês corrente) e Cartões (próxima fatura)
        alinhados durante a navegação.
        """
        today = ref or date.today()
        cur_inv = self.get_invoice(card_id, today.year, today.month, ref=today)
        if today >= cur_inv.data_fechamento and (cur_inv.paga or cur_inv.total <= 0):
            target = add_months(date(year, month, 1), 1)
            return self.get_invoice(card_id, target.year, target.month, ref=today)
        return self.get_invoice(card_id, year, month, ref=today)

    def preview_realign_card_expenses(self, card_id: str) -> List[Dict[str, object]]:
        """
        Lista (SEM gravar) as compras à vista e parcelas importadas, não pagas, do cartão cujo
        vencimento gravado difere do calculado pelo ciclo atual (`compute_due_date` sobre a data
        da compra/faturamento). Fixas e adiantamentos são ignorados por segurança.
        """
        card = self.get_card(card_id)
        if card is None:
            raise ValueError(f"Cartão '{card_id}' não encontrado.")
        rows = self.db.execute_query(
            """
            SELECT id, descricao, data_evento, data, valor, recorrencia, num_parcela, num_parcelas
            FROM despesas
            WHERE id_cartao_credito = ?
              AND (data_exclusao IS NULL OR data_exclusao = '')
              AND LOWER(COALESCE(status, 'pd')) NOT IN ('pg', 'e', 's')
              AND COALESCE(recorrencia, 'U') IN ('U', 'P')
              AND COALESCE(adiantamento_fatura, 'N') <> 'S'
              AND COALESCE(valor, 0) > 0
              AND NULLIF(data_evento, '') IS NOT NULL
            ORDER BY data_evento, descricao
            """,
            (str(card_id),),
        )
        changes: List[Dict[str, object]] = []
        for r in rows:
            purchase = parse_date(r["data_evento"])
            old_due = parse_date(r["data"])
            if purchase is None or old_due is None:
                continue
            rec = str(r["recorrencia"] or "U").upper()
            n_parc = int(r["num_parcela"] or 1)
            tot_parc = int(r["num_parcelas"] or 1)
            base_due = self.compute_due_date(card, purchase)
            if rec == "P" and tot_parc > 1 and n_parc > 1:
                month_diff = abs(
                    (old_due.year - purchase.year) * 12 + (old_due.month - purchase.month)
                )
                if month_diff <= 1:
                    new_due = base_due
                else:
                    new_due = add_months(base_due, n_parc - 1, day=card.dia_venc)
            else:
                new_due = base_due
            if new_due != old_due:
                changes.append(
                    {
                        "id": str(r["id"]),
                        "descricao": str(r["descricao"] or ""),
                        "valor": float(r["valor"] or 0.0),
                        "data_compra": purchase,
                        "vencimento_atual": old_due,
                        "vencimento_novo": new_due,
                    }
                )
        return changes

    def realign_card_expenses(self, card_id: str) -> int:
        """Grava o realinhamento previsto em `preview_realign_card_expenses`. Retorna a quantidade."""
        changes = self.preview_realign_card_expenses(card_id)
        if not changes:
            return 0
        with self.db.transaction() as cur:
            for ch in changes:
                cur.execute(
                    "UPDATE despesas SET data = ? WHERE id = ?",
                    (to_db_date(ch["vencimento_novo"]), ch["id"]),  # type: ignore[arg-type]
                )
        return len(changes)

    def add_invoice_advance(
        self,
        card_id: str,
        year: int,
        month: int,
        *,
        valor: float,
        id_conta: str,
        data_pagamento: Optional[date] = None,
        descricao: str = "Adiantamento de fatura",
    ) -> Tuple[str, str]:
        """
        Registra um adiantamento de fatura:
        1. Cria uma despesa paga na conta corrente selecionada (`adiantamento_fatura = 'S'`).
        2. Cria um crédito (valor negativo) na fatura `(year, month)` do cartão para abater o saldo.
        Retorna `(id_despesa_conta, id_credito_fatura)`.
        """
        if valor <= 0:
            raise ValueError("O valor do adiantamento deve ser maior que zero.")
        invoice = self.get_invoice(card_id, year, month)
        pay_date = data_pagamento or date.today()
        cat_id, sub_id = self.tx_service.default_category(
            KIND_DESPESA, invoice.card.id_profile
        )

        # 1. Despesa efetivada na conta corrente
        acc_exp_ids = self.tx_service.create_expense(
            descricao=f"{descricao} ({invoice.card.nome})",
            valor=round(float(valor), 2),
            data_vencimento=pay_date,
            data_evento=pay_date,
            profile_id=invoice.card.id_profile,
            id_conta=id_conta,
            id_categoria=cat_id,
            id_subcategoria=sub_id,
            recorrencia=REC_UNICA,
            pago=True,
            data_efetivacao=pay_date,
            obs=f"Adiantamento da fatura {month:02d}/{year} do cartão {invoice.card.nome}",
        )
        acc_exp_id = acc_exp_ids[0]

        # 2. Crédito (valor negativo) direto na fatura do mês/ano do cartão
        credit_id = uuid.uuid4().hex[:16]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE despesas SET adiantamento_fatura = 'S' WHERE id = ?",
                (acc_exp_id,),
            )
            cur.execute(
                """
                INSERT INTO despesas (
                    id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                    obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                    parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                    id_subcategoria, contabilizar, considerar_estatistica, somar_total,
                    adiantamento_fatura, data_update, ultima_modificacao
                ) VALUES (?, ?, ?, ?, 'U', ?, ?, 'pd', ?, ?, ?, ?, 1, 1, 1, 30, 0, ?, ?, ?, 'N', 'N', 'S', 'S', ?, ?)
                """,
                (
                    credit_id,
                    invoice.card.id_profile,
                    f"Crédito Adiantamento — {descricao}",
                    -round(float(valor), 2),
                    invoice.data_vencimento.isoformat(),
                    to_db_date(pay_date),
                    f"Crédito referente ao adiantamento na conta #{id_conta}",
                    now,
                    id_conta,
                    credit_id,
                    card_id,
                    cat_id,
                    sub_id,
                    now,
                    now,
                ),
            )
        return acc_exp_id, credit_id

    def refund_card_expense(
        self,
        occ: Occurrence,
        *,
        valor: Optional[float] = None,
        data_estorno: Optional[date] = None,
    ) -> str:
        """
        Registra o estorno de uma despesa de cartão na mesma fatura (`id_despesa_estornada`),
        lançando um valor negativo vinculado à despesa original.
        """
        if not occ.id_cartao:
            raise ValueError("Apenas despesas de cartão possuem estorno de fatura.")
        refund_val = abs(float(valor if valor is not None else occ.total))
        evt_date = data_estorno or date.today()
        refund_id = uuid.uuid4().hex[:16]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cat_id = occ.id_categoria
        sub_id = occ.id_subcategoria
        if not cat_id:
            cat_id, sub_id = self.tx_service.default_category(
                KIND_DESPESA, occ.id_profile
            )

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO despesas (
                    id, id_profile, descricao, valor, recorrencia, data, data_evento, status,
                    obs, data_cadastro, id_conta, id_origem, num_parcela, num_parcelas,
                    parc_inicial, intervalo, juros, id_cartao_credito, id_categoria,
                    id_subcategoria, id_despesa_estornada, contabilizar,
                    considerar_estatistica, somar_total, data_update, ultima_modificacao
                ) VALUES (?, ?, ?, ?, 'U', ?, ?, 'pd', ?, ?, ?, ?, 1, 1, 1, 30, 0, ?, ?, ?, ?, 'S', 'S', 'S', ?, ?)
                """,
                (
                    refund_id,
                    occ.id_profile,
                    f"Estorno: {occ.descricao}",
                    -round(refund_val, 2),
                    occ.data_vencimento.isoformat(),
                    to_db_date(evt_date),
                    f"Estorno referente a {occ.descricao}",
                    now,
                    occ.id_conta,
                    refund_id,
                    occ.id_cartao,
                    cat_id,
                    sub_id,
                    occ.id,
                    now,
                    now,
                ),
            )
        return refund_id

    def wipe_card_expenses(self, card_id: str, soft: bool = False) -> int:
        """
        Exclui todas as despesas vinculadas a este cartão (para limpar a fatura e permitir reimportação do zero).
        Também limpa as impressões digitais de importação (import_fingerprints) para permitir reimportar
        os mesmos extratos sem falso-positivo de duplicidade.
        Redefine o status das faturas mensais do cartão para 'Aberta' / não paga.
        Retorna o total de despesas excluídas.
        """
        card = self.get_card(card_id)
        if card is None:
            raise ValueError(f"Cartão '{card_id}' não encontrado.")
        rows = self.db.execute_query(
            """
            SELECT id FROM despesas
            WHERE id_cartao_credito = ? OR obs LIKE ?
            """,
            (str(card_id), f"%[Pagamento Fatura:{card_id}:%"),
        )
        if not rows:
            return 0
        tx_ids = [str(r["id"]) for r in rows]
        count = len(tx_ids)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction() as cur:
            for chunk in _chunks(tx_ids):
                ph = ",".join("?" * len(chunk))
                cur.execute(f"DELETE FROM import_fingerprints WHERE id_transacao IN ({ph})", list(chunk))
                cur.execute(f"DELETE FROM despesas_cat_valor WHERE id_despesa IN ({ph})", list(chunk))
                cur.execute(f"DELETE FROM despesas_fixas WHERE id_despesa IN ({ph})", list(chunk))
                cur.execute(f"DELETE FROM tags_transacoes WHERE id_transacao IN ({ph}) AND tipo_transacao = 'DESPESA'", list(chunk))

            if soft:
                cur.execute(
                    """
                    UPDATE despesas
                    SET data_exclusao = ?, ultima_modificacao = ?
                    WHERE (id_cartao_credito = ? OR obs LIKE ?)
                      AND (data_exclusao IS NULL OR data_exclusao = '')
                    """,
                    (now_str, now_str, str(card_id), f"%[Pagamento Fatura:{card_id}:%"),
                )
            else:
                for chunk in _chunks(tx_ids):
                    ph = ",".join("?" * len(chunk))
                    cur.execute(f"DELETE FROM despesas WHERE id IN ({ph})", list(chunk))

            cur.execute(
                """
                UPDATE cartoes_credito_mes
                SET fatura_paga = 'N', status_manual = NULL, data_fecha_manual = NULL, data_venc_manual = NULL
                WHERE id_cartao = ?
                """,
                (str(card_id),),
            )
        return count
