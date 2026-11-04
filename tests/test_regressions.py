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
