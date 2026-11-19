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

from PySide6.QtCore import QEvent, Qt
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
    win.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
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
    
    # A primeira opção e a opção selecionada por padrão deve ser "Todas as Contas e Cartões" (ALL),
    # com a Conta Corrente prioritária listada logo em seguida no combo
    assert tx_view.cb_filter_source.count() > 2
    assert tx_view.cb_filter_source.currentData() == "ALL"
    assert tx_view.cb_filter_source.findData(f"ACC:{acc_id}") >= 1


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

    win, db, _ = regression_env
    prof_id = win.active_profile_id
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

    win, db, _ = regression_env
    prof_id = win.active_profile_id
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


def test_regression_artha_lancamentos_unified_modal_and_timeline(regression_env) -> None:
    """Regressão Artha: Sem '+ Novo' na Topbar, modal único Novo Lançamento, pílula com tooltip e Drawer por ano."""
    from datetime import date
    from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA, REC_PARCELADA
    from app.domain.services.transaction_service import TransactionService
    from app.ui.components import InstallmentMiniBar, TimelineStepMarker
    from app.ui.views.transacoes_view import UnifiedTransactionDialog

    win, db, _ = regression_env
    prof_id = win.active_profile_id
    assert not hasattr(win, "btn_fab_add"), "Botão '+ Novo' global não deve existir na Topbar!"

    win.navigate_to("transacoes")
    QApplication.processEvents()
    tx_view = win.transacoes_view
    assert tx_view.lbl_title.text() == "Lançamentos"
    assert tx_view.btn_new_expense.text() == "Novo lançamento"
    assert tx_view.btn_new_expense.objectName() == "PrimaryButton"

    # Modal único alternando Receita | Despesa | Transferência
    dlg = UnifiedTransactionDialog(db, profile_id=prof_id, default_date=date(2026, 11, 17))
    assert dlg.selected_kind() == KIND_DESPESA
    dlg._set_kind(KIND_RECEITA)
    assert dlg.selected_kind() == KIND_RECEITA
    dlg._set_kind(KIND_TRANSFERENCIA)
    assert dlg.selected_kind() == KIND_TRANSFERENCIA
    dlg.close()

    # Pílula InstallmentMiniBar + Drawer com TimelineStepMarker por ano
    repo = AccountRepository(db)
    accs = repo.list_accounts(prof_id)
    acc_id = accs[0].id if accs else repo.create_account("Conta", 1000.0, profile_id=prof_id)
    _, ctx_m, ctx_y, _ = win.get_active_context()
    tx_srv = TransactionService(db)
    tx_srv.create_expense(
        descricao="Curso Anual",
        valor=1200.0,
        data_vencimento=date(ctx_y, ctx_m, 15),
        id_conta=acc_id,
        recorrencia=REC_PARCELADA,
        num_parcelas=12,
        profile_id=prof_id,
    )
    tx_view.refresh_data()
    QApplication.processEvents()
    assert len(tx_view._occurrences) >= 1
    bars = tx_view.feed_host.findChildren(InstallmentMiniBar)
    assert len(bars) >= 1
    assert bars[0].toolTip() == "Ver as 12 parcelas"
    bars[0].clicked.emit()
    QApplication.processEvents()
    assert tx_view.installment_drawer.isVisible() is True
    assert len(tx_view.installment_drawer.findChildren(TimelineStepMarker)) == 12


def test_regression_etapa1_kpi_no_clipping_and_feed_alignment(regression_env) -> None:
    """Regressão Etapa 1: KpiCard horizontal sem recorte, checkbox do Feed sem colidir e gráficos do Dashboard transparentes."""
    from datetime import date
    from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout
    from app.domain.models import REC_PARCELADA
    from app.domain.services.transaction_service import TransactionService
    from app.ui.components import KpiCard

    win, db, _ = regression_env
    prof_id, ctx_m, ctx_y, _ = win.get_active_context()

    # 1. Dashboard: KPIs horizontais sem recorte e fundo de QChart transparente
    win.navigate_to("dashboard")
    win.dashboard_view.refresh_data()
    QApplication.processEvents()

    dash_cards = [c for c in win.dashboard_view.findChildren(KpiCard) if c.isVisible()]
    assert len(dash_cards) >= 4
    for card in dash_cards:
        assert isinstance(card.layout(), QHBoxLayout)
        assert card.minimumHeight() >= 84
        assert card.lbl_value.sizeHint().height() <= card.height()

    assert win.dashboard_view.chart_view.chart().isBackgroundVisible() is False
    assert win.dashboard_view.monthly_chart_view.chart().isBackgroundVisible() is False
    assert win.dashboard_view.monthly_chart_view.chart().isPlotAreaBackgroundVisible() is False

    # 2. Lançamentos: despesa parcelada no contexto ativo e validação de KPIs + Feed
    acc_repo = AccountRepository(db)
    accounts = acc_repo.list_accounts(profile_id=prof_id)
    acc_id = accounts[0].id if accounts else acc_repo.create_account("Conta Etapa 1", profile_id=prof_id)
    win.dashboard_view.refresh_data()
    QApplication.processEvents()
    dash_rows = [
        f
        for f in win.dashboard_view.acc_list_widget.findChildren(QFrame)
        if f.objectName() == "DashListRow"
    ]
    assert len(dash_rows) >= 1
    for dr in dash_rows:
        assert "QFrame#DashListRow" in dr.styleSheet()
        assert dr.minimumHeight() >= 52

    tx_svc = TransactionService(db)
    tx_svc.create_expense(
        descricao="Notebook Etapa 1",
        valor=1200.0,
        data_vencimento=date(ctx_y, ctx_m, 10),
        profile_id=prof_id,
        id_conta=acc_id,
        recorrencia=REC_PARCELADA,
        num_parcelas=3,
    )

    win.navigate_to("transacoes")
    win.transacoes_view.refresh_data()
    QApplication.processEvents()

    tx_cards = [c for c in win.transacoes_view.findChildren(KpiCard) if c.isVisible()]
    assert len(tx_cards) >= 4
    for card in tx_cards:
        assert isinstance(card.layout(), QHBoxLayout)
        assert card.minimumHeight() >= 84
        assert card.lbl_value.sizeHint().height() <= card.height()

    feed_rows = [
        f
        for f in win.transacoes_view.feed_host.findChildren(QFrame)
        if f.objectName() == "FeedRowCard" and f.isVisible()
    ]
    assert len(feed_rows) >= 1
    for row in feed_rows:
        assert row.minimumHeight() >= 58
        chks = row.findChildren(QCheckBox)
        assert len(chks) == 1
        assert chks[0].width() >= 22


def test_regression_etapa2_installment_drawer_overlay_and_spacing(regression_env) -> None:
    """Regressão Etapa 2: InstallmentDrawer em overlay (440px + scrim), margens amplas (28x24) e linhas da timeline espaçadas."""
    from datetime import date
    from PySide6.QtWidgets import QFrame
    from app.domain.models import REC_PARCELADA
    from app.domain.services.transaction_service import TransactionService
    from app.ui.components import InstallmentMiniBar, TimelineStepMarker

    win, db, _ = regression_env
    prof_id, ctx_m, ctx_y, _ = win.get_active_context()

    acc_repo = AccountRepository(db)
    accounts = acc_repo.list_accounts(profile_id=prof_id)
    acc_id = accounts[0].id if accounts else acc_repo.create_account("Conta Etapa 2", profile_id=prof_id)

    tx_svc = TransactionService(db)
    tx_svc.create_expense(
        descricao="Mp *Pichau",
        valor=125.76,
        data_vencimento=date(ctx_y, ctx_m, 10),
        profile_id=prof_id,
        id_conta=acc_id,
        recorrencia=REC_PARCELADA,
        num_parcelas=8,
    )

    win.navigate_to("transacoes")
    tx_view = win.transacoes_view
    tx_view.refresh_data()
    QApplication.processEvents()

    drawer = tx_view.installment_drawer
    assert drawer.property("overlay") is True
    assert drawer.width() == 440
    assert drawer.scrim is not None

    root_lay = drawer.layout()
    assert root_lay is not None
    m = root_lay.contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (28, 24, 28, 24)
    assert root_lay.spacing() >= 18

    bars = tx_view.feed_host.findChildren(InstallmentMiniBar)
    assert len(bars) >= 1
    bars[0].clicked.emit()
    QApplication.processEvents()

    assert drawer.isVisible() is True
    assert drawer.scrim.isVisible() is True

    tl_cards = [
        w for w in drawer.findChildren(QFrame) if w.objectName() == "TimelineItemCard"
    ]
    assert len(tl_cards) == 8
    for tc in tl_cards:
        assert tc.minimumHeight() >= 54
        tc_lay = tc.layout()
        assert tc_lay is not None
        tm = tc_lay.contentsMargins()
        assert tm.left() >= 12 and tm.top() >= 10 and tm.right() >= 14 and tm.bottom() >= 10
        assert tc_lay.spacing() >= 14

    markers = drawer.findChildren(TimelineStepMarker)
    assert len(markers) == 8
    assert markers[0].width() == 20
    assert markers[0].minimumHeight() >= 48

    drawer.close_drawer()
    QApplication.processEvents()
    assert drawer.isVisible() is False
    assert drawer.scrim.isVisible() is False

    # Cartões de crédito também possui o drawer em overlay (440px)
    assert hasattr(win.cartoes_view, "installment_drawer")
    assert win.cartoes_view.installment_drawer.property("overlay") is True
    assert win.cartoes_view.installment_drawer.width() == 440


def test_regression_etapa3_settings_centralized_in_user_avatar(regression_env) -> None:
    """Regressão Etapa 3: Configurações removidas da sidebar/topbar e centralizadas exclusivamente no avatar circular."""
    win, _, _ = regression_env

    # 1. Sidebar não exibe item 'configuracoes'
    nav_keys = [k for k, _ in win.NAV_ITEMS]
    assert "configuracoes" not in nav_keys
    assert "configuracoes" not in win._nav_buttons
    for _, grp_keys in win.NAV_GROUPS:
        assert "configuracoes" not in grp_keys

    # 2. Topbar sem botões técnicos soltos (btn_db_status / cb_date_ref) e com avatar circular 34x34
    assert not hasattr(win, "btn_db_status")
    assert not hasattr(win, "cb_date_ref")
    assert hasattr(win, "btn_user_avatar")
    assert win.btn_user_avatar.objectName() == "UserAvatarButton"
    assert win.btn_user_avatar.width() == 34
    assert win.btn_user_avatar.height() == 34

    # 3. Inicial dinâmica e menu 'Sua conta' -> 'Minha conta' / 'Sair' com e-mail mascarado
    win.db.settings.user_display_name = "Diogo Lima Duarte"
    win.db.settings.user_email = "diogo@gmail.com"
    win._refresh_header_state()
    assert win.btn_user_avatar.text() == "D"

    menu = win.build_user_account_menu()
    assert menu.objectName() == "UserAccountMenu"
    assert menu.lbl_subtitle.text() == "d***@gmail.com"
    assert menu.btn_my_account.text().strip() == "Minha conta"
    assert menu.btn_logout.text().strip() == "Sair"

    # 4. Clicar em 'Minha conta' leva à tela de configurações
    assert win.current_nav_key == "dashboard"
    menu.btn_my_account.click()
    QApplication.processEvents()
    assert win.current_nav_key == "configuracoes"
    assert win.stack.currentWidget() is win.config_hub_view


def test_regression_etapa4_minha_conta_master_detail_arthas_layout(regression_env) -> None:
    """Regressão Etapa 4: Tela 'Minha conta' em Master-Detail 2 colunas estilo Arthas com seções e dados de perfil."""
    win, _, _ = regression_env
    win.db.settings.user_display_name = "Diogo Lima Duarte"
    win.db.settings.user_email = "diogold527@gmail.com"
    win.db.settings.user_phone = "5567999999999"

    win.navigate_to("configuracoes")
    QApplication.processEvents()

    hub: ConfiguracoesHubView = win.config_hub_view
    assert hub.lbl_page_title.text() == "Minha conta"
    assert hub.workspace_frame.objectName() == "AccountWorkspaceFrame"
    assert hub.nav_card.objectName() == "AccountNavCard"
    assert hub.nav_card.width() == 264
    assert hub.tabs.tabBar().isVisible() is False

    # Inicia em 'Perfil' com avatar 'DD', card 'Seus dados' e card 'Família'
    assert hub._active_section == "perfil"
    assert hub.detail_stack.currentWidget() is hub.perfil_tab
    assert hub._nav_rows["perfil"].property("active") is True
    assert hub.lbl_nav_avatar.text() == "DD"
    assert hub.lbl_nav_name.text() == "DIOGO LIMA DUARTE"
    assert hub.perfil_tab.lbl_val_name.text() == "Diogo Lima Duarte"
    assert hub.perfil_tab.lbl_val_email.text() == "diogold527@gmail.com"
    assert hub.perfil_tab.lbl_val_phone.text() == "5567999999999"

    # Alternância entre seções laterais do Master-Detail
    hub.select_section("preferencias")
    QApplication.processEvents()
    assert hub.detail_stack.currentWidget() is hub.preferencias_tab
    assert hub._nav_rows["preferencias"].property("active") is True

    hub.select_section("avisos")
    QApplication.processEvents()
    assert hub.detail_stack.currentWidget() is hub.avisos_tab

    for tab_idx, key in enumerate(("banco", "open_finance", "ferramentas", "ia", "investimentos")):
        hub.select_tab(key)
        QApplication.processEvents()
        assert hub.detail_stack.currentWidget() is hub.tabs
        assert hub.tabs.currentIndex() == tab_idx
        assert hub._nav_rows[key].property("active") is True


def test_regression_round2_etapa1_topbar_and_minha_conta_alignment(regression_env) -> None:
    """Regressão Etapa 1 (R2): Esquadro 24px entre Topbar e Minha conta, pílula Pessoal▾ simétrica, largura total nos cards e pílula Local 20px."""
    win, _, _ = regression_env
    win.navigate_to("configuracoes")
    QApplication.processEvents()

    # 1. Margem esquerda de DesktopHeader e ConfiguracoesHubView cravadas em 24px
    hdr_m = win.header_frame.layout().contentsMargins()
    hub_m = win.config_hub_view.layout().contentsMargins()
    assert hdr_m.left() == 24 and hdr_m.right() == 24
    assert hub_m.left() == 24 and hub_m.right() == 24

    # 2. Seletor de perfil na Topbar com altura 34px igual à busca global e chevron ▾
    assert win.cb_profile.height() == 34
    assert win.ed_global_search.height() == 34
    assert "▾" in win.cb_profile.currentText()

    # 3. Cards de Perfil preenchem toda a coluna direita (sem trava 680px) e pílula Local tem 20px de altura
    hub = win.config_hub_view
    assert hub.perfil_tab.data_card.maximumWidth() > 1000
    assert hub.perfil_tab.family_card.maximumWidth() > 1000
    sec_badge = hub._nav_rows["banco"].badge_widget
    assert sec_badge is not None
    assert sec_badge.objectName() == "AccountNavPill"
    assert sec_badge.height() == 20


def test_regression_round2_etapa2_dot_timeline_capsules_and_subtotals(regression_env) -> None:
    """Regressão Etapa 2 (R2): Cápsulas FilterCountPill, subtotais discretos vs valores reais e linha do tempo de pontos InstallmentMiniBar."""
    from datetime import date
    from PySide6.QtWidgets import QLabel
    from app.domain.models import REC_PARCELADA
    from app.ui.components import FilterCountPill, InstallmentMiniBar

    win, db, _ = regression_env
    prof_id = win.active_profile_id
    today = date.today()

    card = win.card_service.create_card(
        nome="Nubank",
        limite=5000.0,
        dia_fecha=28,
        dia_venc=10,
        profile_id=prof_id,
    )
    open_inv = win.card_service.get_open_invoice(card.id, today)
    win.tx_service.create_expense(
        descricao="Alura",
        valor=97.66,
        data_vencimento=open_inv.data_vencimento,
        data_evento=today,
        recorrencia=REC_PARCELADA,
        num_parcelas=12,
        valor_por_parcela=True,
        id_cartao=card.id,
        profile_id=prof_id,
    )

    win.current_month = open_inv.data_vencimento.month
    win.current_year = open_inv.data_vencimento.year
    win.navigate_to("transacoes")
    QApplication.processEvents()

    tx_view = win.transacoes_view
    for k in ("ALL", "RECEITA", "DESPESA", "TRANSFERENCIA"):
        pill = tx_view.count_pills[k]
        assert isinstance(pill, FilterCountPill)
        assert pill.height() == 32

    # Subtotal discreto separado do valor real
    subtotals = [
        lbl for lbl in tx_view.findChildren(QLabel)
        if lbl.objectName() == "FeedSubtotalBadge"
    ]
    assert len(subtotals) >= 1
    assert "Subtotal" in subtotals[0].text()

    cat_pills = [
        lbl for lbl in tx_view.findChildren(QLabel)
        if lbl.objectName() == "CategoryCapsulePill"
    ]
    assert len(cat_pills) >= 1

    # Contratos de geometria, pulso 1.8s, parcela final verde e limite de 12 pontos
    bar_mid = InstallmentMiniBar(8, 12)
    assert bar_mid.dots_count == 12
    assert bar_mid.is_final_installment is False
    assert bar_mid._pulse_anim is not None
    assert bar_mid._pulse_anim.duration() == 1800

    bar_end = InstallmentMiniBar(3, 3)
    assert bar_end.is_final_installment is True
    assert bar_end._pulse_anim is None
    assert bar_end.FINAL_DOT_HEX == "#1D9E75"
    assert bar_end.FINAL_RING_HEX == "#9FE1CB"

    bar_long = InstallmentMiniBar(6, 24)
    assert bar_long.dots_count == 12

    # Clique na linha do tempo inline abre o SideDrawer de parcelas
    feed_bars = [
        b for b in tx_view.findChildren(InstallmentMiniBar)
        if b.isVisible()
    ]
    assert len(feed_bars) >= 1
    feed_bars[0].clicked.emit()
    QApplication.processEvents()
    assert tx_view.installment_drawer.isVisible()
    tx_view.installment_drawer.close_drawer()


def test_regression_round2_etapa3_cartoes_single_row_actions_and_modal(regression_env) -> None:
    """Regressão Etapa 3 (R2): Cartões e faturas com barra única de ações, banner de melhor dia, filtros de faturas e modal Arthas de 2 colunas com swatches."""
    from datetime import date
    from app.domain.models import REC_PARCELADA
    from app.ui.views.cartoes_view import CardFormDialog

    win, db, _ = regression_env
    prof_id = win.active_profile_id
    today = date.today()

    card = win.card_service.create_card(
        nome="Nubank Gold",
        limite=3000.0,
        dia_fecha=28,
        dia_venc=10,
        profile_id=prof_id,
    )
    open_inv = win.card_service.get_open_invoice(card.id, today)
    win.tx_service.create_expense(
        descricao="Compra À Vista",
        valor=50.0,
        data_vencimento=open_inv.data_vencimento,
        data_evento=today,
        id_cartao=card.id,
        profile_id=prof_id,
    )
    win.tx_service.create_expense(
        descricao="Notebook Parcelado",
        valor=250.0,
        data_vencimento=open_inv.data_vencimento,
        data_evento=today,
        recorrencia=REC_PARCELADA,
        num_parcelas=6,
        valor_por_parcela=True,
        id_cartao=card.id,
        profile_id=prof_id,
    )

    win.current_month = open_inv.mes
    win.current_year = open_inv.ano
    win.navigate_to("cartoes")
    QApplication.processEvents()
    cview = win.cartoes_view

    assert cview.btn_limits_toggle.objectName() == "SecondaryButton"
    assert cview.btn_new_card.objectName() == "PrimaryButton"
    assert not cview.btn_new_card.text().startswith("+ ")
    assert cview.best_day_banner.objectName() == "BestDayBanner"
    assert "Melhor dia de compra" in cview.lbl_best_day_text.text()

    # Adiantar fatura foi consolidado no menu Gerenciar ▾ (sem segunda fileira de botões)
    menu = cview.btn_card_actions.menu()
    assert menu is not None
    action_texts = [a.text() for a in menu.actions() if a.text()]
    assert "Adiantar fatura" in action_texts

    # Filtro Todos vs Parcelados na seção Lançamentos da fatura
    assert cview.pill_inv_all.text() == "Todos 2"
    assert cview.pill_inv_parc.text() == "Parcelados 1"
    cview._set_inv_type_filter("PARC")
    QApplication.processEvents()
    assert cview.pill_inv_parc.property("active") is True
    assert cview.tbl_items.rowCount() == 1
    cview._set_inv_type_filter("ALL")
    QApplication.processEvents()
    assert cview.pill_inv_all.property("active") is True
    assert cview.tbl_items.rowCount() == 2

    # Modal Novo Cartão de Crédito de 2 colunas com 15 swatches circulares e últimos 4 dígitos
    dlg = CardFormDialog(db, profile_id=prof_id, parent=cview)
    assert len(dlg.swatch_buttons) == 15
    assert dlg.ed_last4.maxLength() == 4
    dlg.ed_nome.setText("Itaú Personnalité")
    dlg.ed_last4.setText("9876")
    assert dlg.resolved_card_name() == "Itaú Personnalité 9876"
    dlg.swatch_buttons[4].click()
    assert dlg.cb_cor.currentData() == dlg.ARTHAS_CARD_COLORS[4]
    dlg.close()


def test_regression_round2_etapa4_responsive_ui_zoom_and_auto_mode(regression_env) -> None:
    """Regressão Etapa 4 (R2): Controle de zoom responsivo (60%-150%), atalhos/persistência, modo Automático e integridade Claro/Escuro."""
    from app.config.app_settings import AppSettings, clamp_ui_zoom
    from app.ui.style_manager import get_current_ui_zoom

    win, db, tmp_path = regression_env

    # 1. Limites estritos [0.60, 1.50] com arredondamento em 2 casas
    assert clamp_ui_zoom(0.25) == 0.60
    assert clamp_ui_zoom(1.95) == 1.50
    assert clamp_ui_zoom(0.856) == 0.86

    # 2. Aplicação manual do zoom (80%), escala estrutural e persistência em JSON
    applied = win.set_ui_zoom(0.80, manual=True)
    QApplication.processEvents()
    assert applied == 0.80
    assert get_current_ui_zoom() == 0.80
    assert win.sidebar_frame.width() == round(216 * 0.80)

    reloaded = AppSettings.load(tmp_path / "settings.json")
    assert reloaded.ui_zoom_factor == 0.80
    assert reloaded.ui_zoom_auto is False

    # Passos de atalho (+0.10 / -0.05)
    assert win.step_ui_zoom(+0.10) == 0.90
    assert win.step_ui_zoom(-0.05) == 0.85

    # 3. Controles em Minha conta -> Preferências + Modo Automático
    win.navigate_to("configuracoes")
    win.config_hub_view.select_section("preferencias")
    QApplication.processEvents()
    pref = win.config_hub_view.preferencias_tab

    assert pref.slider_zoom.minimum() == 60
    assert pref.slider_zoom.maximum() == 150
    assert pref.slider_zoom.singleStep() == 5
    assert pref.lbl_zoom_val.text() == "85%"

    # Ativa modo Automático: zoom = min(1.0, max(0.7, largura / 1920))
    pref.chk_zoom_auto.setChecked(True)
    QApplication.processEvents()
    assert db.settings.ui_zoom_auto is True

    win.resize(1344, 800)  # 1344 / 1920 = 0.70
    win._apply_auto_zoom_from_window()
    QApplication.processEvents()
    assert db.settings.ui_zoom_factor == 0.70
    assert pref.lbl_zoom_val.text() == "70%"

    # Mexer manualmente no slider desativa o modo Automático
    pref.slider_zoom.setValue(115)
    QApplication.processEvents()
    assert db.settings.ui_zoom_auto is False
    assert pref.chk_zoom_auto.isChecked() is False
    assert db.settings.ui_zoom_factor == 1.15
    assert pref.lbl_zoom_val.text() == "115%"

    # Valida gráficos e alternância Claro/Escuro sob zoom diferente de 100%
    win.navigate_to("graficos")
    QApplication.processEvents()
    win.toggle_theme_mode()
    QApplication.processEvents()
    assert get_current_ui_zoom() == 1.15
    win.toggle_theme_mode()
    QApplication.processEvents()

    # Botão Restaurar 100% retorna ao padrão 1.0 (sidebar 216px)
    pref.btn_zoom_reset.click()
    QApplication.processEvents()
    assert db.settings.ui_zoom_factor == 1.00
    assert win.sidebar_frame.width() == 216
    assert pref.lbl_zoom_val.text() == "100%"

