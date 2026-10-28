"""Repositório de Contas Bancárias (`contas`) e Saldos Mensais (`contas_saldo`)."""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from app.config.theme_palette import argb_int_to_hex
from app.database.connection_manager import ConnectionManager


@dataclass
class AccountBalanceSummaryDTO:
    id: str
    id_profile: str
    descricao: str
    id_categoria: str
    categoria_nome: str
    categoria_cor_hex: str
    image_id: int
    image_key: str  # nome do arquivo de ícone do banco (ex.: 'ic_nubank.png')
    exibir_resumo: str
    somar_total: str
    padrao: str
    investimento: str
    fav: int
    exibir_saldo: str
    cheque_especial: float
    currency: str
    mes: int
    ano: int
    saldo_inicial: float
    receitas_efetivadas: float
    receitas_pendentes: float
    despesas_pagas: float
    despesas_pendentes: float
    transf_credito_efet: float
    transf_credito_pend: float
    transf_debito_efet: float
    transf_debito_pend: float

    @property
    def saldo_atual(self) -> float:
        """Saldo confirmado (efetivado) no mês."""
        return round(
            self.saldo_inicial
            + self.receitas_efetivadas
            - self.despesas_pagas
            + self.transf_credito_efet
            - self.transf_debito_efet,
            2,
        )

    @property
    def saldo_previsto(self) -> float:
        """Saldo previsto ao final do mês (incluindo pendentes)."""
        return round(
            self.saldo_atual
            + self.receitas_pendentes
            - self.despesas_pendentes
            + self.transf_credito_pend
            - self.transf_debito_pend,
            2,
        )

    @property
    def disponivel_com_cheque_especial(self) -> float:
        return round(self.saldo_atual + self.cheque_especial, 2)

    @property
    def name(self) -> str:
        return self.descricao



class AccountRepository:
    """
    Gerencia Contas (`contas`), Saldos Iniciais Mensais (`contas_saldo`) e o cálculo
    de Saldo Atual (Confirmado) e Saldo Previsto por conta e consolidado.
    """

    def __init__(self, db: ConnectionManager) -> None:
        self.db = db

    def create_account(
        self,
        descricao: str,
        id_categoria: str = "3",
        saldo_inicial: float = 0.0,
        cheque_especial: float = 0.0,
        exibir_resumo: str = "S",
        somar_total: str = "S",
        padrao: str = "N",
        investimento: str = "N",
        fav: int = 0,
        exibir_saldo: str = "S",
        image_id: int = 0,
        image_key: str = "ic_banco_default.png",
        profile_id: str = "1",
        currency: str = "BRL",
        mes_inicial: Optional[int] = None,
        ano_inicial: Optional[int] = None,
    ) -> str:
        account_id = str(uuid.uuid4())[:8]
        today = date.today()
        m = mes_inicial or today.month
        y = ano_inicial or today.year
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.transaction() as cur:
            if padrao == "S":
                cur.execute(
                    "UPDATE contas SET padrao = 'N' WHERE id_profile = ?",
                    (str(profile_id),),
                )
            seq = cur.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM contas WHERE id_profile = ?",
                (str(profile_id),),
            ).fetchone()[0]

            cur.execute(
                """
                INSERT INTO contas (
                    id, descricao, exibir_resumo, data_cadastro, somar_total,
                    padrao, id_categoria, cheque_especial, fav, exibir_saldo,
                    image_id, image_url, investimento, sequence, id_profile, currency
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    descricao.strip(),
                    exibir_resumo,
                    now_str,
                    somar_total,
                    padrao,
                    str(id_categoria),
                    float(cheque_especial),
                    int(fav),
                    exibir_saldo,
                    int(image_id),
                    image_key,
                    investimento,
                    int(seq),
                    str(profile_id),
                    currency,
                ),
            )
            cur.execute(
                """
                INSERT OR REPLACE INTO contas_saldo (
                    id_conta, mes, ano, si, cheque_especial, obs, si_custom
                )
                VALUES (?, ?, ?, ?, ?, 'Saldo inicial na criação', 1)
                """,
                (
                    account_id,
                    int(m),
                    int(y),
                    float(saldo_inicial),
                    float(cheque_especial),
                ),
            )
        return account_id

    def update_account(
        self,
        account_id: str,
        descricao: str,
        id_categoria: str,
        cheque_especial: float = 0.0,
        exibir_resumo: str = "S",
        somar_total: str = "S",
        padrao: str = "N",
        investimento: str = "N",
        fav: int = 0,
        exibir_saldo: str = "S",
        image_id: int = 0,
        image_key: str = "ic_banco_default.png",
        profile_id: str = "1",
    ) -> None:
        with self.db.transaction() as cur:
            if padrao == "S":
                cur.execute(
                    "UPDATE contas SET padrao = 'N' WHERE id_profile = ?",
                    (str(profile_id),),
                )
            cur.execute(
                """
                UPDATE contas
                SET descricao = ?,
                    id_categoria = ?,
                    cheque_especial = ?,
                    exibir_resumo = ?,
                    somar_total = ?,
                    padrao = ?,
                    investimento = ?,
                    fav = ?,
                    exibir_saldo = ?,
                    image_id = ?,
                    image_url = ?
                WHERE id = ?
                """,
                (
                    descricao.strip(),
                    str(id_categoria),
                    float(cheque_especial),
                    exibir_resumo,
                    somar_total,
                    padrao,
                    investimento,
                    int(fav),
                    exibir_saldo,
                    int(image_id),
                    image_key,
                    str(account_id),
                ),
            )

    def delete_account(self, account_id: str, soft: bool = True) -> None:
        if soft:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_write(
                "UPDATE contas SET data_exclusao = ? WHERE id = ?",
                (now_str, str(account_id)),
            )
        else:
            with self.db.transaction() as cur:
                cur.execute(
                    "DELETE FROM contas_saldo WHERE id_conta = ?",
                    (str(account_id),),
                )
                cur.execute("DELETE FROM contas WHERE id = ?", (str(account_id),))

    def set_monthly_opening_balance(
        self,
        account_id: str,
        mes: int,
        ano: int,
        saldo_inicial: float,
        cheque_especial: Optional[float] = None,
        obs: str = "Ajuste manual de saldo inicial",
    ) -> None:
        """Define explicitamente o saldo inicial (`si`) de uma conta para um mês/ano."""
        if cheque_especial is None:
            cheque_especial = float(
                self.db.fetch_scalar(
                    "SELECT COALESCE(cheque_especial, 0) FROM contas WHERE id = ?",
                    (str(account_id),),
                    default=0.0,
                )
            )
        self.db.execute_write(
            """
            INSERT OR REPLACE INTO contas_saldo (
                id_conta, mes, ano, si, cheque_especial, obs, si_custom
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                str(account_id),
                int(mes),
                int(ano),
                float(saldo_inicial),
                float(cheque_especial),
                obs,
            ),
        )

    def reconcile_account_balance(
        self,
        account_id: str,
        mes: int,
        ano: int,
        desired_current_balance: float,
    ) -> float:
        """
        Reconcilia o Saldo Atual (Confirmado) da conta no mês/ano, ajustando o saldo inicial `si`
        de forma que `saldo_atual` passe a ser exatamente `desired_current_balance`.
        Retorna o novo `saldo_inicial` gravado.
        """
        summary = self.get_account_summary(account_id, mes, ano)
        if summary is None:
            raise ValueError(f"Conta não encontrada: {account_id}")
        delta = round(desired_current_balance - summary.saldo_atual, 2)
        new_si = round(summary.saldo_inicial + delta, 2)
        self.set_monthly_opening_balance(
            account_id=account_id,
            mes=mes,
            ano=ano,
            saldo_inicial=new_si,
            cheque_especial=summary.cheque_especial,
            obs=f"Reconciliação de saldo ({datetime.now().strftime('%d/%m/%Y %H:%M')})",
        )
        return new_si

    def _compute_opening_balance(
        self, account_id: str, mes: int, ano: int
    ) -> tuple[float, float]:
        """
        Obtém o Saldo Inicial (si) e Cheque Especial para `(mes, ano)`:
        1. Se houver registro em `contas_saldo` para `(mes, ano)` com `si_custom IN (1, '1', 'S')`, usa-o.
        2. Caso contrário, busca o `contas_saldo` customizado mais recente anterior a `(mes, ano)`
           e acumula o fluxo confirmado entre aquele mês e o início de `(mes, ano)`.
        """
        exact_row = self.db.fetch_one(
            """
            SELECT si, COALESCE(cheque_especial, 0) AS cheque_especial, si_custom
            FROM contas_saldo
            WHERE id_conta = ? AND mes = ? AND ano = ?
            """,
            (str(account_id), int(mes), int(ano)),
        )
        default_overdraft = float(
            self.db.fetch_scalar(
                "SELECT COALESCE(cheque_especial, 0) FROM contas WHERE id = ?",
                (str(account_id),),
                default=0.0,
            )
        )
        if exact_row is not None and str(exact_row["si_custom"]) in ("1", "S", "True"):
            return float(exact_row["si"] or 0.0), float(
                exact_row["cheque_especial"] or default_overdraft
            )

        # Busca o marco anterior mais próximo em contas_saldo
        prev_row = self.db.fetch_one(
            """
            SELECT mes, ano, si
            FROM contas_saldo
            WHERE id_conta = ?
              AND (ano < ? OR (ano = ? AND mes < ?))
            ORDER BY ano DESC, mes DESC
            LIMIT 1
            """,
            (str(account_id), int(ano), int(ano), int(mes)),
        )
        target_start = f"{int(ano):04d}-{int(mes):02d}-01"
        if prev_row is not None:
            base_si = float(prev_row["si"] or 0.0)
            base_start = f"{int(prev_row['ano']):04d}-{int(prev_row['mes']):02d}-01"
            date_filter_sql = "AND date(data) >= date(?) AND date(data) < date(?)"
            date_params: tuple = (base_start, target_start)
        else:
            # Se só existe um contas_saldo cadastrado no próprio mês (mesmo sem si_custom)
            if exact_row is not None:
                return float(exact_row["si"] or 0.0), float(
                    exact_row["cheque_especial"] or default_overdraft
                )
            base_si = 0.0
            date_filter_sql = "AND date(data) < date(?)"
            date_params = (target_start,)

        rec_prev = float(
            self.db.fetch_scalar(
                f"""
                SELECT COALESCE(SUM(valor), 0)
                FROM receitas
                WHERE id_conta = ?
                  AND data_exclusao IS NULL
                  AND COALESCE(efetivado, 'N') = 'S'
                  {date_filter_sql}
                """,
                (str(account_id), *date_params),
                default=0.0,
            )
        )
        desp_prev = float(
            self.db.fetch_scalar(
                f"""
                SELECT COALESCE(SUM(valor + COALESCE(juros, 0)), 0)
                FROM despesas
                WHERE id_conta = ?
                  AND COALESCE(id_cartao_credito, '') IN ('', '-1')
                  AND data_exclusao IS NULL
                  AND LOWER(COALESCE(status, 'p')) IN ('pg', 'e', 's')
                  {date_filter_sql}
                """,
                (str(account_id), *date_params),
                default=0.0,
            )
        )
        tc_prev = float(
            self.db.fetch_scalar(
                f"""
                SELECT COALESCE(SUM(valor), 0)
                FROM transferencias
                WHERE id_conta_destino = ?
                  AND data_exclusao IS NULL
                  AND COALESCE(contabilizada, 'N') = 'S'
                  {date_filter_sql}
                """,
                (str(account_id), *date_params),
                default=0.0,
            )
        )
        td_prev = float(
            self.db.fetch_scalar(
                f"""
                SELECT COALESCE(SUM(valor), 0)
                FROM transferencias
                WHERE id_conta_origem = ?
                  AND data_exclusao IS NULL
                  AND COALESCE(contabilizada, 'N') = 'S'
                  {date_filter_sql}
                """,
                (str(account_id), *date_params),
                default=0.0,
            )
        )
        computed_si = round(base_si + rec_prev - desp_prev + tc_prev - td_prev, 2)
        return computed_si, default_overdraft

    def _compute_monthly_flows(
        self, account_id: str, mes: int, ano: int
    ) -> dict[str, float]:
        """Calcula receitas, despesas (inclusive fixas) e transferências da conta no mês/ano."""
        last_day = calendar.monthrange(int(ano), int(mes))[1]
        start_date = f"{int(ano):04d}-{int(mes):02d}-01"
        end_date = f"{int(ano):04d}-{int(mes):02d}-{last_day:02d}"

        # 1. Receitas normais/parceladas no mês + Receitas fixas ativas no mês
        rec_rows = self.db.execute_query(
            """
            SELECT r.id, r.recorrencia, r.valor, r.efetivado, r.data,
                   rf.valor AS rf_valor, rf.efetivado AS rf_efetivado, rf.excluido_mes
            FROM receitas r
            LEFT JOIN receitas_fixas rf
              ON rf.id_receita = r.id
             AND strftime('%Y-%m', rf.data) = ?
            WHERE COALESCE(rf.id_conta, r.id_conta) = ?
              AND r.data_exclusao IS NULL
              AND COALESCE(rf.excluido_mes, 'N') != 'S'
              AND (
                  (COALESCE(r.recorrencia, 'U') NOT IN ('F', 'M') AND date(r.data) BETWEEN date(?) AND date(?))
                  OR
                  (COALESCE(r.recorrencia, 'U') IN ('F', 'M') AND date(r.data, 'start of month') <= date(?))
              )
            """,
            (f"{int(ano):04d}-{int(mes):02d}", str(account_id), start_date, end_date, start_date),
        )
        rec_efet = 0.0
        rec_pend = 0.0
        for rr in rec_rows:
            is_fixed = str(rr["recorrencia"] or "U") in ("F", "M")
            val = float(rr["rf_valor"] if (is_fixed and rr["rf_valor"] is not None) else (rr["valor"] or 0.0))
            efet_flag = str(
                rr["rf_efetivado"]
                if (is_fixed and rr["rf_efetivado"] is not None)
                else (rr["efetivado"] or "N")
            ).upper()
            if efet_flag in ("S", "PG", "E"):
                rec_efet += val
            else:
                rec_pend += val

        # 2. Despesas de conta (não cartão) no mês + Despesas fixas ativas no mês
        desp_rows = self.db.execute_query(
            """
            SELECT d.id, d.recorrencia, d.valor, d.juros, d.status, d.data,
                   df.valor AS df_valor, df.juros AS df_juros, df.status AS df_status, df.excluido_mes
            FROM despesas d
            LEFT JOIN despesas_fixas df
              ON df.id_despesa = d.id
             AND strftime('%Y-%m', df.data) = ?
            WHERE COALESCE(df.id_conta, d.id_conta) = ?
              AND COALESCE(df.id_cartao_credito, d.id_cartao_credito, '') IN ('', '-1')
              AND d.data_exclusao IS NULL
              AND COALESCE(d.contabilizar, 'S') != 'N'
              AND COALESCE(df.excluido_mes, 'N') != 'S'
              AND (
                  (COALESCE(d.recorrencia, 'U') != 'F' AND date(d.data) BETWEEN date(?) AND date(?))
                  OR
                  (COALESCE(d.recorrencia, 'U') = 'F' AND date(d.data, 'start of month') <= date(?))
              )
            """,
            (f"{int(ano):04d}-{int(mes):02d}", str(account_id), start_date, end_date, start_date),
        )
        desp_pg = 0.0
        desp_pd = 0.0
        for dr in desp_rows:
            is_fixed = str(dr["recorrencia"] or "U") == "F"
            val = float(dr["df_valor"] if (is_fixed and dr["df_valor"] is not None) else (dr["valor"] or 0.0))
            juros = float(dr["df_juros"] if (is_fixed and dr["df_juros"] is not None) else (dr["juros"] or 0.0))
            st_flag = str(
                dr["df_status"]
                if (is_fixed and dr["df_status"] is not None)
                else (dr["status"] if not is_fixed else "pd")
            ).lower()
            if st_flag in ("pg", "e", "s"):
                desp_pg += val + juros
            else:
                desp_pd += val + juros

        # 3. Transferências de entrada (crédito) e saída (débito)
        transf_rows = self.db.execute_query(
            """
            SELECT id_conta_origem, id_conta_destino, valor, COALESCE(contabilizada, 'N') AS contabilizada
            FROM transferencias
            WHERE (id_conta_origem = ? OR id_conta_destino = ?)
              AND data_exclusao IS NULL
              AND date(data) BETWEEN date(?) AND date(?)
            """,
            (str(account_id), str(account_id), start_date, end_date),
        )
        tc_ef = tc_pd = td_ef = td_pd = 0.0
        for tr in transf_rows:
            val = float(tr["valor"] or 0.0)
            is_efet = str(tr["contabilizada"]).upper() == "S"
            if str(tr["id_conta_destino"]) == str(account_id):
                if is_efet:
                    tc_ef += val
                else:
                    tc_pd += val
            if str(tr["id_conta_origem"]) == str(account_id):
                if is_efet:
                    td_ef += val
                else:
                    td_pd += val

        return {
            "receitas_efetivadas": round(rec_efet, 2),
            "receitas_pendentes": round(rec_pend, 2),
            "despesas_pagas": round(desp_pg, 2),
            "despesas_pendentes": round(desp_pd, 2),
            "transf_credito_efet": round(tc_ef, 2),
            "transf_credito_pend": round(tc_pd, 2),
            "transf_debito_efet": round(td_ef, 2),
            "transf_debito_pend": round(td_pd, 2),
        }

    def get_account_summary(
        self,
        account_id: str,
        mes: Optional[int] = None,
        ano: Optional[int] = None,
    ) -> Optional[AccountBalanceSummaryDTO]:
        today = date.today()
        m = int(mes or today.month)
        y = int(ano or today.year)
        row = self.db.fetch_one(
            """
            SELECT c.id, c.id_profile, c.descricao,
                   COALESCE(c.id_categoria, '3') AS id_categoria,
                   COALESCE(cc.descricao, 'Conta Corrente') AS categoria_nome,
                   COALESCE(cc.cor, -15228834) AS categoria_cor,
                   COALESCE(c.image_id, 0) AS image_id,
                   COALESCE(c.image_url, 'ic_banco_default.png') AS image_key,
                   COALESCE(c.exibir_resumo, 'S') AS exibir_resumo,
                   COALESCE(c.somar_total, 'S') AS somar_total,
                   COALESCE(c.padrao, 'N') AS padrao,
                   COALESCE(c.investimento, 'N') AS investimento,
                   COALESCE(c.fav, 0) AS fav,
                   COALESCE(c.exibir_saldo, 'S') AS exibir_saldo,
                   COALESCE(c.cheque_especial, 0) AS cheque_especial,
                   COALESCE(c.currency, 'BRL') AS currency
            FROM contas c
            LEFT JOIN contas_cat cc ON cc.id = c.id_categoria
            WHERE c.id = ?
            """,
            (str(account_id),),
        )
        if row is None:
            return None

        si, overdraft = self._compute_opening_balance(str(row["id"]), m, y)
        flows = self._compute_monthly_flows(str(row["id"]), m, y)
        return AccountBalanceSummaryDTO(
            id=str(row["id"]),
            id_profile=str(row["id_profile"] or "1"),
            descricao=str(row["descricao"] or "Conta"),
            id_categoria=str(row["id_categoria"]),
            categoria_nome=str(row["categoria_nome"]),
            categoria_cor_hex=argb_int_to_hex(int(row["categoria_cor"])),
            image_id=int(row["image_id"]),
            image_key=str(row["image_key"] or "ic_banco_default.png"),
            exibir_resumo=str(row["exibir_resumo"]),
            somar_total=str(row["somar_total"]),
            padrao=str(row["padrao"]),
            investimento=str(row["investimento"]),
            fav=int(row["fav"]),
            exibir_saldo=str(row["exibir_saldo"]),
            cheque_especial=float(overdraft),
            currency=str(row["currency"] or "BRL"),
            mes=m,
            ano=y,
            saldo_inicial=si,
            **flows,
        )

    def list_accounts_with_balances(
        self,
        profile_id: str = "1",
        mes: Optional[int] = None,
        ano: Optional[int] = None,
        search_text: str = "",
        include_deleted: bool = False,
    ) -> List[AccountBalanceSummaryDTO]:
        today = date.today()
        m = int(mes or today.month)
        y = int(ano or today.year)

        clauses = ["c.id_profile = ?"]
        params: list[object] = [str(profile_id)]
        if not include_deleted:
            clauses.append("c.data_exclusao IS NULL")
        if search_text.strip():
            clauses.append("LOWER(c.descricao) LIKE ?")
            params.append(f"%{search_text.strip().lower()}%")

        where_sql = " AND ".join(clauses)
        rows = self.db.execute_query(
            f"""
            SELECT c.id
            FROM contas c
            WHERE {where_sql}
            ORDER BY COALESCE(c.fav, 0) DESC,
                     CASE WHEN COALESCE(c.padrao, 'N') = 'S' THEN 0 ELSE 1 END,
                     COALESCE(c.sequence, 999) ASC,
                     c.descricao ASC
            """,
            params,
        )
        summaries: List[AccountBalanceSummaryDTO] = []
        for r in rows:
            s = self.get_account_summary(str(r["id"]), m, y)
            if s is not None:
                summaries.append(s)
        return summaries

    def list_accounts(
        self,
        profile_id: str = "1",
        mes: Optional[int] = None,
        ano: Optional[int] = None,
        include_deleted: bool = False,
    ) -> List[AccountBalanceSummaryDTO]:
        return self.list_accounts_with_balances(
            profile_id=profile_id,
            mes=mes,
            ano=ano,
            include_deleted=include_deleted,
        )

    def get_consolidated_totals(
        self, profile_id: str = "1", mes: Optional[int] = None, ano: Optional[int] = None
    ) -> dict[str, float]:
        accounts = [
            a
            for a in self.list_accounts_with_balances(
                profile_id=profile_id, mes=mes, ano=ano
            )
            if str(a.somar_total or "S").upper() == "S"
        ]
        return {
            "saldo_inicial": round(sum(a.saldo_inicial for a in accounts), 2),
            "saldo_atual": round(sum(a.saldo_atual for a in accounts), 2),
            "saldo_previsto": round(sum(a.saldo_previsto for a in accounts), 2),
            "disponivel_com_cheque_especial": round(
                sum(a.disponivel_com_cheque_especial for a in accounts), 2
            ),
        }

