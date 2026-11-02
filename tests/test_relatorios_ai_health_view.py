"""Testes de interface gráfica do Diagnóstico & Saúde Financeira com IA na RelatoriosView (Etapa 5)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

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

    # 6. Simula erro amigável
    panel._on_worker_error("Limite de requisições excedido")
    assert "Limite de requisições excedido" in panel.lbl_status.text()
    assert panel.btn_generate.isEnabled()
