"""
Serviço de Objetivos / Metas Financeiras (`objetivos` e `objetivos_dep`).

Regras de negócio:
- Gerencia metas de médio e longo prazo com saldo inicial (`saldo_inicial`),
  histórico de aportes/retiradas (`objetivos_dep`), data alvo (`expec`),
  motivação, cor e status de conclusão (`realizado = 'S'/'N'`).
- Calcula automaticamente o saldo acumulado, valor restante, percentual de progresso
  e o aporte mensal sugerido até a data de expectativa (`expec`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from app.config.theme_palette import argb_int_to_hex, hex_to_argb_int
from app.database.connection_manager import ConnectionManager
from app.domain.date_utils import parse_date


@dataclass
class GoalDepositDTO:
    id: str
    id_objetivo: str
    valor: float
    data: date
    obs: str = ""


@dataclass
class GoalDTO:
    id: str
    id_profile: str
    descricao: str
    meta: float
    saldo_inicial: float
    total_aportes: float
    data_cadastro: date
    data_expectativa: Optional[date]
    data_realizado: Optional[date]
    motivacao: str
    realizado: bool
    color_int: int
    color_hex: str
    deposits: List[GoalDepositDTO] = field(default_factory=list)

    @property
    def saldo_acumulado(self) -> float:
        return round(self.saldo_inicial + self.total_aportes, 2)

    @property
    def restante(self) -> float:
        return max(0.0, round(self.meta - self.saldo_acumulado, 2))

    @property
    def percentual(self) -> float:
        if self.meta <= 0:
            return 100.0
        return min(100.0, round((self.saldo_acumulado / self.meta) * 100.0, 1))

    @property
    def aporte_mensal_sugerido(self) -> float:
        rem = self.restante
        if rem <= 0 or not self.data_expectativa:
            return 0.0
        today = date.today()
        months = (
            (self.data_expectativa.year - today.year) * 12
            + (self.data_expectativa.month - today.month)
        )
        months = max(1, months)
        return round(rem / months, 2)


class GoalService:
    """Serviço de domínio para Objetivos (Metas Financeiras) e seus Aportes."""

    def __init__(self, db: ConnectionManager) -> None:
        self.db = db

    def create_goal(
        self,
        *,
        descricao: str,
        meta: float,
        saldo_inicial: float = 0.0,
        data_expectativa: Optional[date] = None,
        motivacao: str = "",
        color_hex: str = "#1E88E5",
        profile_id: str = "1",
    ) -> GoalDTO:
        clean_desc = descricao.strip()
        if not clean_desc:
            raise ValueError("Informe a descrição do objetivo.")
        if meta <= 0:
            raise ValueError("O valor da meta deve ser maior que zero.")

        goal_id = uuid.uuid4().hex[:16]
        now_str = datetime.now().strftime("%Y-%m-%d")
        expec_str = data_expectativa.isoformat() if data_expectativa else None
        color_int = hex_to_argb_int(color_hex)

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO objetivos (
                    id, id_profile, descricao, meta, data_cadastro, expec,
                    saldo_inicial, motivacao, realizado, icon_id, color
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'N', 1, ?)
                """,
                (
                    goal_id,
                    str(profile_id),
                    clean_desc,
                    round(float(meta), 2),
                    now_str,
                    expec_str,
                    round(float(saldo_inicial), 2),
                    motivacao.strip(),
                    color_int,
                ),
            )
        goal = self.get_goal(goal_id)
        assert goal is not None
        return goal

    def update_goal(
        self,
        goal_id: str,
        *,
        descricao: str,
        meta: float,
        saldo_inicial: float = 0.0,
        data_expectativa: Optional[date] = None,
        motivacao: str = "",
        color_hex: str = "#1E88E5",
        realizado: bool = False,
    ) -> None:
        clean_desc = descricao.strip()
        if not clean_desc:
            raise ValueError("Informe a descrição do objetivo.")
        color_int = hex_to_argb_int(color_hex)
        expec_str = data_expectativa.isoformat() if data_expectativa else None
        real_date = date.today().isoformat() if realizado else None

        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE objetivos
                SET descricao = ?, meta = ?, saldo_inicial = ?, expec = ?,
                    motivacao = ?, color = ?, realizado = ?, data_realizado = ?
                WHERE id = ?
                """,
                (
                    clean_desc,
                    round(float(meta), 2),
                    round(float(saldo_inicial), 2),
                    expec_str,
                    motivacao.strip(),
                    color_int,
                    "S" if realizado else "N",
                    real_date,
                    str(goal_id),
                ),
            )

    def delete_goal(self, goal_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "DELETE FROM objetivos_dep WHERE id_objetivo = ?",
                (str(goal_id),),
            )
            cur.execute("DELETE FROM objetivos WHERE id = ?", (str(goal_id),))

    def add_deposit(
        self,
        goal_id: str,
        *,
        valor: float,
        data_deposito: Optional[date] = None,
        obs: str = "",
    ) -> str:
        if abs(valor) < 0.005:
            raise ValueError("Informe um valor de aporte ou retirada diferente de zero.")
        dep_id = uuid.uuid4().hex[:16]
        dt_str = (data_deposito or date.today()).isoformat()

        with self.db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO objetivos_dep (id, id_objetivo, valor, data, mensal, obs)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    dep_id,
                    str(goal_id),
                    round(float(valor), 2),
                    dt_str,
                    obs.strip(),
                ),
            )
        # Se atingiu a meta automaticamente, marca como realizado
        goal = self.get_goal(goal_id)
        if goal and goal.saldo_acumulado >= goal.meta and not goal.realizado:
            with self.db.transaction() as cur:
                cur.execute(
                    "UPDATE objetivos SET realizado = 'S', data_realizado = ? WHERE id = ?",
                    (dt_str, str(goal_id)),
                )
        return dep_id

    def delete_deposit(self, deposit_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute(
                "DELETE FROM objetivos_dep WHERE id = ?", (str(deposit_id),)
            )

    def get_goal(self, goal_id: str) -> Optional[GoalDTO]:
        rows = self.db.execute_query(
            """
            SELECT id, id_profile, descricao, COALESCE(meta, 0) AS meta,
                   data_cadastro, expec, data_realizado,
                   COALESCE(saldo_inicial, 0) AS saldo_inicial,
                   COALESCE(motivacao, '') AS motivacao,
                   COALESCE(realizado, 'N') AS realizado,
                   COALESCE(color, -14776091) AS color
            FROM objetivos
            WHERE id = ?
            """,
            (str(goal_id),),
        )
        if not rows:
            return None
        return self._row_to_goal(rows[0])

    def list_goals(
        self, profile_id: str = "1", include_completed: bool = True
    ) -> List[GoalDTO]:
        where_comp = (
            ""
            if include_completed
            else "AND UPPER(COALESCE(realizado, 'N')) != 'S'"
        )
        rows = self.db.execute_query(
            f"""
            SELECT id, id_profile, descricao, COALESCE(meta, 0) AS meta,
                   data_cadastro, expec, data_realizado,
                   COALESCE(saldo_inicial, 0) AS saldo_inicial,
                   COALESCE(motivacao, '') AS motivacao,
                   COALESCE(realizado, 'N') AS realizado,
                   COALESCE(color, -14776091) AS color
            FROM objetivos
            WHERE COALESCE(id_profile, '1') = ? {where_comp}
            ORDER BY CASE WHEN UPPER(COALESCE(realizado, 'N')) = 'S' THEN 1 ELSE 0 END,
                     COALESCE(expec, '9999-12-31') ASC,
                     descricao COLLATE NOCASE ASC
            """,
            (str(profile_id),),
        )
        return [self._row_to_goal(r) for r in rows]

    def _row_to_goal(self, r: object) -> GoalDTO:
        gid = str(r["id"])
        dep_rows = self.db.execute_query(
            """
            SELECT id, id_objetivo, COALESCE(valor, 0) AS valor, data, COALESCE(obs, '') AS obs
            FROM objetivos_dep
            WHERE id_objetivo = ?
            ORDER BY date(data) DESC, id DESC
            """,
            (gid,),
        )
        deposits = [
            GoalDepositDTO(
                id=str(dr["id"]),
                id_objetivo=gid,
                valor=round(float(dr["valor"] or 0.0), 2),
                data=parse_date(dr["data"]) or date.today(),
                obs=str(dr["obs"] or ""),
            )
            for dr in dep_rows
        ]
        total_aportes = round(sum(d.valor for d in deposits), 2)
        color_int = int(r["color"] if r["color"] is not None else -14776091)

        return GoalDTO(
            id=gid,
            id_profile=str(r["id_profile"] or "1"),
            descricao=str(r["descricao"] or "Objetivo"),
            meta=round(float(r["meta"] or 0.0), 2),
            saldo_inicial=round(float(r["saldo_inicial"] or 0.0), 2),
            total_aportes=total_aportes,
            data_cadastro=parse_date(r["data_cadastro"]) or date.today(),
            data_expectativa=parse_date(r["expec"]),
            data_realizado=parse_date(r["data_realizado"]),
            motivacao=str(r["motivacao"] or ""),
            realizado=str(r["realizado"] or "N").upper() == "S",
            color_int=color_int,
            color_hex=argb_int_to_hex(color_int),
            deposits=deposits,
        )
