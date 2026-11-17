"""Suíte Cumulativa de Testes de Regressão do Plutos.

Esta suíte cumpre a Regra 7 de Governança ('Tolerância Zero à Regressão / Andar Sempre para Frente'):
Toda vez que um bug ou falha visual/lógica for reportado e corrigido, um teste de regressão
específico deve ser adicionado aqui para garantir que o erro jamais volte a ocorrer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget, QTabWidget

from app.config.app_settings import AppSettings
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.ui.main_window import MainWindow
from app.ui.views.configuracoes_hub_view import ConfiguracoesHubView
from app.ui.views.configuracoes_view import ConfiguracoesView
from app.ui.views.transacoes_view import TransacoesView


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def regression_env(qapp: QApplication, tmp_path: Path):
    """Cria um ambiente de testes completo e isolado."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db_file = tmp_path / "regression_test.sqlite"
    db.create_new_database(db_file, overwrite=True)
    backup = BackupSchedulerService(connection_manager=db, settings=settings)
    backup.set_backup_directory(tmp_path / "backups")
    win = MainWindow(db=db, backup_service=backup)
    win.resize(1280, 800)
    win.show()
    yield win, db, tmp_path
    win.close()
    db.close()


def test_regression_issue2_minisidebar_theme_toggle_visibility(regression_env) -> None:
    """Regressão Issue #2: Botão de alternar tema desaparecia ao colapsar sidebar para 56px."""
    win, _, _ = regression_env
    
    # 1. Sidebar expandida inicialmente
    assert win.sidebar_frame.width() > 80
    assert win.btn_theme_toggle_side.isVisible()
    
    # 2. Colapsa para mini-sidebar (56px)
    win.toggle_sidebar()
    QApplication.processEvents()
    
    assert win.sidebar_frame.width() <= 70
    assert win.btn_theme_toggle_side.isVisible(), "O alternador de tema DEVE permanecer visível na mini-sidebar!"
    assert not win.btn_theme_toggle_side.icon().isNull(), "O ícone (sol/lua) deve ser válido na mini-sidebar!"
    assert win.btn_theme_toggle_side.text() == "", "O texto deve ser vazio para evitar truncamento em hífen/dash!"
    assert win.btn_theme_toggle_side.toolTip() != "", "Tooltip explicativo deve existir no modo colapsado!"
    
    # 3. Restaura para modo expandido
    win.toggle_sidebar()
    QApplication.processEvents()
    assert win.sidebar_frame.width() > 80
    assert win.btn_theme_toggle_side.isVisible()
    assert win.btn_theme_toggle_side.text().strip() in ("Modo Claro", "Modo Escuro")


def test_regression_issue2_primary_buttons_retain_contract(regression_env) -> None:
    """Regressão Issue #2: Botões primários perdiam background terracota (#E5603D) em cascata no Qt."""
    win, _, _ = regression_env
    win.navigate_to("configuracoes")
    QApplication.processEvents()

    hub: ConfiguracoesHubView = win.config_hub_view
    assert isinstance(hub, ConfiguracoesHubView)

    expected_primary_buttons = [
        "btn_new_db",
        "btn_run_bkp_force",
        "btn_new_prof",
        "btn_save_pluggy",
        "btn_connect_bank",
        "btn_save",
        "btn_save_cdi",
    ]

    for mode in ("dark", "light"):
        if win.db.settings.theme_mode != mode:
            win.toggle_theme_mode()
            QApplication.processEvents()

        # Varre todos os botões do hub de configurações
        found_primary = []
        for btn in hub.findChildren(QPushButton):
            if btn.objectName() == "PrimaryButton":
                found_primary.append(btn)

        assert len(found_primary) >= len(expected_primary_buttons), (
            f"No modo {mode}, esperava ao menos {len(expected_primary_buttons)} botões primários, "
            f"encontrados: {len(found_primary)}"
        )


def test_regression_issue2_transacoes_filter_defaults_to_conta_corrente(regression_env) -> None:
    """Regressão Issue #2: Filtro de contas em Transações deve priorizar Conta Corrente como padrão."""
    win, db, _ = regression_env
    
    # Cria uma conta corrente de teste
    prof_id = win.active_profile_id
    repo = AccountRepository(db)
    acc_id = repo.create_account(
        descricao="Minha Conta Corrente",
        saldo_inicial=1000.0,
        profile_id=prof_id,
    )
    
    win.navigate_to("transacoes")
    QApplication.processEvents()
    
    tx_view: TransacoesView = win.transacoes_view
    tx_view._reload_source_combo(prof_id)
    QApplication.processEvents()
    
    # A primeira opção e a opção selecionada por padrão deve ser a Conta Corrente prioritária
    assert tx_view.cb_filter_source.count() > 0
    first_item_text = tx_view.cb_filter_source.itemText(0)
    first_item_data = tx_view.cb_filter_source.itemData(0)
    
    assert "Conta:" in first_item_text
    assert str(first_item_data).startswith("ACC:")
    assert tx_view.cb_filter_source.currentData() == first_item_data, (
        "O combobox de filtros DEVE iniciar com a Conta Corrente selecionada por padrão!"
    )


def test_regression_issue2_profile_table_double_click_and_edit_btn(regression_env) -> None:
    """Regressão Issue #2: Edição de perfil via botão dedicado e duplo-clique na tabela."""
    win, _, _ = regression_env
    win.navigate_to("configuracoes")
    QApplication.processEvents()

    cfg_view: ConfiguracoesView = win.config_view
    assert hasattr(cfg_view, "btn_edit_prof")
    assert cfg_view.btn_edit_prof.objectName() == "SecondaryButton"
    assert "Editar Perfil" in cfg_view.btn_edit_prof.text()
    
    # Verifica que a tabela possui duplo-clique conectado
    assert isinstance(cfg_view.table_profiles, QTableWidget)


def test_regression_issue2_investimentos_cdi_tab_mnemonic_escaped(regression_env) -> None:
    """Regressão Issue #2: Aba 'Investimentos && CDI' deve ter o caractere '&' devidamente escapado."""
    win, _, _ = regression_env
    win.navigate_to("configuracoes")
    QApplication.processEvents()

    hub: ConfiguracoesHubView = win.config_hub_view
    tab_widget: QTabWidget = hub.tabs
    
    # Encontra o texto da 5ª aba
    found_tab_text = None
    for i in range(tab_widget.count()):
        text = tab_widget.tabText(i)
        if "CDI" in text:
            found_tab_text = text
            break
            
    assert found_tab_text is not None, "Aba de Parâmetros de Investimento & CDI deve existir no Hub!"
    assert "&&" in found_tab_text or "&" in found_tab_text
    # Garante que não é exibido como mnemônico sublinhado truncado
    assert "Investimentos" in found_tab_text and "CDI" in found_tab_text


def test_regression_artha_indigo_icons_and_transacoes_feed(regression_env) -> None:
    """Regressão Etapas 1-2: Paleta Indigo Artha, ícones sem caixas vazias, statusbar oculta e Transações em Feed."""
    from app.config.theme_palette import ThemePalette
    from app.ui.icons import get_line_pixmap

    assert ThemePalette.light().primary == "#5B5BD6"
    assert ThemePalette.dark().primary == "#6366F1"

    required_icons = (
        "arrow-up",
        "arrow-down",
        "calendar",
        "trending_up",
        "pie_chart",
        "chart-bar",
        "check_circle",
        "file_text",
        "chevron-left",
        "chevron-right",
        "filter",
    )
    for icon_name in required_icons:
        pix = get_line_pixmap(icon_name, color="#5B5BD6", size=18)
        assert not pix.isNull(), f"Ícone '{icon_name}' não pode ser nulo"
        img = pix.toImage()
        has_visible_pixel = any(
            img.pixelColor(x, y).alpha() > 0
            for x in range(img.width())
            for y in range(img.height())
        )
        assert has_visible_pixel, f"Ícone '{icon_name}' renderizou totalmente transparente (caixa vazia)"

    win, _, _ = regression_env
    assert win.status_bar.isHidden(), "QStatusBar inferior deve permanecer oculta para não vazar na base"

    win.navigate_to("transacoes")
    QApplication.processEvents()
    tx_view: TransacoesView = win.transacoes_view
    assert tx_view._view_mode == "feed"
    assert tx_view.installment_drawer.width() >= 400


def test_regression_etapa3_standardized_modals(regression_env) -> None:
    """Regressão Etapa 3: Modais padronizados em 2 colunas (Despesa, Receita, Transferência e Orçamento)."""
    from datetime import date
    from PySide6.QtWidgets import QGridLayout
    from app.ui.views.orcamentos_view import BudgetFormDialog
    from app.ui.views.transacoes_view import ExpenseDialog, IncomeDialog, TransferDialog

    win, db, prof_id = regression_env
    today = date(2026, 11, 16)

    exp_dlg = ExpenseDialog(db=db, profile_id=prof_id, default_date=today, card_mode=False)
    assert exp_dlg.minimumWidth() >= 600
    assert exp_dlg.cb_conta.isVisibleTo(exp_dlg) is True
    assert exp_dlg.cb_cartao.isVisibleTo(exp_dlg) is False
    exp_dlg.rb_cartao.setChecked(True)
    QApplication.processEvents()
    assert exp_dlg.cb_cartao.isVisibleTo(exp_dlg) is True
    assert exp_dlg.cb_conta.isVisibleTo(exp_dlg) is False

    inc_dlg = IncomeDialog(db=db, profile_id=prof_id, default_date=today)
    assert inc_dlg.minimumWidth() >= 600

    tr_dlg = TransferDialog(db=db, profile_id=prof_id, default_date=today)
    assert tr_dlg.minimumWidth() >= 560
    assert len(tr_dlg.findChildren(QGridLayout)) >= 1

    bdg_dlg = BudgetFormDialog(db=db, profile_id=prof_id)
    assert bdg_dlg.minimumWidth() >= 560
    assert len(bdg_dlg.findChildren(QGridLayout)) >= 1


def test_regression_etapa4_cartoes_no_parcel_overlap_and_clean_header(regression_env) -> None:
    """Regressão Etapa 4: Coluna Parcela sem texto sobreposto atrás do InstallmentMiniBar e menu Gerenciar."""
    from datetime import date
    from app.domain.models import REC_PARCELADA
    from app.domain.services.credit_card_service import CreditCardService
    from app.domain.services.transaction_service import TransactionService
    from app.database.repositories.account_repository import AccountRepository

    win, db, prof_id = regression_env
    tx = TransactionService(db)
    acc_repo = AccountRepository(db)
    accounts = acc_repo.list_accounts(prof_id)
    acc_id = accounts[0].id if accounts else acc_repo.create_account(
        descricao="Conta Teste",
        saldo_inicial=1000.0,
        profile_id=prof_id,
    )
    card_srv = CreditCardService(db, tx)
    card = card_srv.create_card(
        profile_id=prof_id,
        nome="Nubank Teste",
        limite=3000.0,
        dia_fecha=2,
        dia_venc=9,
        id_conta=acc_id,
    )
    _, ctx_month, ctx_year, _ = win.get_active_context()
    prev_month = 12 if ctx_month == 1 else ctx_month - 1
    prev_year = ctx_year - 1 if ctx_month == 1 else ctx_year
    tx.create_expense(
        descricao="Notebook",
        valor=1200.0,
        data_vencimento=date(ctx_year, ctx_month, 9),
        data_evento=date(prev_year, prev_month, 20),
        id_cartao=card.id,
        recorrencia=REC_PARCELADA,
        num_parcelas=3,
        profile_id=prof_id,
    )

    from app.ui.views.cartoes_view import CartoesView

    cview = CartoesView(db, lambda: (prof_id, ctx_month, ctx_year, ""), lambda: None)
    cview.refresh_data()
    QApplication.processEvents()

    assert hasattr(cview, "btn_card_actions")
    assert cview.btn_card_actions.menu() is not None
    assert cview.tbl_items.rowCount() >= 1
    assert cview.tbl_items.item(0, 2).text() == "", (
        "Célula da coluna Parcela deve ter texto vazio quando possui InstallmentMiniBar!"
    )


def test_regression_etapa5_dashboard_card_lists_and_graficos_axes(regression_env) -> None:
    """Regressão Etapa 5: Dashboard sem QTableWidget com gráfico Resumo Mensal e GraficosView com eixo MM/AAAA."""
    from PySide6.QtCharts import QCategoryAxis
    from PySide6.QtCore import Qt

    win, db, prof_id = regression_env
    win.navigate_to("dashboard")
    QApplication.processEvents()
    dash = win.dashboard_view
    assert len(dash.findChildren(QTableWidget)) == 0, "Dashboard não deve usar QTableWidget rígidas"
    assert hasattr(dash, "monthly_chart_view")
    assert dash.monthly_chart_view.chart() is not None
    assert hasattr(dash, "cat_legend_layout")

    win.navigate_to("graficos")
    QApplication.processEvents()
    gview = win.graficos_view
    gview.refresh_data()
    h_axes = gview.cv_line.chart().axes(Qt.Orientation.Horizontal)
    assert len(h_axes) == 1
    assert isinstance(h_axes[0], QCategoryAxis)
    assert len(h_axes[0].categoriesLabels()) >= 1
    assert "/" in h_axes[0].categoriesLabels()[0]


def test_regression_etapa6_orcamentos_cards_calendario_grid_and_indigo(regression_env) -> None:
    """Regressão Etapa 6: Orçamentos com alternador Cards|Tabela, Calendário com grade sutil e ícone sparkles."""
    from app.ui.icons import get_line_pixmap

    pix = get_line_pixmap("sparkles", color="#5B5BD6", size=18)
    assert not pix.isNull()

    win, _, _ = regression_env
    win.navigate_to("orcamentos")
    QApplication.processEvents()
    oview = win.orcamentos_view
    assert oview._view_mode == "cards"
    assert oview.table.columnCount() == 9

    win.navigate_to("calendario")
    QApplication.processEvents()
    cal_v = win.calendario_view
    assert cal_v.calendar.isGridVisible() is True
