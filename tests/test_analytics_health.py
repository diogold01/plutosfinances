"""Testes automatizados do Agregador de Saúde Financeira (Etapa 1 - AnalyticsService)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.config.app_settings import AppSettings
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.analytics_service import (
    AnalyticsService,
    CategoryHealthMetric,
    FinancialHealthData,
)
from app.domain.services.transaction_service import TransactionService


def _setup_test_db(tmp_path: Path) -> ConnectionManager:
    db_file = tmp_path / "test_health.sqlite"
    cfg_file = tmp_path / "settings.json"
    settings = AppSettings.load(cfg_file)
    settings.active_db_path = str(db_file)
    settings.save()
    conn = ConnectionManager(settings=settings, auto_connect=False)
    conn.create_new_database(db_file, overwrite=True)
    return conn


def test_is_essential_category():
    assert AnalyticsService._is_essential_category("Alimentação & Mercado") is True
    assert AnalyticsService._is_essential_category("Supermercado") is True
    assert AnalyticsService._is_essential_category("Aluguel e Condomínio") is True
    assert AnalyticsService._is_essential_category("Farmácia / Saúde") is True
    assert AnalyticsService._is_essential_category("Combustível") is True
    assert AnalyticsService._is_essential_category("Energia Elétrica") is True

    # Não essenciais (estilo de vida / supérfluos)
    assert AnalyticsService._is_essential_category("Restaurante e Bares") is False
    assert AnalyticsService._is_essential_category("Viagens") is False
    assert AnalyticsService._is_essential_category("Streaming e Jogos") is False
    assert AnalyticsService._is_essential_category("Vestuário e Roupas") is False


def test_financial_health_summary_and_ai_payload(tmp_path: Path):
    conn = _setup_test_db(tmp_path)
    tx_srv = TransactionService(conn)
    cat_repo = CategoryRepository(conn)
    acc_repo = AccountRepository(conn)
    analytics = AnalyticsService(conn, tx_service=tx_srv)

    acc_id = acc_repo.create_account("Conta Corrente", saldo_inicial=0.0)

    # Cria categorias
    c_mercado = cat_repo.create_category(KIND_DESPESA, "Mercado", color_hex="#4CAF50")
    c_lazer = cat_repo.create_category(KIND_DESPESA, "Lazer", color_hex="#E91E63")
    c_salario = cat_repo.create_category(KIND_RECEITA, "Salário", color_hex="#2196F3")

    # Mês retrasado (08/2026): Mercado 500, Lazer 200
    tx_srv.create_expense(
        descricao="Compras Ago",
        valor=500.0,
        data_vencimento=date(2026, 8, 10),
        id_conta=acc_id,
        id_categoria=c_mercado.id,
        pago=True,
    )
    tx_srv.create_expense(
        descricao="Cinema Ago",
        valor=200.0,
        data_vencimento=date(2026, 8, 15),
        id_conta=acc_id,
        id_categoria=c_lazer.id,
        pago=True,
    )

    # Mês anterior (09/2026): Mercado 500, Lazer 200
    tx_srv.create_expense(
        descricao="Compras Set",
        valor=500.0,
        data_vencimento=date(2026, 9, 10),
        id_conta=acc_id,
        id_categoria=c_mercado.id,
        pago=True,
    )
    tx_srv.create_expense(
        descricao="Cinema Set",
        valor=200.0,
        data_vencimento=date(2026, 9, 15),
        id_conta=acc_id,
        id_categoria=c_lazer.id,
        pago=True,
    )

    # Mês atual (10/2026):
    # Receita: 5000 Salário
    # Despesa Essencial (Mercado): 750 (+50% vs média 500)
    # Despesa Estilo de Vida (Lazer): 250 (+25% vs média 200)
    tx_srv.create_income(
        descricao="Salário Out",
        valor=5000.0,
        data=date(2026, 10, 5),
        id_conta=acc_id,
        id_categoria=c_salario.id,
        recebido=True,
    )
    tx_srv.create_expense(
        descricao="Supermercado Out",
        valor=750.0,
        data_vencimento=date(2026, 10, 10),
        id_conta=acc_id,
        id_categoria=c_mercado.id,
        pago=True,
    )
    tx_srv.create_expense(
        descricao="Passeios Out",
        valor=250.0,
        data_vencimento=date(2026, 10, 15),
        id_conta=acc_id,
        id_categoria=c_lazer.id,
        pago=True,
    )

    summary = analytics.get_financial_health_summary(2026, 10, profile_id="1")

    # Validações dos totais
    assert summary.total_receitas == 5000.0
    assert summary.total_despesas == 1000.0
    assert summary.resultado_liquido == 4000.0
    assert summary.despesas_essenciais == 750.0
    assert summary.despesas_estilo_vida == 250.0

    # Validação Regra 50-30-20
    # 750 / 5000 = 15.0%
    assert summary.percentual_essenciais == 15.0
    # 250 / 5000 = 5.0%
    assert summary.percentual_estilo_vida == 5.0
    # (5000 - 1000) / 5000 = 80.0%
    assert summary.percentual_poupanca == 80.0

    # Validações das categorias e variação percentual vs média dos 2 meses anteriores
    cat_map = {c.categoria_nome: c for c in summary.categorias}
    assert "Mercado" in cat_map
    assert cat_map["Mercado"].tipo_regra == "ESSENCIAL"
    assert cat_map["Mercado"].media_anterior_2m == 500.0
    assert cat_map["Mercado"].variacao_percentual == 50.0  # (750 - 500) / 500 * 100

    assert "Lazer" in cat_map
    assert cat_map["Lazer"].tipo_regra == "ESTILO_DE_VIDA"
    assert cat_map["Lazer"].media_anterior_2m == 200.0
    assert cat_map["Lazer"].variacao_percentual == 25.0  # (250 - 200) / 200 * 100

    # Validação do payload anonimizado para a IA
    payload = summary.to_ai_payload()
    assert payload["periodo"] == "10/2026"
    assert payload["totais"]["receitas"] == 5000.0
    assert payload["totais"]["despesas"] == 1000.0
    assert len(payload["historico_2_meses_anteriores"]) == 2
    assert "descricao" not in str(payload)  # Zero dados brutos
    assert "Compras Ago" not in str(payload)
    assert "Salário Out" not in str(payload)
