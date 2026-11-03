"""Hub unificado de Configurações: Banco/Backup/Perfis, Open Finance (Pluggy), Ferramentas e IA (BYOK)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import gemini_key_store as key_store
from app.config.theme_palette import ThemePalette
from app.database.connection_manager import ConnectionManager
from app.database.repositories.profile_repository import ProfileRepository
from app.domain.services.ai_service import AIService
from app.services.pluggy_client import PluggyClient, PluggyConfigManager
from app.ui.ai_worker import AITestWorker
from app.ui.components import Badge
from app.ui.icons import get_line_icon
from app.ui.views.configuracoes_view import ConfiguracoesView
from app.ui.views.ferramentas_view import FerramentasView
from app.ui.views.open_finance_dialog import OpenFinanceSyncDialog

GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.8-flash"]
TAB_KEYS = ("banco", "open_finance", "ferramentas", "ia", "investimentos")


class AIConfigTab(QWidget):
    """Aba de Inteligência Artificial: chave BYOK, modelo e teste de conexão."""

    def __init__(self, db: ConnectionManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self._worker: Optional[AITestWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 12, 0, 0)
        card = QFrame()
        card.setObjectName("CardSurface")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        lbl_t = QLabel("Lançamento Rápido por IA (Google Gemini)")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Use a sua própria chave do Google AI Studio (BYOK). "
            "Ela fica somente neste computador, em dados_usuario/gemini_key.local."
        )
        lbl_s.setObjectName("MutedText")
        lbl_s.setWordWrap(True)
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_s)

        lbl_where = QLabel(
            "Como usar: clique no ícone do Gemini (✦) no topo, ao lado do botão \"Novo\". "
            "Atalho opcional: Ctrl+K."
        )
        lbl_where.setObjectName("MutedText")
        lbl_where.setWordWrap(True)
        lay.addWidget(lbl_where)

        self.lbl_source = QLabel()
        self.lbl_source.setObjectName("MutedText")
        lay.addWidget(self.lbl_source)

        key_row = QHBoxLayout()
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_key.setPlaceholderText("Cole aqui a sua API Key (AIza...)")
        self.btn_show = QPushButton("Mostrar")
        self.btn_show.setObjectName("SecondaryButton")
        self.btn_show.setCheckable(True)
        self.btn_show.toggled.connect(self._toggle_visibility)
        key_row.addWidget(self.ed_key, stretch=1)
        key_row.addWidget(self.btn_show)
        lay.addLayout(key_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Modelo:"))
        self.cb_model = QComboBox()
        self.cb_model.setEditable(True)
        self.cb_model.addItems(GEMINI_MODELS)
        model_row.addWidget(self.cb_model, stretch=1)
        lay.addLayout(model_row)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("Salvar")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self.save)
        self.btn_test = QPushButton("Testar conexão")
        self.btn_test.setObjectName("SecondaryButton")
        self.btn_test.clicked.connect(self.test_connection)
        self.btn_clear = QPushButton("Remover chave")
        self.btn_clear.setObjectName("SecondaryButton")
        self.btn_clear.clicked.connect(self.clear)
        for b in (self.btn_save, self.btn_test, self.btn_clear):
            btn_row.addWidget(b)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        root.addWidget(card)
        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------ #
    def _toggle_visibility(self, shown: bool) -> None:
        self.ed_key.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        self.btn_show.setText("Ocultar" if shown else "Mostrar")

    def refresh_data(self) -> None:
        settings = self.db.settings
        key, source = key_store.resolve_gemini_key(settings.user_data_dir)
        texts = {
            key_store.SOURCE_ENV: f"Chave ativa via variável de ambiente ({key_store.mask_key(key)}).",
            key_store.SOURCE_FILE: f"Chave ativa via arquivo local ({key_store.mask_key(key)}).",
            key_store.SOURCE_NONE: "Nenhuma chave configurada.",
        }
        self.lbl_source.setText(texts[source])
        self.ed_key.clear()
        self.ed_key.setEnabled(source != key_store.SOURCE_ENV)
        self.cb_model.setCurrentText(settings.gemini_model)

    def _effective_key(self) -> str:
        typed = self.ed_key.text().strip()
        if typed:
            return typed
        return key_store.resolve_gemini_key(self.db.settings.user_data_dir)[0]

    def save(self) -> None:
        settings = self.db.settings
        typed = self.ed_key.text().strip()
        if typed:
            key_store.save_gemini_key(settings.user_data_dir, typed)
        settings.gemini_model = self.cb_model.currentText().strip() or GEMINI_MODELS[0]
        settings.save()
        self.refresh_data()
        self._set_status("Configuração salva.", ok=True)

    def clear(self) -> None:
        if QMessageBox.question(self, "Remover chave", "Remover a chave de API salva?") != (
            QMessageBox.StandardButton.Yes
        ):
            return
        key_store.clear_gemini_key(self.db.settings.user_data_dir)
        self.refresh_data()
        self._set_status("Chave removida.", ok=True)

    def test_connection(self) -> None:
        key = self._effective_key()
        if not key:
            self._set_status("Informe uma chave antes de testar.", ok=False)
            return
        service = AIService(key, model=self.cb_model.currentText().strip())
        self.btn_test.setEnabled(False)
        self._set_status("Testando conexão...", ok=None)
        self._worker = AITestWorker(service, self)
        self._worker.succeeded.connect(lambda _r: self._on_test_done("Conexão OK.", True))
        self._worker.failed.connect(lambda msg: self._on_test_done(msg, False))
        self._worker.start()

    def _on_test_done(self, msg: str, ok: bool) -> None:
        self.btn_test.setEnabled(True)
        self._set_status(msg, ok=ok)

    def _set_status(self, msg: str, ok: Optional[bool]) -> None:
        color = {True: "#2E7D32", False: "#C62828", None: ""}[ok]
        self.lbl_status.setStyleSheet(f"color: {color};" if color else "")
        self.lbl_status.setText(msg)


class OpenFinanceConfigTab(QWidget):
    """Aba dedicada de Open Finance (Pluggy - BYOK): credenciais, conexões e sincronização."""

    def __init__(
        self,
        db: ConnectionManager,
        on_environment_changed: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.on_environment_changed = on_environment_changed or (lambda: None)
        self.profile_repo = ProfileRepository(db)
        self.pluggy_config_mgr = PluggyConfigManager(self.db.settings.user_data_dir)
        self.pluggy_client = PluggyClient()
        self._pluggy_items = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_title = QLabel("Open Finance (Pluggy)")
        lbl_title.setObjectName("SectionTitle")
        lbl_sub = QLabel(
            "Conexão bancária direta e segura via Pluggy (Bring Your Own Key) — 100% Local-First"
        )
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        root.addLayout(title_box)

        f_bold = QFont()
        f_bold.setBold(True)
        f_bold.setPointSize(11)

        pluggy_card = QFrame()
        pluggy_card.setObjectName("CardSurface")
        pluggy_lay = QVBoxLayout(pluggy_card)
        pluggy_lay.setContentsMargins(20, 18, 20, 18)
        pluggy_lay.setSpacing(12)

        pluggy_head = QHBoxLayout()
        pluggy_t_col = QVBoxLayout()
        pluggy_t_col.setSpacing(2)
        lbl_pluggy_title = QLabel("Credenciais da API Pluggy")
        lbl_pluggy_title.setFont(f_bold)
        lbl_pluggy_sub = QLabel(
            "Suas credenciais são salvas exclusivamente neste computador (dados_usuario/pluggy_config.local)"
        )
        lbl_pluggy_sub.setObjectName("MutedText")
        pluggy_t_col.addWidget(lbl_pluggy_title)
        pluggy_t_col.addWidget(lbl_pluggy_sub)
        pluggy_head.addLayout(pluggy_t_col)
        pluggy_head.addStretch()

        self.lbl_pluggy_status_badge = Badge("Não configurado", variant="neutral")
        pluggy_head.addWidget(self.lbl_pluggy_status_badge)
        pluggy_lay.addLayout(pluggy_head)

        cred_form = QHBoxLayout()
        cred_form.setSpacing(12)

        col_cid = QVBoxLayout()
        col_cid.setSpacing(4)
        lbl_cid = QLabel("Client ID:")
        lbl_cid.setFont(f_bold)
        self.txt_pluggy_client_id = QLineEdit()
        self.txt_pluggy_client_id.setMinimumHeight(34)
        self.txt_pluggy_client_id.setPlaceholderText("Cole seu Client ID da Pluggy aqui...")
        col_cid.addWidget(lbl_cid)
        col_cid.addWidget(self.txt_pluggy_client_id)
        cred_form.addLayout(col_cid, stretch=1)

        col_sec = QVBoxLayout()
        col_sec.setSpacing(4)
        lbl_sec = QLabel("Client Secret:")
        lbl_sec.setFont(f_bold)
        sec_input_box = QHBoxLayout()
        sec_input_box.setSpacing(6)
        self.txt_pluggy_client_secret = QLineEdit()
        self.txt_pluggy_client_secret.setMinimumHeight(34)
        self.txt_pluggy_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pluggy_client_secret.setPlaceholderText("Cole seu Client Secret da Pluggy aqui...")
        self.btn_toggle_pluggy_secret = QPushButton()
        self.btn_toggle_pluggy_secret.setObjectName("SecondaryButton")
        self.btn_toggle_pluggy_secret.setIcon(get_line_icon("eye", size=14))
        self.btn_toggle_pluggy_secret.setToolTip("Mostrar / Ocultar Secret")
        self.btn_toggle_pluggy_secret.clicked.connect(self._toggle_pluggy_secret_visibility)
        sec_input_box.addWidget(self.txt_pluggy_client_secret)
        sec_input_box.addWidget(self.btn_toggle_pluggy_secret)
        col_sec.addWidget(lbl_sec)
        col_sec.addLayout(sec_input_box)
        cred_form.addLayout(col_sec, stretch=1)

        pluggy_lay.addLayout(cred_form)

        pluggy_actions = QHBoxLayout()
        pluggy_actions.setSpacing(8)

        self.btn_test_pluggy = QPushButton("Testar Conexão")
        self.btn_test_pluggy.setObjectName("SecondaryButton")
        self.btn_test_pluggy.setIcon(get_line_icon("refresh_cw", size=14))
        self.btn_test_pluggy.clicked.connect(self._on_test_pluggy_connection)

        self.btn_save_pluggy = QPushButton("Salvar Credenciais")
        self.btn_save_pluggy.setObjectName("PrimaryButton")
        self.btn_save_pluggy.setIcon(get_line_icon("check", size=14, color="#FFFFFF"))
        self.btn_save_pluggy.clicked.connect(self._on_save_pluggy_credentials)

        pluggy_actions.addWidget(self.btn_test_pluggy)
        pluggy_actions.addWidget(self.btn_save_pluggy)
        pluggy_actions.addStretch()

        self.lbl_pluggy_feedback = QLabel()
        self.lbl_pluggy_feedback.setObjectName("MutedText")
        pluggy_actions.addWidget(self.lbl_pluggy_feedback)

        pluggy_lay.addLayout(pluggy_actions)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        pluggy_lay.addWidget(sep)

        items_head = QHBoxLayout()
        items_t_col = QVBoxLayout()
        items_t_col.setSpacing(2)
        lbl_items_title = QLabel("Instituições Bancárias Conectadas")
        lbl_items_title.setFont(f_bold)
        lbl_items_sub = QLabel(
            "Bancos autorizados via Open Finance para sincronização de extratos e investimentos"
        )
        lbl_items_sub.setObjectName("MutedText")
        lbl_items_sub.setWordWrap(True)
        items_t_col.addWidget(lbl_items_title)
        items_t_col.addWidget(lbl_items_sub)
        items_head.addLayout(items_t_col, stretch=1)

        # Linha principal: ações de conexão (destaque)
        items_btns = QHBoxLayout()
        items_btns.setSpacing(8)

        self.btn_add_item_by_id = QPushButton("Adicionar por ID")
        self.btn_add_item_by_id.setObjectName("SecondaryButton")
        self.btn_add_item_by_id.setIcon(get_line_icon("plus", size=14))
        self.btn_add_item_by_id.clicked.connect(self._on_add_item_by_id)

        self.btn_connect_bank = QPushButton("Conectar Novo Banco")
        self.btn_connect_bank.setObjectName("PrimaryButton")
        self.btn_connect_bank.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        self.btn_connect_bank.clicked.connect(self._on_connect_new_bank)

        # Linha de gestão: sincronização e remoção
        self.btn_sync_items_list = QPushButton("Atualizar Conexões")
        self.btn_sync_items_list.setObjectName("SecondaryButton")
        self.btn_sync_items_list.setIcon(get_line_icon("refresh_cw", size=14))
        self.btn_sync_items_list.clicked.connect(self._on_refresh_connected_items)

        self.btn_sync_open_finance_data = QPushButton("Sincronizar Lançamentos")
        self.btn_sync_open_finance_data.setObjectName("SecondaryButton")
        self.btn_sync_open_finance_data.setIcon(get_line_icon("download", size=14))
        self.btn_sync_open_finance_data.clicked.connect(self._on_open_sync_dialog)

        self.btn_delete_item = QPushButton("Remover Selecionado")
        self.btn_delete_item.setObjectName("SecondaryButton")
        self.btn_delete_item.setIcon(get_line_icon("trash", size=14))
        self.btn_delete_item.clicked.connect(self._on_delete_selected_item)

        for btn in (
            self.btn_add_item_by_id,
            self.btn_connect_bank,
            self.btn_sync_items_list,
            self.btn_sync_open_finance_data,
            self.btn_delete_item,
            self.btn_test_pluggy,
            self.btn_save_pluggy,
        ):
            btn.setMinimumHeight(34)

        items_btns.addStretch()
        items_btns.addWidget(self.btn_add_item_by_id)
        items_btns.addWidget(self.btn_connect_bank)
        items_head.addLayout(items_btns)
        pluggy_lay.addLayout(items_head)

        manage_btns = QHBoxLayout()
        manage_btns.setSpacing(8)
        manage_btns.addWidget(self.btn_sync_items_list)
        manage_btns.addWidget(self.btn_sync_open_finance_data)
        manage_btns.addWidget(self.btn_delete_item)
        manage_btns.addStretch()
        pluggy_lay.addLayout(manage_btns)

        self.table_pluggy_items = QTableWidget(0, 4)
        self.table_pluggy_items.setHorizontalHeaderLabels(
            ["Instituição Financeira", "Status", "Última Sincronização", "ID Conexão"]
        )
        self.table_pluggy_items.setShowGrid(False)
        self.table_pluggy_items.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_pluggy_items.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.table_pluggy_items.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table_pluggy_items.verticalHeader().setVisible(False)
        self.table_pluggy_items.verticalHeader().setDefaultSectionSize(36)
        self.table_pluggy_items.setMinimumHeight(180)
        pih = self.table_pluggy_items.horizontalHeader()
        pih.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        pih.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        pih.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        pih.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        pluggy_lay.addWidget(self.table_pluggy_items)

        root.addWidget(pluggy_card)
        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def refresh_data(self) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        pluggy_cfg = self.pluggy_config_mgr.load_config()
        if not self.txt_pluggy_client_id.text() and pluggy_cfg.client_id:
            self.txt_pluggy_client_id.setText(pluggy_cfg.client_id)
        if not self.txt_pluggy_client_secret.text() and pluggy_cfg.client_secret:
            self.txt_pluggy_client_secret.setText(pluggy_cfg.client_secret)

        if pluggy_cfg.client_id and pluggy_cfg.client_secret:
            total_items = len(pluggy_cfg.items)
            self.lbl_pluggy_status_badge.setText(
                f"{total_items} banco(s) conectado(s)" if total_items > 0 else "Configurado"
            )
            self.lbl_pluggy_status_badge.setProperty("variant", "success")
        else:
            self.lbl_pluggy_status_badge.setText("Não configurado")
            self.lbl_pluggy_status_badge.setProperty("variant", "neutral")
        self.lbl_pluggy_status_badge.style().unpolish(self.lbl_pluggy_status_badge)
        self.lbl_pluggy_status_badge.style().polish(self.lbl_pluggy_status_badge)

        self._pluggy_items = pluggy_cfg.items
        self.table_pluggy_items.setRowCount(len(self._pluggy_items))
        for idx, item in enumerate(self._pluggy_items):
            it_name = QTableWidgetItem(item.connector_name or "Banco Conectado")
            f_name = it_name.font()
            f_name.setBold(True)
            it_name.setFont(f_name)
            it_name.setData(Qt.ItemDataRole.UserRole, item.item_id)
            self.table_pluggy_items.setItem(idx, 0, it_name)

            is_ok = item.status == "UPDATED" and item.execution_status == "SUCCESS"
            badge = Badge(
                "Sincronizado" if is_ok else item.status,
                variant="success" if is_ok else "warning",
            )
            c_w = QWidget()
            c_lay = QHBoxLayout(c_w)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.addWidget(badge)
            self.table_pluggy_items.setCellWidget(idx, 1, c_w)

            it_date = QTableWidgetItem(
                item.last_updated_at[:10] if item.last_updated_at else "Pendente"
            )
            it_date.setForeground(QColor(pal.text_secondary))
            self.table_pluggy_items.setItem(idx, 2, it_date)

            it_id = QTableWidgetItem(item.item_id[:8] + "...")
            it_id.setForeground(QColor(pal.text_secondary))
            self.table_pluggy_items.setItem(idx, 3, it_id)

    def _toggle_pluggy_secret_visibility(self) -> None:
        if self.txt_pluggy_client_secret.echoMode() == QLineEdit.EchoMode.Password:
            self.txt_pluggy_client_secret.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_pluggy_secret.setIcon(get_line_icon("eye_off", size=14))
        else:
            self.txt_pluggy_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_pluggy_secret.setIcon(get_line_icon("eye", size=14))

    def _on_save_pluggy_credentials(self) -> None:
        cid = self.txt_pluggy_client_id.text().strip()
        sec = self.txt_pluggy_client_secret.text().strip()

        cfg = self.pluggy_config_mgr.load_config()
        cfg.client_id = cid
        cfg.client_secret = sec
        self.pluggy_config_mgr.save_config(cfg)

        self.lbl_pluggy_feedback.setText(
            "<span style='color: #1F9D6A;'>✓ Credenciais salvas com segurança localmente!</span>"
        )
        self.refresh_data()

    def _on_test_pluggy_connection(self) -> None:
        cid = self.txt_pluggy_client_id.text().strip()
        sec = self.txt_pluggy_client_secret.text().strip()

        if not cid or not sec:
            QMessageBox.warning(
                self,
                "Campos Obrigatórios",
                "Informe tanto o Client ID quanto o Client Secret para testar a conexão.",
            )
            return

        self.btn_test_pluggy.setEnabled(False)
        self.lbl_pluggy_feedback.setText("<i>Testando autenticação na Pluggy...</i>")
        self.repaint()

        try:
            ok, msg = self.pluggy_client.test_connection(cid, sec)
            if ok:
                self.lbl_pluggy_feedback.setText(
                    "<span style='color: #1F9D6A;'>✓ Conexão bem-sucedida com a Pluggy!</span>"
                )
                QMessageBox.information(
                    self,
                    "Conexão Estabelecida",
                    "Autenticação com a API da Pluggy realizada com sucesso!\n"
                    "Suas credenciais são válidas.",
                )
            else:
                self.lbl_pluggy_feedback.setText(
                    f"<span style='color: #E05252;'>✗ Falha: {msg}</span>"
                )
                QMessageBox.critical(
                    self,
                    "Falha na Conexão",
                    f"Não foi possível autenticar na Pluggy:\n\n{msg}",
                )
        finally:
            self.btn_test_pluggy.setEnabled(True)

    def _on_connect_new_bank(self) -> None:
        cid = self.txt_pluggy_client_id.text().strip()
        sec = self.txt_pluggy_client_secret.text().strip()

        if not cid or not sec:
            QMessageBox.warning(
                self,
                "Configuração Necessária",
                "Você precisa preencher e salvar seu Client ID e Client Secret antes de conectar um banco.",
            )
            return

        self.btn_connect_bank.setEnabled(False)
        try:
            self.pluggy_client.client_id = cid
            self.pluggy_client.client_secret = sec
            self.pluggy_client.authenticate()

            html_path = self.pluggy_client.generate_connect_html(
                self.db.settings.user_data_dir
            )
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(html_path)))

            QMessageBox.information(
                self,
                "Conectar Instituição Bancária",
                "O assistente oficial do Pluggy Connect foi aberto no seu navegador.\n\n"
                "1. Escolha o seu banco e conclua a autorização.\n"
                "2. Ao finalizar com sucesso, o ID da conexão será exibido na tela com um botão para copiar.\n"
                "3. Retorne aqui e clique no botão '+ Adicionar por ID' para confirmar!",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erro ao Iniciar Conexão",
                f"Não foi possível abrir o assistente de conexão:\n\n{exc}",
            )
        finally:
            self.btn_connect_bank.setEnabled(True)

    def _on_add_item_by_id(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Adicionar Conexão por ID",
            "Informe o UUID do Item (obtido na conexão ou no menu Monitorar/Dados do Dashboard):",
        )
        if not ok or not text or not text.strip():
            return

        item_id = text.strip()
        cid = self.txt_pluggy_client_id.text().strip()
        sec = self.txt_pluggy_client_secret.text().strip()
        if not cid or not sec:
            QMessageBox.warning(
                self, "Aviso", "Configure e salve o Client ID e Client Secret primeiro."
            )
            return

        try:
            self.pluggy_client.client_id = cid
            self.pluggy_client.client_secret = sec
            self.pluggy_client.authenticate()
            item = self.pluggy_client.fetch_item(item_id)
            cfg = self.pluggy_config_mgr.load_config()
            cfg.upsert_item(item)
            self.pluggy_config_mgr.save_config(cfg)
            self.refresh_data()
            QMessageBox.information(
                self,
                "Conexão Registrada",
                f"Instituição '{item.connector_name}' (Status: {item.status}) registrada com sucesso!",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erro ao Localizar Conexão",
                f"Não foi possível localizar o item com ID '{item_id}' na Pluggy:\n\n{exc}",
            )

    def _on_refresh_connected_items(self) -> None:
        cid = self.txt_pluggy_client_id.text().strip()
        sec = self.txt_pluggy_client_secret.text().strip()

        if not cid or not sec:
            return

        self.btn_sync_items_list.setEnabled(False)
        try:
            self.pluggy_client.client_id = cid
            self.pluggy_client.client_secret = sec
            self.pluggy_client.authenticate()

            cfg = self.pluggy_config_mgr.load_config()
            items = self.pluggy_client.fetch_items(local_items=cfg.items)
            cfg.items = items
            self.pluggy_config_mgr.save_config(cfg)

            self.refresh_data()
            QMessageBox.information(
                self,
                "Conexões Atualizadas",
                f"Sincronização concluída!\n\nTotal de bancos conectados: {len(items)}",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erro ao Atualizar Conexões",
                f"Falha ao consultar instituições na Pluggy:\n\n{exc}",
            )
        finally:
            self.btn_sync_items_list.setEnabled(True)

    def _on_delete_selected_item(self) -> None:
        row = self.table_pluggy_items.currentRow()
        if row < 0 or row >= len(getattr(self, "_pluggy_items", [])):
            QMessageBox.information(
                self,
                "Selecione uma Instituição",
                "Selecione uma instituição na tabela para remover.",
            )
            return

        item = self._pluggy_items[row]
        ans = QMessageBox.question(
            self,
            "Revogar Conexão Bancária",
            f"Deseja realmente desconectar e revogar o acesso de '{item.connector_name}'?\n\n"
            "Isso revogará o consentimento Open Finance na Pluggy.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return

        try:
            self.pluggy_client.delete_item(item.item_id)
            cfg = self.pluggy_config_mgr.load_config()
            cfg.remove_item(item.item_id)
            self.pluggy_config_mgr.save_config(cfg)
            self.refresh_data()
            QMessageBox.information(
                self,
                "Conexão Removida",
                f"O banco '{item.connector_name}' foi desconectado com sucesso.",
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Erro ao Desconectar",
                f"Não foi possível remover a instituição da Pluggy:\n\n{exc}",
            )

    def _on_open_sync_dialog(self) -> None:
        active_profile = self.profile_repo.get_active_profile()
        prof_id = active_profile.id if active_profile else "1"
        dlg = OpenFinanceSyncDialog(self.db, profile_id=prof_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_data()
            self.on_environment_changed()


class InvestimentosConfigTab(QWidget):
    """Aba de Parâmetros de Investimento & Rendimento (Caixinhas CDB / Taxa CDI)."""

    def __init__(
        self,
        db: ConnectionManager,
        on_environment_changed: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.on_environment_changed = on_environment_changed
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 12, 0, 32)
        root.setSpacing(16)

        cdi_card = QFrame()
        cdi_card.setObjectName("CardSurface")
        cdi_lay = QVBoxLayout(cdi_card)
        cdi_lay.setContentsMargins(20, 18, 20, 18)
        cdi_lay.setSpacing(14)

        cdi_head = QHBoxLayout()
        cdi_t_col = QVBoxLayout()
        cdi_t_col.setSpacing(4)
        lbl_cdi_title = QLabel("Parâmetros de Investimento & Rendimento Automático")
        lbl_cdi_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        lbl_cdi_sub = QLabel(
            "Configure a taxa CDI anual padrão utilizada para calcular o rendimento diário "
            "composto das Caixinhas CDB (convenção 252 dias úteis B3 / Anbima, 100% offline)."
        )
        lbl_cdi_sub.setObjectName("MutedText")
        lbl_cdi_sub.setWordWrap(True)
        cdi_t_col.addWidget(lbl_cdi_title)
        cdi_t_col.addWidget(lbl_cdi_sub)
        cdi_head.addLayout(cdi_t_col)
        cdi_head.addStretch()
        cdi_lay.addLayout(cdi_head)

        cdi_form_row = QHBoxLayout()
        cdi_form_row.setSpacing(12)

        lbl_taxa = QLabel("Taxa CDI Padrão Anual:")
        lbl_taxa.setStyleSheet("font-weight: 600;")
        self.sp_cdi_taxa = QDoubleSpinBox()
        self.sp_cdi_taxa.setRange(0.0, 100.0)
        self.sp_cdi_taxa.setDecimals(2)
        self.sp_cdi_taxa.setSingleStep(0.25)
        self.sp_cdi_taxa.setSuffix(" % ao ano")
        self.sp_cdi_taxa.setFixedWidth(160)
        self.sp_cdi_taxa.setValue(float(getattr(self.db.settings, "cdi_taxa_anual", 10.75) or 10.75))

        btn_save_cdi = QPushButton("Salvar Taxa CDI")
        btn_save_cdi.setObjectName("PrimaryButton")
        btn_save_cdi.setIcon(get_line_icon("check", size=14, color="#FFFFFF"))
        btn_save_cdi.setMinimumWidth(155)
        btn_save_cdi.setMinimumHeight(32)
        btn_save_cdi.setStyleSheet("QPushButton { padding: 0 16px; font-weight: 600; }")
        btn_save_cdi.clicked.connect(self._on_save_cdi_rate)

        self.lbl_cdi_feedback = QLabel("")
        self.lbl_cdi_feedback.setStyleSheet("color: #17A05E; font-weight: 600;")

        cdi_form_row.addWidget(lbl_taxa)
        cdi_form_row.addWidget(self.sp_cdi_taxa)
        cdi_form_row.addWidget(btn_save_cdi)
        cdi_form_row.addWidget(self.lbl_cdi_feedback)
        cdi_form_row.addStretch()
        cdi_lay.addLayout(cdi_form_row)

        # Card informativo sobre como funciona o rendimento diário
        info_card = QFrame()
        info_card.setObjectName("CardSurface")
        info_lay = QVBoxLayout(info_card)
        info_lay.setContentsMargins(20, 16, 20, 16)
        info_lay.setSpacing(8)

        lbl_info_t = QLabel("Como funciona o rendimento diário de Caixinhas CDB no Plutos:")
        lbl_info_t.setStyleSheet("font-weight: 600; font-size: 14px;")
        info_lay.addWidget(lbl_info_t)

        lbl_info_desc = QLabel(
            "• Cálculo Exato B3: O rendimento utiliza a fórmula oficial (1 + CDI)^(du/252) - 1 considerando apenas dias úteis e feriados nacionais fixos.\n"
            "• Múltiplos Aportes & Resgates: Cada movimentação na conta é calculada individualmente a partir do dia útil em que ocorreu.\n"
            "• 100% Local-First: O cálculo ocorre localmente sem necessidade de conexão com a internet.\n"
            "• Ativação: Em 'Contas Bancárias', ao criar ou editar uma conta, ative a opção 'Caixinha CDB / Rendimento CDI' e defina o percentual desejado (ex.: 100% do CDI)."
        )
        lbl_info_desc.setObjectName("MutedText")
        lbl_info_desc.setWordWrap(True)
        info_lay.addWidget(lbl_info_desc)

        root.addWidget(cdi_card)
        root.addWidget(info_card)
        root.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def refresh_data(self) -> None:
        self.sp_cdi_taxa.setValue(float(getattr(self.db.settings, "cdi_taxa_anual", 10.75) or 10.75))

    def _on_save_cdi_rate(self) -> None:
        rate = round(self.sp_cdi_taxa.value(), 2)
        self.db.settings.cdi_taxa_anual = rate
        self.db.settings.save()
        self.lbl_cdi_feedback.setText("Taxa CDI atualizada com sucesso!")
        if self.on_environment_changed:
            self.on_environment_changed()
        QTimer.singleShot(3500, lambda: self.lbl_cdi_feedback.setText(""))


class ConfiguracoesHubView(QWidget):
    """Hub único de Configurações com sub-abas (reaproveita as views existentes)."""

    def __init__(
        self,
        banco_view: ConfiguracoesView,
        ferramentas_view: FerramentasView,
        db: ConnectionManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banco_view = banco_view
        self.open_finance_tab = OpenFinanceConfigTab(
            db,
            on_environment_changed=getattr(banco_view, "on_environment_changed", lambda: None),
            parent=self,
        )
        self.ferramentas_view = ferramentas_view
        self.ia_tab = AIConfigTab(db, self)
        self.invest_tab = InvestimentosConfigTab(
            db,
            on_environment_changed=getattr(banco_view, "on_environment_changed", lambda: None),
            parent=self,
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.addTab(banco_view, "Banco, Backup e Perfis")
        self.tabs.addTab(self.open_finance_tab, "Open Finance (Pluggy)")
        self.tabs.addTab(ferramentas_view, "Ferramentas")
        self.tabs.addTab(self.ia_tab, "Inteligência Artificial")
        self.tabs.addTab(self.invest_tab, "Investimentos && CDI")
        self.tabs.currentChanged.connect(lambda _i: self.refresh_data())
        root.addWidget(self.tabs)

    def select_tab(self, key: str) -> None:
        if key in TAB_KEYS:
            self.tabs.setCurrentIndex(TAB_KEYS.index(key))

    def refresh_data(self) -> None:
        current = self.tabs.currentWidget()
        if hasattr(current, "refresh_data"):
            current.refresh_data()
