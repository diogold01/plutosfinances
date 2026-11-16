"""Testes de interface gráfica do Diagnóstico & Saúde Financeira com IA na RelatoriosView (Etapa 5)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from app.config.app_settings import AppSettings
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.ai_service import FinancialHealthReport
from app.domain.services.transaction_service import TransactionService
from app.ui.views.relatorios_view import FinancialHealthPanel, RelatoriosView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _setup_test_db(tmp_path: Path) -> ConnectionManager:
    db_file = tmp_path / "test_relatorios_health.sqlite"
    cfg_file = tmp_path / "settings.json"
    settings = AppSettings.load(cfg_file)
    settings.active_db_path = str(db_file)
    settings.save()
    conn = ConnectionManager(settings=settings, auto_connect=False)
    conn.create_new_database(db_file, overwrite=True)
    return conn


def test_relatorios_view_ai_health_navigation_and_rendering(qapp: QApplication, tmp_path: Path):
    conn = _setup_test_db(tmp_path)
    tx_srv = TransactionService(conn)
    cat_repo = CategoryRepository(conn)
    acc_repo = AccountRepository(conn)

    acc_id = acc_repo.create_account("Conta Teste", saldo_inicial=0.0)
    c_salario = cat_repo.create_category(KIND_RECEITA, "Salário", color_hex="#2196F3")
    c_mercado = cat_repo.create_category(KIND_DESPESA, "Mercado", color_hex="#4CAF50")

    # Mês 10/2026: Receita 4000, Despesa 1500
    tx_srv.create_income(
        descricao="Salário Out",
        valor=4000.0,
        data=date(2026, 10, 5),
        id_conta=acc_id,
        id_categoria=c_salario.id,
        recebido=True,
    )
    tx_srv.create_expense(
        descricao="Supermercado Out",
        valor=1500.0,
        data_vencimento=date(2026, 10, 10),
        id_conta=acc_id,
        id_categoria=c_mercado.id,
        pago=True,
    )

    context_fn = lambda: ("1", 10, 2026, "")
    view = RelatoriosView(conn, get_context=context_fn)
    view.show()

    # 1. Verifica presença da nova opção no combo box
    idx = view.cb_report_type.findData("AI_HEALTH")
    assert idx != -1

    # 2. Alterna para o relatório de IA
    view.cb_report_type.setCurrentIndex(idx)
    assert view.stack.currentWidget() == view.health_panel
    assert isinstance(view.stack.currentWidget(), FinancialHealthPanel)

    # 3. Verifica KPIs superiores
    assert "4.000,00" in view.kpi_confirmed.lbl_value.text()
    assert "1.500,00" in view.kpi_pending.lbl_value.text()
    assert "2.500,00" in view.kpi_total.lbl_value.text()

    # 4. Verifica estado vazio inicial do painel com as proporções locais
    panel: FinancialHealthPanel = view.health_panel
    assert panel.empty_card.isVisible()
    assert not panel.results_widget.isVisible()
    assert "10/2026" in panel.lbl_empty_title.text()
    assert "Essenciais" in panel.lbl_p_ess.text()

    # 5. Simula sucesso do worker com relatório completo da IA
    sample_report = FinancialHealthReport(
        score_saude=82,
        resumo="Balanço mensal excelente com alto índice de poupança (62.5%).",
        essenciais_pct=37.5,
        estilo_vida_pct=0.0,
        poupanca_pct=62.5,
        comentario_regra="Despesas essenciais bem dentro da meta de 50%.",
        alertas_anomalias=["Mercado apresentou leve aumento de 15%."],
        projecao_fechamento="Previsão de fechar o mês com superávit de R$ 2.500,00.",
        recomendacoes_praticas=[
            "Aportar o superávit na caixinha CDB 100% CDI.",
            "Monitorar despesas eventuais até o fechamento.",
        ],
    )
    panel._on_worker_success(sample_report)

    # Verifica transição de tela para resultados
    assert not panel.empty_card.isVisible()
    assert panel.results_widget.isVisible()
    assert panel.lbl_score_num.text() == "82"
    assert panel.badge_score_status.text() == "Saudável"
    assert panel.bar_ess.value() == 37
    assert panel.bar_pou.value() == 62
    assert "superávit" in panel.lbl_proj_text.text()
    assert panel.alerts_list_lay.count() == 1
    assert panel.recs_list_lay.count() == 2

    # Regressão visual: QFrame escopado para evitar cascata de borda/padding nos filhos
    alert_frame = panel.alerts_list_lay.itemAt(0).widget()
    assert isinstance(alert_frame, QFrame)
    assert alert_frame.objectName() == "HealthAlertFrame"
    assert "QFrame#HealthAlertFrame" in alert_frame.styleSheet()
    alert_labels = alert_frame.findChildren(QLabel)
    assert len(alert_labels) == 2
    assert all(
        "border: none" in lbl.styleSheet() and "padding: 0px" in lbl.styleSheet()
        for lbl in alert_labels
    )

    rec_frame = panel.recs_list_lay.itemAt(0).widget()
    assert isinstance(rec_frame, QFrame)
    assert rec_frame.objectName() == "HealthRecFrame"
    assert "QFrame#HealthRecFrame" in rec_frame.styleSheet()
    rec_labels = rec_frame.findChildren(QLabel)
    assert len(rec_labels) == 2
    lbl_num = next(lbl for lbl in rec_labels if lbl.text() == "1")
    assert "padding: 0px" in lbl_num.styleSheet()
    assert "border: none" in lbl_num.styleSheet()
    assert lbl_num.width() >= 22

    # 6. Simula erro amigável
    panel._on_worker_error("Limite de requisições excedido")
    assert "Limite de requisições excedido" in panel.lbl_status.text()
    assert panel.btn_generate.isEnabled()


def test_relatorios_ai_health_persistence_proactive_cards_and_copilot(
    qapp: QApplication, tmp_path: Path
) -> None:
    from app.domain.services.budget_service import BudgetService

    conn = _setup_test_db(tmp_path)
    tx_srv = TransactionService(conn)
    cat_repo = CategoryRepository(conn)
    acc_repo = AccountRepository(conn)
    budget_srv = BudgetService(conn, tx_srv)

    acc_id = acc_repo.create_account("Conta Corrente", saldo_inicial=1500.0)
    c_sal = cat_repo.create_category(KIND_RECEITA, "Salário", color_hex="#2196F3")
    c_merc = cat_repo.create_category(KIND_DESPESA, "Mercado", color_hex="#4CAF50")

    budget_srv.create_budget(meta=1000.0, id_categoria=c_merc.id, perc_alerta=80.0)
    tx_srv.create_income(
        descricao="Salário Out",
        valor=5000.0,
        data=date(2026, 10, 5),
        id_conta=acc_id,
        id_categoria=c_sal.id,
        recebido=True,
    )
    tx_srv.create_expense(
        descricao="Compras Out",
        valor=900.0,
        data_vencimento=date(2026, 10, 10),
        id_conta=acc_id,
        id_categoria=c_merc.id,
        pago=True,
    )

    state = {"month": 9, "year": 2026}
    view = RelatoriosView(conn, get_context=lambda: ("1", state["month"], state["year"], ""))
    view.show()

    idx = view.cb_report_type.findData("AI_HEALTH")
    assert idx != -1
    view.cb_report_type.setCurrentIndex(idx)
    panel: FinancialHealthPanel = view.health_panel

    # Grava relatório de Setembro (score 75)
    rep_sep = FinancialHealthReport(
        score_saude=75,
        resumo="Setembro estável.",
        essenciais_pct=45.0,
        estilo_vida_pct=25.0,
        poupanca_pct=30.0,
        comentario_regra="Equilibrado.",
        alertas_anomalias=[],
        projecao_fechamento="Fechamento positivo.",
        recomendacoes_praticas=["Manter disciplina."],
    )
    panel._on_worker_success(rep_sep)
    ok_frame = panel.alerts_list_lay.itemAt(0).widget()
    assert isinstance(ok_frame, QFrame)
    assert ok_frame.objectName() == "HealthAlertOkFrame"
    assert "QFrame#HealthAlertOkFrame" in ok_frame.styleSheet()

    # Alterna para Outubro: sem relatório salvo ainda, mas cards 30/60/90d e radar já aparecem
    state["month"] = 10
    view.refresh_data()
    assert panel.empty_card.isVisible()
    assert not panel.results_widget.isVisible()
    assert "30 dias" in panel.lbl_cash_30d.text()
    assert "60 dias" in panel.lbl_cash_60d.text()
    assert "90 dias" in panel.lbl_cash_90d.text()
    assert "orçamento" in panel.lbl_proactive_alerts.text().lower()

    # Conclui geração em Outubro (score 88 -> delta +13 vs Setembro)
    rep_oct = FinancialHealthReport(
        score_saude=88,
        resumo="Outubro muito saudável.",
        essenciais_pct=40.0,
        estilo_vida_pct=20.0,
        poupanca_pct=40.0,
        comentario_regra="Acima da meta.",
        alertas_anomalias=[],
        projecao_fechamento="Sobra confortável.",
        recomendacoes_praticas=["Investir sobra mensal."],
    )
    panel._on_worker_success(rep_oct)
    assert panel.lbl_score_delta.isVisible()
    assert "+13 pts" in panel.lbl_score_delta.text()

    # Troca para Novembro (vazio) e volta para Outubro -> carrega automaticamente do SQLite
    state["month"] = 11
    view.refresh_data()
    assert panel.empty_card.isVisible()
    assert not panel.results_widget.isVisible()

    state["month"] = 10
    view.refresh_data()
    assert not panel.empty_card.isVisible()
    assert panel.results_widget.isVisible()
    assert panel.lbl_score_num.text() == "88"
    assert "+13 pts" in panel.lbl_score_delta.text()

    # Fluxo do Copiloto Financeiro
    assert len(panel.copilot_chips) == 3
    assert all(not chip.text().startswith("+ ") for chip in panel.copilot_chips)
    panel._on_copilot_success("Você fecha o mês com folga estimada de R$ 4.100,00.")
    assert panel.lbl_copilot_answer.isVisible()
    assert "4.100,00" in panel.lbl_copilot_answer.text()
    assert panel.btn_ask_copilot.isEnabled()

    panel._on_copilot_error("Tempo limite excedido")
    assert "Tempo limite excedido" in panel.lbl_copilot_answer.text()
    assert panel.btn_ask_copilot.isEnabled()

    conn.close()
