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


def test_proactive_projections_budgets_cards_goals_and_report_persistence(
    tmp_path: Path,
) -> None:
    from app.domain.models import REC_PARCELADA
    from app.domain.services.ai_service import FinancialHealthReport
    from app.domain.services.budget_service import BudgetService
    from app.domain.services.credit_card_service import CreditCardService
    from app.domain.services.goal_service import GoalService

    conn = _setup_test_db(tmp_path)
    tx_srv = TransactionService(conn)
    cat_repo = CategoryRepository(conn)
    acc_repo = AccountRepository(conn)
    budget_srv = BudgetService(conn, tx_srv)
    card_srv = CreditCardService(conn, tx_srv)
    goal_srv = GoalService(conn)
    analytics = AnalyticsService(conn, tx_service=tx_srv)

    acc_id = acc_repo.create_account("Conta Principal", saldo_inicial=1000.0)
    c_alim = cat_repo.create_category(KIND_DESPESA, "Alimentação Extra", color_hex="#4CAF50")
    c_sal = cat_repo.create_category(KIND_RECEITA, "Salário Principal", color_hex="#2196F3")

    card = card_srv.create_card(
        nome="Cartão Teste",
        limite=5000.0,
        dia_fecha=5,
        dia_venc=12,
        id_conta=acc_id,
    )

    # Orçamento de R$ 500 e gasto de R$ 450 (90% -> Em Alerta)
    budget_srv.create_budget(meta=500.0, id_categoria=c_alim.id, perc_alerta=80.0)
    tx_srv.create_expense(
        descricao="Supermercado Semanal",
        valor=450.0,
        data_vencimento=date(2026, 10, 10),
        id_conta=acc_id,
        id_categoria=c_alim.id,
        pago=True,
    )

    # Receita prevista em 11/2026 e parcelamento em cartão para 11/2026 e 12/2026
    tx_srv.create_income(
        descricao="Salário Nov",
        valor=4000.0,
        data=date(2026, 11, 5),
        id_conta=acc_id,
        id_categoria=c_sal.id,
        recebido=False,
    )
    tx_srv.create_expense(
        descricao="Notebook Parcelado",
        valor=1200.0,
        data_vencimento=date(2026, 11, 12),
        data_evento=date(2026, 10, 1),
        id_cartao=card.id,
        id_categoria=c_alim.id,
        recorrencia=REC_PARCELADA,
        num_parcelas=2,
        preserve_due_date=True,
    )

    # Objetivo financeiro ativo
    goal_srv.create_goal(
        descricao="Reserva de Emergência",
        meta=10000.0,
        saldo_inicial=2500.0,
        data_expectativa=date(2027, 10, 1),
    )

    summary = analytics.get_financial_health_summary(2026, 10, profile_id="1")

    assert len(summary.projecao_caixa_30_60_90) == 3
    assert [p["horizonte"] for p in summary.projecao_caixa_30_60_90] == ["30d", "60d", "90d"]
    assert [p["periodo"] for p in summary.projecao_caixa_30_60_90] == [
        "11/2026",
        "12/2026",
        "01/2027",
    ]
    assert summary.projecao_caixa_30_60_90[0]["receitas_previstas"] == 4000.0
    assert summary.projecao_caixa_30_60_90[0]["faturas_cartao"] == 600.0

    assert len(summary.comprometimento_cartoes_futuro) == 3
    assert summary.comprometimento_cartoes_futuro[0]["total_faturas"] == 600.0
    assert summary.comprometimento_cartoes_futuro[1]["total_faturas"] == 600.0

    assert len(summary.orcamentos_em_risco) == 1
    assert summary.orcamentos_em_risco[0]["alvo"] == "Alimentação Extra"
    assert summary.orcamentos_em_risco[0]["status"] == "Em Alerta"

    assert len(summary.objetivos_ativos) == 1
    assert summary.objetivos_ativos[0]["objetivo"] == "Reserva de Emergência"
    assert summary.objetivos_ativos[0]["restante"] == 7500.0

    payload = summary.to_ai_payload()
    assert "projecao_caixa_30_60_90" in payload
    assert "orcamentos_em_risco" in payload
    assert "comprometimento_cartoes_futuro" in payload
    assert "objetivos_ativos" in payload
    assert "descricao" not in str(payload)
    assert "Supermercado Semanal" not in str(payload)
    assert "Notebook Parcelado" not in str(payload)

    # Persistência em SQLite por competência e evolução de score
    rep_sep = FinancialHealthReport(
        score_saude=74,
        resumo="Setembro equilibrado.",
        essenciais_pct=48.0,
        estilo_vida_pct=28.0,
        poupanca_pct=24.0,
        comentario_regra="Dentro da meta.",
        alertas_anomalias=[],
        projecao_fechamento="Fechamento positivo.",
        recomendacoes_praticas=["Manter aportes na reserva."],
    )
    rep_oct = FinancialHealthReport(
        score_saude=86,
        resumo="Outubro saudável.",
        essenciais_pct=42.0,
        estilo_vida_pct=20.0,
        poupanca_pct=38.0,
        comentario_regra="Ótima poupança.",
        alertas_anomalias=["Alimentação Extra em 90% do orçamento."],
        projecao_fechamento="Sobra prevista.",
        recomendacoes_praticas=["Acompanhar faturas de 11/2026."],
    )
    analytics.save_health_report(2026, 9, rep_sep, profile_id="1")
    analytics.save_health_report(2026, 10, rep_oct, profile_id="1")

    loaded_oct = analytics.load_health_report(2026, 10, profile_id="1")
    assert loaded_oct is not None
    assert loaded_oct.score_saude == 86
    assert loaded_oct.resumo == "Outubro saudável."
    assert analytics.get_previous_health_score(2026, 10, profile_id="1") == 74

    # Atualização idempotente (UPSERT) na mesma competência
    rep_oct_v2 = FinancialHealthReport(
        score_saude=91,
        resumo="Outubro revisado.",
        essenciais_pct=40.0,
        estilo_vida_pct=20.0,
        poupanca_pct=40.0,
        comentario_regra="Excelente.",
        alertas_anomalias=[],
        projecao_fechamento="Superávit consolidado.",
        recomendacoes_praticas=["Direcionar excedente para objetivos."],
    )
    analytics.save_health_report(2026, 10, rep_oct_v2, profile_id="1")
    assert analytics.load_health_report(2026, 10, profile_id="1").score_saude == 91  # type: ignore[union-attr]
    conn.close()
