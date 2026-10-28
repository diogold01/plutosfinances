"""Utilitários de datas (meses, intervalos de recorrência e parsing seguro)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Iterator, Optional, Tuple


def parse_date(value: object) -> Optional[date]:
    """Converte valores do SQLite ('YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS', date) em `date`."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def to_db_date(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def clamp_day(year: int, month: int, day: int) -> int:
    last = calendar.monthrange(year, month)[1]
    return max(1, min(int(day), last))


def month_bounds(year: int, month: int) -> Tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def add_months(base: date, months: int, day: Optional[int] = None) -> date:
    """Soma `months` meses preservando (ou forçando) o dia, limitado ao último dia do mês."""
    total = base.year * 12 + (base.month - 1) + int(months)
    year, month0 = divmod(total, 12)
    month = month0 + 1
    target_day = day if day is not None else base.day
    return date(year, month, clamp_day(year, month, target_day))


def add_interval(base: date, index: int, intervalo: Optional[int]) -> date:
    """
    Calcula a data da ocorrência `index` (0-based) conforme o intervalo da referência:
    30 (ou 0/-1/None) = mensal, 7 = semanal, 15 = quinzenal, 60 = bimestral,
    90 = trimestral, 180 = semestral, 365 = anual; outros valores = dias corridos.
    """
    iv = int(intervalo or 30)
    if iv in (30, 0, -1):
        return add_months(base, index)
    if iv == 60:
        return add_months(base, 2 * index)
    if iv == 90:
        return add_months(base, 3 * index)
    if iv == 180:
        return add_months(base, 6 * index)
    if iv == 365:
        return add_months(base, 12 * index)
    return base + timedelta(days=iv * index)


def iter_months(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> Iterator[Tuple[int, int]]:
    """Itera meses de (start) inclusive até (end) exclusive."""
    y, m = start_year, start_month
    while (y, m) < (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def split_amount(total: float, parts: int) -> list[float]:
    """Divide um valor em `parts` parcelas em centavos, com o resíduo na 1ª parcela."""
    parts = max(1, int(parts))
    cents = int(round(float(total) * 100))
    base, rem = divmod(abs(cents), parts)
    sign = -1 if cents < 0 else 1
    values = [base] * parts
    values[0] += rem
    return [sign * v / 100.0 for v in values]


def format_br_date(value: Optional[date]) -> str:
    return value.strftime("%d/%m/%Y") if value else ""
