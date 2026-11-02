"""Módulo de serviços de cálculo de rendimento de investimentos (CDB / CDI 100% Local-First).

Implementa a convenção oficial do mercado financeiro brasileiro (B3 / Anbima):
- Ano padrão de 252 dias úteis.
- Fator diário derivado da taxa CDI anual: (1 + CDI_anual)^(1 / 252) - 1.
- Composição diária de juros sobre o saldo líquido aportado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple


# Feriados nacionais fixos brasileiros (mês, dia)
NATIONAL_FIXED_HOLIDAYS = {
    (1, 1),    # Confraternização Universal
    (4, 21),   # Tiradentes
    (5, 1),    # Dia do Trabalho
    (9, 7),    # Independência do Brasil
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),   # Finados
    (11, 15),  # Proclamação da República
    (11, 20),  # Dia da Consciência Negra
    (12, 25),  # Natal
}


def is_business_day(d: date) -> bool:
    """Verifica se uma data é dia útil bancário (segunda a sexta e não feriado nacional fixo)."""
    if d.weekday() >= 5:
        return False
    if (d.month, d.day) in NATIONAL_FIXED_HOLIDAYS:
        return False
    return True


def count_business_days(start_date: date, end_date: date) -> int:
    """
    Conta os dias úteis entre start_date (exclusivo) e end_date (inclusive),
    seguindo a convenção de apuração de juros diários D+1.
    """
    if end_date <= start_date:
        return 0
    curr = start_date + timedelta(days=1)
    business_days = 0
    while curr <= end_date:
        if is_business_day(curr):
            business_days += 1
        curr += timedelta(days=1)
    return business_days


def calculate_daily_cdi_factor(cdi_annual_pct: float, cdi_factor_pct: float = 100.0) -> float:
    """
    Calcula o fator diário de rendimento proporcional ao CDI.
    Exemplo: CDI 10.75% a.a. e 100% do CDI -> (1 + 0.1075)^(1/252) - 1.
    """
    if cdi_annual_pct <= 0 or cdi_factor_pct <= 0:
        return 0.0
    annual_rate = cdi_annual_pct / 100.0
    daily_rate_full = (1.0 + annual_rate) ** (1.0 / 252.0) - 1.0
    return daily_rate_full * (cdi_factor_pct / 100.0)


@dataclass
class CDBYieldResult:
    """Resultado detalhado do rendimento de uma Caixinha CDB."""

    saldo_aportado: float          # Saldo nominal líquido de aportes - resgates
    rendimento_acumulado: float     # Juros acumulados calculados no período
    saldo_total: float             # saldo_aportado + rendimento_acumulado
    dias_uteis: int                # Quantidade de dias úteis com rendimento
    cdi_anual: float               # Taxa CDI anual utilizada (ex: 10.75)
    percentual_cdi: float          # Percentual da taxa (ex: 100.0)


def calculate_account_monthly_yield(
    saldo_inicial: float,
    daily_movements: Dict[date, float],
    year: int,
    month: int,
    cdi_annual_pct: float,
    percentual_cdi: float = 100.0,
    reference_date: Optional[date] = None,
) -> CDBYieldResult:
    """
    Calcula dia a dia o rendimento composto de uma conta CDB durante um mês específico.

    :param saldo_inicial: Saldo que abriu o mês.
    :param daily_movements: Dicionário mapeando {data: valor_liquido_movimentado_no_dia}.
           Valores positivos são aportes; negativos são resgates.
    :param year: Ano de competência.
    :param month: Mês de competência.
    :param cdi_annual_pct: Taxa CDI anual padrão (ex: 10.75).
    :param percentual_cdi: Percentual do CDI da caixinha (ex: 100.0%).
    :param reference_date: Data limite de apuração (padrão: hoje ou fim do mês).
    """
    import calendar

    _, last_day = calendar.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    today = reference_date or date.today()

    if today < month_start:
        return CDBYieldResult(
            saldo_aportado=round(saldo_inicial, 2),
            rendimento_acumulado=0.0,
            saldo_total=round(saldo_inicial, 2),
            dias_uteis=0,
            cdi_anual=cdi_annual_pct,
            percentual_cdi=percentual_cdi,
        )

    end_calc_date = min(month_end, today)
    daily_factor = calculate_daily_cdi_factor(cdi_annual_pct, percentual_cdi)

    # Simulação diária
    current_nominal = float(saldo_inicial)
    total_yield = 0.0
    business_days_counted = 0

    curr = month_start
    while curr <= end_calc_date:
        mov = daily_movements.get(curr, 0.0)
        current_nominal += mov

        if is_business_day(curr) and current_nominal > 0:
            business_days_counted += 1
            base = current_nominal + total_yield
            day_interest = base * daily_factor
            total_yield += day_interest

        curr += timedelta(days=1)

    saldo_aportado = round(current_nominal, 2)
    rendimento_acumulado = round(total_yield, 2)
    saldo_total = round(saldo_aportado + rendimento_acumulado, 2)

    return CDBYieldResult(
        saldo_aportado=saldo_aportado,
        rendimento_acumulado=rendimento_acumulado,
        saldo_total=saldo_total,
        dias_uteis=business_days_counted,
        cdi_anual=cdi_annual_pct,
        percentual_cdi=percentual_cdi,
    )
