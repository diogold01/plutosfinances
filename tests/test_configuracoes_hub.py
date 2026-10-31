"""Testes automatizados do Hub de Configurações e integração de UI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.config import gemini_key_store as key_store
from app.database.backup_service import BackupSchedulerService
from app.ui.main_window import MainWindow
from app.ui.views.configuracoes_hub_view import ConfiguracoesHubView
from tests.test_etapa4_transactions_and_cards import _make_env


def test_configuracoes_hub_navigation_and_tabs(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    bkp = BackupSchedulerService(connection_manager=conn, settings=conn.settings)
    try:
        win = MainWindow(conn, bkp)

        # 1. Navega para Configurações
        win.navigate_to("configuracoes")
        assert win.current_nav_key == "configuracoes"
        assert isinstance(win.stack.currentWidget(), ConfiguracoesHubView)
        hub = win.config_hub_view

        # 2. Testa troca de abas internas
        assert hub.tabs.count() == 3
        hub.select_tab("ferramentas")
        assert hub.tabs.currentIndex() == 1

        hub.select_tab("ia")
        assert hub.tabs.currentIndex() == 2

        hub.select_tab("banco")
        assert hub.tabs.currentIndex() == 0

        # 3. Testa compatibilidade legada: navigate_to("ferramentas") redireciona para a sub-aba
        win.navigate_to("ferramentas")
        assert win.current_nav_key == "configuracoes"
        assert hub.tabs.currentIndex() == 1

        # 4. Testa aba de IA
        ia_tab = hub.ia_tab
        ia_tab.ed_key.setText("AIzaSyTeste123456789")
        ia_tab.save()
        key, source = key_store.resolve_gemini_key(conn.settings.user_data_dir)
        assert key == "AIzaSyTeste123456789"
        assert source == key_store.SOURCE_FILE

        # Limpeza com simulação de confirmação
        monkeypatch.setattr(
            "app.ui.views.configuracoes_hub_view.QMessageBox.question",
            lambda *a, **kw: ia_tab.btn_clear.parent().findChild(object) or 16384,  # StandardButton.Yes
        )
        key_store.clear_gemini_key(conn.settings.user_data_dir)
        ia_tab.refresh_data()
        assert key_store.resolve_gemini_key(conn.settings.user_data_dir)[0] == ""

        win.close()
    finally:
        conn.close()
