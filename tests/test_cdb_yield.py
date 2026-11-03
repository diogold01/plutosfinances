"""Testes unitários do motor de rendimento de Caixinhas CDB / CDI."""

from __future__ import annotations

import os
from datetime import date
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

from app.domain.services.investment_yield_service import (
    calculate_daily_cdi_factor,
    count_business_days,
    is_business_day,
    calculate_account_monthly_yield,
)


def test_business_days_detection():
    # Sábado e Domingo nunca são dias úteis
    sabado = date(2026, 10, 31)
    domingo = date(2026, 11, 1)
    segunda = date(2026, 11, 2)  # Finados (feriado nacional)
    terca = date(2026, 11, 3)

    assert not is_business_day(sabado)
    assert not is_business_day(domingo)
    assert not is_business_day(segunda)
    assert is_business_day(terca)


def test_count_business_days():
    # De 03/11/2026 (terça) a 06/11/2026 (sexta) -> 3 dias úteis subsequentes (4, 5, 6)
    d1 = date(2026, 11, 3)
    d2 = date(2026, 11, 6)
    assert count_business_days(d1, d2) == 3


def test_daily_factor_calculation():
    # Com CDI 10.75% a.a. e 100% CDI
    factor = calculate_daily_cdi_factor(10.75, 100.0)
    # (1 + 0.1075)^(1/252) - 1 aprox 0.0004051 (aprox 0.0405% ao dia)
    assert 0.00040 < factor < 0.00041

    # Com 0% ou negativo retorna 0
    assert calculate_daily_cdi_factor(0.0) == 0.0
    assert calculate_daily_cdi_factor(10.75, 0.0) == 0.0


def test_monthly_yield_calculation():
    # Simulação: R$ 10.000 aportados no início de Outubro de 2026
    # Outubro/2026 teve 21 dias úteis (12/10 foi feriado)
    res = calculate_account_monthly_yield(
        saldo_inicial=10000.0,
        daily_movements={},
        year=2026,
        month=10,
        cdi_annual_pct=10.75,
        percentual_cdi=100.0,
        reference_date=date(2026, 10, 31),
    )

    assert res.saldo_aportado == 10000.0
    # Com 21 dias úteis a aprox 0.0405% ao dia, 10.000 rende por volta de R$ 85 a R$ 90
    assert 80.0 < res.rendimento_acumulado < 95.0
    assert res.saldo_total == round(10000.0 + res.rendimento_acumulado, 2)
    assert res.dias_uteis == 21


def test_monthly_yield_with_intra_month_movements():
    # R$ 1000 de saldo inicial + aporte de R$ 500 no dia 15
    res = calculate_account_monthly_yield(
        saldo_inicial=1000.0,
        daily_movements={date(2026, 10, 15): 500.0},
        year=2026,
        month=10,
        cdi_annual_pct=10.75,
        percentual_cdi=100.0,
        reference_date=date(2026, 10, 31),
    )
    assert res.saldo_aportado == 1500.0
    assert res.rendimento_acumulado > 0.0
    assert res.saldo_total == round(1500.0 + res.rendimento_acumulado, 2)


def test_monthly_yield_edge_cases():
    # Mês futuro não deve gerar rendimento
    res_future = calculate_account_monthly_yield(
        saldo_inicial=5000.0,
        daily_movements={},
        year=2026,
        month=12,
        cdi_annual_pct=10.75,
        percentual_cdi=100.0,
        reference_date=date(2026, 10, 31),
    )
    assert res_future.rendimento_acumulado == 0.0
    assert res_future.saldo_total == 5000.0
    assert res_future.dias_uteis == 0

    # Saldo zero ou negativo não deve gerar rendimento
    res_zero = calculate_account_monthly_yield(
        saldo_inicial=0.0,
        daily_movements={},
        year=2026,
        month=10,
        cdi_annual_pct=10.75,
        percentual_cdi=100.0,
        reference_date=date(2026, 10, 31),
    )
    assert res_zero.rendimento_acumulado == 0.0

    # 110% do CDI deve render mais que 100% do CDI
    res_100 = calculate_account_monthly_yield(
        saldo_inicial=10000.0,
        daily_movements={},
        year=2026,
        month=10,
        cdi_annual_pct=10.75,
        percentual_cdi=100.0,
        reference_date=date(2026, 10, 31),
    )
    res_110 = calculate_account_monthly_yield(
        saldo_inicial=10000.0,
        daily_movements={},
        year=2026,
        month=10,
        cdi_annual_pct=10.75,
        percentual_cdi=110.0,
        reference_date=date(2026, 10, 31),
    )
    assert res_110.rendimento_acumulado > res_100.rendimento_acumulado


def test_account_repository_cdb_yield_integration(tmp_path) -> None:
    from pathlib import Path
    from app.database.connection_manager import ConnectionManager
    from app.database.repositories.account_repository import AccountRepository
    from app.config.app_settings import AppSettings

    db_path = tmp_path / "test_cdb.sqlite"
    settings = AppSettings.load(tmp_path / "settings.json")
    settings.cdi_taxa_anual = 10.75
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_path)

    repo = AccountRepository(db)
    acc_id = repo.create_account(
        descricao="Minha Caixinha Nubank",
        saldo_inicial=5000.0,
        tipo_rendimento="CDB_CDI",
        percentual_cdi=100.0,
        mes_inicial=10,
        ano_inicial=2026,
    )

    summary = repo.get_account_summary(acc_id, mes=10, ano=2026)
    assert summary is not None
    assert summary.is_cdb is True
    assert summary.tipo_rendimento == "CDB_CDI"
    assert summary.percentual_cdi == 100.0
    assert summary.saldo_aportado == 5000.0
    assert summary.rendimento_acumulado > 0.0
    assert summary.saldo_atual == round(5000.0 + summary.rendimento_acumulado, 2)

    # Conta padrão tradicional sem CDB
    acc_std_id = repo.create_account(
        descricao="Conta Corrente Comum",
        saldo_inicial=1500.0,
        tipo_rendimento="NENHUM",
        mes_inicial=10,
        ano_inicial=2026,
    )
    std_summary = repo.get_account_summary(acc_std_id, mes=10, ano=2026)
    assert std_summary.is_cdb is False
    assert std_summary.rendimento_acumulado == 0.0
    assert std_summary.saldo_atual == 1500.0

    # Atualização para 110% do CDI
    repo.update_account(
        account_id=acc_id,
        descricao="Minha Caixinha Atualizada",
        id_categoria="3",
        tipo_rendimento="CDB_CDI",
        percentual_cdi=110.0,
    )
    updated = repo.get_account_summary(acc_id, mes=10, ano=2026)
    assert updated.descricao == "Minha Caixinha Atualizada"
    assert updated.percentual_cdi == 110.0
    assert updated.rendimento_acumulado > summary.rendimento_acumulado


def test_account_dialog_cdb_controls(qapp, tmp_path) -> None:
    from app.database.connection_manager import ConnectionManager
    from app.config.app_settings import AppSettings
    from app.ui.views.contas_view import AccountFormDialog

    db_path = tmp_path / "test_dlg.sqlite"
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_path)

    dlg = AccountFormDialog(db=db, profile_id="1", mes=10, ano=2026)
    assert hasattr(dlg, "chk_cdb")
    assert hasattr(dlg, "sp_percentual_cdi")
    assert not dlg.sp_percentual_cdi.isEnabled()

    # Ao marcar, habilita o spin box
    dlg.chk_cdb.setChecked(True)
    assert dlg.sp_percentual_cdi.isEnabled()
    assert dlg.sp_percentual_cdi.value() == 100.0

    dlg.close()


def test_configuracoes_cdi_rate_update(qapp, tmp_path) -> None:
    from app.database.connection_manager import ConnectionManager
    from app.config.app_settings import AppSettings
    from app.ui.views.configuracoes_hub_view import InvestimentosConfigTab

    db_path = tmp_path / "test_cfg.sqlite"
    settings = AppSettings.load(tmp_path / "settings.json")
    settings.cdi_taxa_anual = 10.75
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_path)

    env_changed = False
    def on_change():
        nonlocal env_changed
        env_changed = True

    tab = InvestimentosConfigTab(db, on_change)
    assert hasattr(tab, "sp_cdi_taxa")
    assert tab.sp_cdi_taxa.value() == 10.75

    # Altera taxa e salva
    tab.sp_cdi_taxa.setValue(12.25)
    tab._on_save_cdi_rate()
    assert db.settings.cdi_taxa_anual == 12.25
    assert env_changed is True
    tab.close()


def test_contas_view_cdb_rendering(qapp, tmp_path) -> None:
    from app.database.connection_manager import ConnectionManager
    from app.config.app_settings import AppSettings
    from app.database.repositories.account_repository import AccountRepository
    from app.ui.views.contas_view import ContasView

    db_path = tmp_path / "test_cv.sqlite"
    settings = AppSettings.load(tmp_path / "settings.json")
    settings.cdi_taxa_anual = 10.75
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_path)

    repo = AccountRepository(db)
    repo.create_account(
        descricao="Caixinha Reserva",
        saldo_inicial=10000.0,
        tipo_rendimento="CDB_CDI",
        percentual_cdi=100.0,
        mes_inicial=10,
        ano_inicial=2026,
    )

    cv = ContasView(db, get_context=lambda: ("1", 10, 2026, ""))
    cv.refresh_data()

    assert cv.table.rowCount() >= 1

    # Localiza a linha da Caixinha CDB
    cdb_row = -1
    for r in range(cv.table.rowCount()):
        if "Caixinha Reserva" in cv.table.item(r, 0).text():
            cdb_row = r
            break
    assert cdb_row >= 0

    it_desc = cv.table.item(cdb_row, 0)
    assert "[CDB 100%]" in it_desc.text()
    assert "Caixinha CDB" in it_desc.toolTip()
    assert "Capital Aportado" in it_desc.toolTip()

    # Categoria
    it_cat = cv.table.item(cdb_row, 1)
    assert "CDB 100% CDI" in it_cat.text()

    # Saldo com juros no resumo de investimentos
    assert "10." in cv.lbl_val_invest.text()
    cv.close()
