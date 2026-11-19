"""Hub unificado de Configurações: Banco/Backup/Perfis, Open Finance (Pluggy), Ferramentas e IA (BYOK)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QEvent, QSize, Qt, QUrl, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import ai_key_store as key_store
from app.config.app_settings import DateReferenceMode, clamp_ui_zoom
from app.config.theme_palette import ThemePalette
from app.database.connection_manager import ConnectionManager
from app.database.repositories.profile_repository import ProfileRepository
from app.domain.services.ai_service import AIService
from app.services.pluggy_client import PluggyClient, PluggyConfigManager
from app.ui.ai_worker import AITestWorker
from app.ui.components import Badge, BaseModalDialog
from app.ui.icons import get_line_icon, get_line_pixmap
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
        content.setObjectName("AIConfigHost")
        content.setStyleSheet("QWidget#AIConfigHost { background: transparent; }")
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 4, 0, 20)
        card = QFrame()
        card.setObjectName("CardSurface")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(12)

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
        content.setObjectName("OpenFinanceHost")
        content.setStyleSheet("QWidget#OpenFinanceHost { background: transparent; }")
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 4, 0, 20)
        root.setSpacing(16)

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
        content.setObjectName("InvestConfigHost")
        content.setStyleSheet("QWidget#InvestConfigHost { background: transparent; }")
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 4, 0, 20)
        root.setSpacing(16)

        cdi_card = QFrame()
        cdi_card.setObjectName("CardSurface")
        cdi_lay = QVBoxLayout(cdi_card)
        cdi_lay.setContentsMargins(22, 20, 22, 20)
        cdi_lay.setSpacing(18)

        cdi_head = QHBoxLayout()
        cdi_t_col = QVBoxLayout()
        cdi_t_col.setSpacing(6)
        lbl_cdi_title = QLabel("Parâmetros de Investimento & Rendimento Automático")
        lbl_cdi_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        lbl_cdi_sub = QLabel(
            "Configure a taxa CDI anual padrão utilizada para calcular o rendimento diário "
            "composto das Caixinhas CDB (convenção 252 dias úteis B3 / Anbima, 100% offline)."
        )
        lbl_cdi_sub.setObjectName("MutedText")
        lbl_cdi_sub.setWordWrap(True)
        cdi_t_col.addWidget(lbl_cdi_title)
        cdi_t_col.addWidget(lbl_cdi_sub)
        cdi_head.addLayout(cdi_t_col, 1)
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
        self.sp_cdi_taxa.setFixedHeight(36)
        self.sp_cdi_taxa.setValue(float(getattr(self.db.settings, "cdi_taxa_anual", 10.75) or 10.75))

        btn_save_cdi = QPushButton("Salvar Taxa CDI")
        btn_save_cdi.setObjectName("PrimaryButton")
        btn_save_cdi.setIcon(get_line_icon("check", size=14, color="#FFFFFF"))
        btn_save_cdi.setMinimumWidth(155)
        btn_save_cdi.setFixedHeight(36)
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


class EditAccountDataDialog(BaseModalDialog):
    """Modal estilo Arthas para editar Nome, E-mail e Telefone em Minha conta -> Perfil."""

    def __init__(
        self,
        name: str,
        email: str,
        phone: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            title="Editar seus dados",
            subtitle="Atualize o nome, e-mail e telefone vinculados à sua conta local.",
            min_width=440,
            parent=parent,
        )
        self.set_confirm_text("Salvar")

        form = QFormLayout()
        form.setSpacing(12)

        self.ed_name = QLineEdit(name)
        self.ed_name.setPlaceholderText("Ex.: DIOGO LIMA DUARTE")

        self.ed_email = QLineEdit(email)
        self.ed_email.setPlaceholderText("Ex.: seuemail@gmail.com")

        self.ed_phone = QLineEdit(phone)
        self.ed_phone.setPlaceholderText("Ex.: 5567999999999")

        form.addRow("Nome:", self.ed_name)
        form.addRow("E-mail:", self.ed_email)
        form.addRow("Telefone:", self.ed_phone)
        self.content_layout.addLayout(form)


class _AccountNavRow(QFrame):
    """Item clicável do menu lateral esquerdo de Minha conta (ícone + rótulo + badge/status)."""

    def __init__(
        self,
        key: str,
        label: str,
        icon_name: str,
        on_clicked: Callable[[str], None],
        *,
        status_text: str = "",
        pill_variant: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.icon_name = icon_name
        self._on_clicked = on_clicked
        self._pill_variant = pill_variant
        self.setObjectName("AccountNavItem")
        self.setProperty("active", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)

        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(18, 18)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_icon)

        self.lbl_text = QLabel(label)
        self.lbl_text.setStyleSheet("font-size: 13px; font-weight: 500; background: transparent; border: none;")
        lay.addWidget(self.lbl_text, 1)

        if pill_variant:
            lbl_pill = QLabel(status_text or "Ativo")
            lbl_pill.setObjectName("AccountNavPill")
            lbl_pill.setFixedHeight(20)
            lbl_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.badge_widget: Optional[QLabel] = lbl_pill
        elif status_text:
            lbl_st = QLabel(status_text)
            lbl_st.setObjectName("MutedText")
            lbl_st.setStyleSheet("font-size: 11px; background: transparent; border: none;")
            self.badge_widget = lbl_st
        else:
            self.badge_widget = None

        if self.badge_widget is not None:
            lay.addWidget(self.badge_widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_status_text(self, text: str) -> None:
        if self.badge_widget is not None:
            self.badge_widget.setText(text)
            self.badge_widget.setVisible(bool(text))

    def set_active(self, active: bool, pal: ThemePalette) -> None:
        self.setProperty("active", active)
        ico_col = pal.primary if active else pal.text_secondary
        txt_col = pal.primary if active else pal.text_primary
        weight = 700 if active else 500
        self.lbl_icon.setPixmap(get_line_pixmap(self.icon_name, color=ico_col, size=16))
        self.lbl_text.setStyleSheet(
            f"font-size: 13px; font-weight: {weight}; color: {txt_col}; background: transparent; border: none;"
        )
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_clicked(self.key)
            event.accept()
            return
        super().mousePressEvent(event)


class AccountProfileTab(QWidget):
    """Seção 'Perfil' estilo Arthas: Card 'Seus dados' + Card 'Família'."""

    def __init__(
        self,
        db: ConnectionManager,
        banco_view: ConfiguracoesView,
        on_changed: Callable[[], None],
        on_open_security: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.banco_view = banco_view
        self.profile_repo = ProfileRepository(db)
        self.on_changed = on_changed
        self.on_open_security = on_open_security
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        host = QWidget()
        host.setObjectName("AccountProfileHost")
        host.setStyleSheet("QWidget#AccountProfileHost { background: transparent; }")
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 4, 0, 20)
        root.setSpacing(18)

        # Card 1: Seus dados
        self.data_card = QFrame()
        self.data_card.setObjectName("CardSurface")
        dc = QVBoxLayout(self.data_card)
        dc.setContentsMargins(0, 0, 0, 0)
        dc.setSpacing(0)

        hdr = QWidget()
        hdr_l = QHBoxLayout(hdr)
        hdr_l.setContentsMargins(22, 18, 22, 14)
        lbl_sd = QLabel("Seus dados")
        lbl_sd.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.btn_edit_account = QPushButton("Editar")
        self.btn_edit_account.setObjectName("SecondaryButton")
        self.btn_edit_account.setIcon(get_line_icon("pencil", size=14))
        self.btn_edit_account.setFixedHeight(32)
        self.btn_edit_account.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_account.clicked.connect(self._open_edit_dialog)
        hdr_l.addWidget(lbl_sd, 0, Qt.AlignmentFlag.AlignVCenter)
        hdr_l.addStretch()
        hdr_l.addWidget(self.btn_edit_account, 0, Qt.AlignmentFlag.AlignVCenter)
        dc.addWidget(hdr)

        sep1 = QFrame()
        sep1.setObjectName("ModalSeparator")
        sep1.setFixedHeight(1)
        dc.addWidget(sep1)

        # Linha Nome
        r_name = QWidget()
        rn_l = QVBoxLayout(r_name)
        rn_l.setContentsMargins(22, 14, 22, 14)
        rn_l.setSpacing(3)
        lbl_k_n = QLabel("Nome")
        lbl_k_n.setObjectName("MutedText")
        lbl_k_n.setStyleSheet("font-size: 11px;")
        self.lbl_val_name = QLabel("—")
        self.lbl_val_name.setStyleSheet("font-size: 13px; font-weight: 600;")
        rn_l.addWidget(lbl_k_n)
        rn_l.addWidget(self.lbl_val_name)
        dc.addWidget(r_name)

        sep2 = QFrame()
        sep2.setObjectName("ModalSeparator")
        sep2.setFixedHeight(1)
        dc.addWidget(sep2)

        # Linha E-mail + Trocar e-mail
        r_mail = QWidget()
        rm_l = QHBoxLayout(r_mail)
        rm_l.setContentsMargins(22, 14, 22, 14)
        rm_col = QVBoxLayout()
        rm_col.setContentsMargins(0, 0, 0, 0)
        rm_col.setSpacing(3)
        lbl_k_m = QLabel("E-mail")
        lbl_k_m.setObjectName("MutedText")
        lbl_k_m.setStyleSheet("font-size: 11px;")
        self.lbl_val_email = QLabel("—")
        self.lbl_val_email.setStyleSheet("font-size: 13px; font-weight: 600;")
        rm_col.addWidget(lbl_k_m)
        rm_col.addWidget(self.lbl_val_email)
        self.btn_change_email = QPushButton("Trocar e-mail")
        self.btn_change_email.setObjectName("SecondaryButton")
        self.btn_change_email.setFixedHeight(32)
        self.btn_change_email.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_email.clicked.connect(self._open_change_email)
        rm_l.addLayout(rm_col, 1)
        rm_l.addWidget(self.btn_change_email, 0, Qt.AlignmentFlag.AlignVCenter)
        dc.addWidget(r_mail)

        sep3 = QFrame()
        sep3.setObjectName("ModalSeparator")
        sep3.setFixedHeight(1)
        dc.addWidget(sep3)

        # Linha Telefone
        r_phone = QWidget()
        rp_l = QVBoxLayout(r_phone)
        rp_l.setContentsMargins(22, 14, 22, 16)
        rp_l.setSpacing(3)
        lbl_k_p = QLabel("Telefone")
        lbl_k_p.setObjectName("MutedText")
        lbl_k_p.setStyleSheet("font-size: 11px;")
        self.lbl_val_phone = QLabel("—")
        self.lbl_val_phone.setStyleSheet("font-size: 13px; font-weight: 600;")
        rp_l.addWidget(lbl_k_p)
        rp_l.addWidget(self.lbl_val_phone)
        dc.addWidget(r_phone)

        root.addWidget(self.data_card)

        # Card 2: Família / Perfis
        self.family_card = QFrame()
        self.family_card.setObjectName("CardSurface")
        fc = QVBoxLayout(self.family_card)
        fc.setContentsMargins(22, 18, 22, 20)
        fc.setSpacing(14)

        f_hdr = QVBoxLayout()
        f_hdr.setSpacing(3)
        lbl_ft = QLabel("Família")
        lbl_ft.setStyleSheet("font-size: 14px; font-weight: 700;")
        lbl_fs = QLabel(
            "Cônjuge, filhos e outros perfis próximos para organizar as finanças em conjunto."
        )
        lbl_fs.setObjectName("MutedText")
        lbl_fs.setStyleSheet("font-size: 12px;")
        lbl_fs.setWordWrap(True)
        f_hdr.addWidget(lbl_ft)
        f_hdr.addWidget(lbl_fs)
        fc.addLayout(f_hdr)

        self.family_inner = QFrame()
        self.family_inner.setObjectName("FamilyInnerBox")
        self.family_inner_lay = QVBoxLayout(self.family_inner)
        self.family_inner_lay.setContentsMargins(24, 24, 24, 24)
        self.family_inner_lay.setSpacing(10)
        fc.addWidget(self.family_inner)

        root.addWidget(self.family_card)
        root.addStretch()

        scroll.setWidget(host)
        outer.addWidget(scroll)

    def refresh_data(self) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        active_prof = self.profile_repo.get_active_profile()
        profiles = self.profile_repo.list_profiles(include_archived=False)

        disp_name = (self.db.settings.user_display_name or "").strip() or active_prof.name.upper()
        disp_email = (
            (self.db.settings.user_email or "").strip()
            or f"{active_prof.name.strip().lower().replace(' ', '.')}@plutos.local"
        )
        disp_phone = (self.db.settings.user_phone or "").strip() or "Não informado"

        self.lbl_val_name.setText(disp_name)
        self.lbl_val_email.setText(disp_email)
        self.lbl_val_phone.setText(disp_phone)

        while self.family_inner_lay.count():
            it = self.family_inner_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif it.layout() is not None:
                while it.layout().count():
                    sub = it.layout().takeAt(0)
                    sw = sub.widget()
                    if sw is not None:
                        sw.hide()
                        sw.setParent(None)
                        sw.deleteLater()

        other_profiles = [p for p in profiles if p.id != active_prof.id]
        if not other_profiles:
            lbl_ico = QLabel()
            lbl_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_ico.setStyleSheet("border: none; background: transparent;")
            lbl_ico.setPixmap(get_line_pixmap("users", color=pal.text_secondary, size=24))
            lbl_emp_t = QLabel("Nenhum relacionamento cadastrado")
            lbl_emp_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_emp_t.setStyleSheet("font-size: 13px; font-weight: 700; border: none; background: transparent;")
            lbl_emp_s = QLabel(
                "Cadastre cônjuge, filhos ou perfis adicionais para acompanhar dados importantes."
            )
            lbl_emp_s.setObjectName("MutedText")
            lbl_emp_s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_emp_s.setWordWrap(True)
            lbl_emp_s.setStyleSheet("font-size: 12px; border: none; background: transparent;")

            btn_add = QPushButton("Adicionar relacionamento")
            btn_add.setObjectName("PrimaryButton")
            btn_add.setIcon(get_line_icon("plus", color="#FFFFFF", size=14))
            btn_add.setFixedHeight(36)
            btn_add.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_add.clicked.connect(self._on_add_family_member)

            self.family_inner_lay.addWidget(lbl_ico)
            self.family_inner_lay.addWidget(lbl_emp_t)
            self.family_inner_lay.addWidget(lbl_emp_s)
            self.family_inner_lay.addSpacing(4)
            self.family_inner_lay.addWidget(btn_add, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            for prof in other_profiles:
                row = QHBoxLayout()
                lbl_pn = QLabel(prof.name)
                lbl_pn.setStyleSheet("font-size: 13px; font-weight: 600; border: none; background: transparent;")
                row.addWidget(lbl_pn, 1)
                row.addWidget(Badge(prof.currency or "BRL", variant="info"))
                self.family_inner_lay.addLayout(row)

            act_row = QHBoxLayout()
            btn_add = QPushButton("Adicionar relacionamento")
            btn_add.setObjectName("PrimaryButton")
            btn_add.setIcon(get_line_icon("plus", color="#FFFFFF", size=14))
            btn_add.clicked.connect(self._on_add_family_member)
            btn_manage = QPushButton("Gerenciar perfis")
            btn_manage.setObjectName("SecondaryButton")
            btn_manage.clicked.connect(self.on_open_security)
            act_row.addWidget(btn_add)
            act_row.addWidget(btn_manage)
            act_row.addStretch()
            self.family_inner_lay.addLayout(act_row)

    def _open_edit_dialog(self) -> None:
        active_prof = self.profile_repo.get_active_profile()
        cur_name = (self.db.settings.user_display_name or "").strip() or active_prof.name.upper()
        cur_email = (self.db.settings.user_email or "").strip()
        cur_phone = (self.db.settings.user_phone or "").strip()

        dlg = EditAccountDataDialog(cur_name, cur_email, cur_phone, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.db.settings.user_display_name = dlg.ed_name.text().strip()
        self.db.settings.user_email = dlg.ed_email.text().strip()
        self.db.settings.user_phone = dlg.ed_phone.text().strip()
        self.db.settings.save()
        self.on_changed()

    def _open_change_email(self) -> None:
        cur_email = (self.db.settings.user_email or "").strip()
        new_email, ok = QInputDialog.getText(
            self, "Trocar e-mail", "Informe o novo endereço de e-mail:", text=cur_email
        )
        if ok:
            self.db.settings.user_email = new_email.strip()
            self.db.settings.save()
            self.on_changed()

    def _on_add_family_member(self) -> None:
        self.banco_view._on_new_profile()
        self.on_changed()


class AccountAlertsTab(QWidget):
    """Seção 'Avisos e notificações' em Minha conta."""

    def __init__(
        self,
        db: ConnectionManager,
        on_changed: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.on_changed = on_changed
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 20)
        outer.setSpacing(16)

        card = QFrame()
        card.setObjectName("CardSurface")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(14)

        lbl_t = QLabel("Alertas do sistema e ciclos de backup")
        lbl_t.setStyleSheet("font-size: 14px; font-weight: 700;")
        lbl_s = QLabel(
            "O Plutos monitora localmente contas vencendo hoje/amanhã, fechamento de faturas "
            "nos próximos 3 dias e mutações pendentes de backup automático."
        )
        lbl_s.setObjectName("MutedText")
        lbl_s.setWordWrap(True)
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_s)

        self.chk_backup_auto = QCheckBox("Ativar avisos e execução do backup automático a cada 3 horas")
        self.chk_backup_auto.setChecked(bool(self.db.settings.backup_enabled))
        self.chk_backup_auto.toggled.connect(self._on_toggle_backup)
        lay.addWidget(self.chk_backup_auto)

        outer.addWidget(card)
        outer.addStretch()

    def _on_toggle_backup(self, checked: bool) -> None:
        self.db.settings.backup_enabled = bool(checked)
        self.db.settings.save()
        self.on_changed()

    def refresh_data(self) -> None:
        self.chk_backup_auto.blockSignals(True)
        self.chk_backup_auto.setChecked(bool(self.db.settings.backup_enabled))
        self.chk_backup_auto.blockSignals(False)


class AccountPreferencesTab(QWidget):
    """Seção 'Preferências' em Minha conta: Regime contábil, Tema e Detalhes Técnicos."""

    def __init__(
        self,
        db: ConnectionManager,
        on_changed: Callable[[], None],
        on_open_invest: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.on_changed = on_changed
        self.on_open_invest = on_open_invest
        self._syncing_zoom_ui: bool = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 20)
        outer.setSpacing(16)

        card = QFrame()
        card.setObjectName("CardSurface")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 18, 22, 20)
        lay.setSpacing(14)

        lbl_t = QLabel("Regime contábil e exibição")
        lbl_t.setStyleSheet("font-size: 14px; font-weight: 700;")
        lbl_s = QLabel(
            "Defina como receitas, despesas e orçamentos são agrupados nos meses e personalize a aparência."
        )
        lbl_s.setObjectName("MutedText")
        lbl_s.setWordWrap(True)
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_s)

        form = QFormLayout()
        form.setSpacing(12)

        self.cb_regime = QComboBox()
        self.cb_regime.addItem("Competência (Data do Lançamento)", DateReferenceMode.LANCAMENTO.value)
        self.cb_regime.addItem("Caixa / Vencimento", DateReferenceMode.VENCIMENTO.value)
        self.cb_regime.addItem("Lançamento Distribuído", DateReferenceMode.LANCAMENTO_DISTRIBUIR.value)
        self.cb_regime.addItem("Efetivação (Pago / Recebido)", DateReferenceMode.EFETIVACAO.value)
        self.cb_regime.currentIndexChanged.connect(self._on_regime_changed)
        form.addRow("Regime padrão:", self.cb_regime)

        self.chk_tech = QCheckBox("Exibir contadores técnicos de mutações SQLite na barra de status")
        self.chk_tech.toggled.connect(self._on_tech_toggled)
        form.addRow("Diagnóstico:", self.chk_tech)

        lay.addLayout(form)

        row_inv = QHBoxLayout()
        btn_inv = QPushButton("Configurar Taxa CDI e Rendimentos")
        btn_inv.setObjectName("SecondaryButton")
        btn_inv.setIcon(get_line_icon("trending_up", size=14))
        btn_inv.clicked.connect(self.on_open_invest)
        row_inv.addWidget(btn_inv)
        row_inv.addStretch()
        lay.addLayout(row_inv)

        outer.addWidget(card)

        # Card 2: Aparência e Zoom da Interface (60% a 150% + Modo Automático)
        zoom_card = QFrame()
        zoom_card.setObjectName("CardSurface")
        z_lay = QVBoxLayout(zoom_card)
        z_lay.setContentsMargins(22, 18, 22, 20)
        z_lay.setSpacing(12)

        lbl_zt = QLabel("Aparência e zoom da interface")
        lbl_zt.setStyleSheet("font-size: 14px; font-weight: 700;")
        lbl_zs = QLabel(
            "Afaste a tela (60%–90%) para visualizar mais lançamentos simultaneamente ou amplie até 150%. "
            "Atalhos rápidos: Ctrl + '-', Ctrl + '+', Ctrl + '0' e Ctrl + Roda do mouse."
        )
        lbl_zs.setObjectName("MutedText")
        lbl_zs.setWordWrap(True)
        z_lay.addWidget(lbl_zt)
        z_lay.addWidget(lbl_zs)

        slider_row = QHBoxLayout()
        slider_row.setSpacing(12)

        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(60, 150)
        self.slider_zoom.setSingleStep(5)
        self.slider_zoom.setPageStep(5)
        self.slider_zoom.setTickInterval(10)
        self.slider_zoom.setValue(100)
        self.slider_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider_zoom.valueChanged.connect(self._on_zoom_slider_changed)
        slider_row.addWidget(self.slider_zoom, 1)

        self.lbl_zoom_val = QLabel("100%")
        self.lbl_zoom_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_zoom_val.setMinimumWidth(52)
        self.lbl_zoom_val.setStyleSheet("font-size: 13px; font-weight: 700;")
        slider_row.addWidget(self.lbl_zoom_val, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_zoom_reset = QPushButton("Restaurar 100%")
        self.btn_zoom_reset.setObjectName("SecondaryButton")
        self.btn_zoom_reset.setMinimumHeight(32)
        self.btn_zoom_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom_reset.clicked.connect(self._on_zoom_reset_clicked)
        slider_row.addWidget(self.btn_zoom_reset, 0, Qt.AlignmentFlag.AlignVCenter)

        z_lay.addLayout(slider_row)

        self.chk_zoom_auto = QCheckBox(
            "Automático (ajustar zoom proporcionalmente ao redimensionar a janela)"
        )
        self.chk_zoom_auto.toggled.connect(self._on_zoom_auto_toggled)
        z_lay.addWidget(self.chk_zoom_auto)

        outer.addWidget(zoom_card)
        outer.addStretch()

    def _on_zoom_slider_changed(self, raw_val: int) -> None:
        if self._syncing_zoom_ui:
            return
        snapped = max(60, min(150, int(round(raw_val / 5.0) * 5)))
        if snapped != raw_val:
            self.slider_zoom.blockSignals(True)
            self.slider_zoom.setValue(snapped)
            self.slider_zoom.blockSignals(False)
        self.lbl_zoom_val.setText(f"{snapped}%")
        self.chk_zoom_auto.blockSignals(True)
        self.chk_zoom_auto.setChecked(False)
        self.chk_zoom_auto.blockSignals(False)

        win = self.window()
        if hasattr(win, "set_ui_zoom"):
            win.set_ui_zoom(snapped / 100.0, manual=True)
        else:
            self.db.settings.ui_zoom_auto = False
            self.db.settings.ui_zoom_factor = clamp_ui_zoom(snapped / 100.0)
            self.db.settings.save()

    def _on_zoom_reset_clicked(self) -> None:
        win = self.window()
        if hasattr(win, "set_ui_zoom"):
            win.set_ui_zoom(1.0, manual=True)
        else:
            self.db.settings.ui_zoom_auto = False
            self.db.settings.ui_zoom_factor = 1.0
            self.db.settings.save()
            self.refresh_data()

    def _on_zoom_auto_toggled(self, checked: bool) -> None:
        if self._syncing_zoom_ui:
            return
        win = self.window()
        if hasattr(win, "set_ui_zoom_auto"):
            win.set_ui_zoom_auto(bool(checked))
        else:
            self.db.settings.ui_zoom_auto = bool(checked)
            self.db.settings.save()
            self.refresh_data()

    def _on_regime_changed(self, idx: int) -> None:
        if idx < 0:
            return
        mode_val = str(self.cb_regime.currentData())
        if mode_val != self.db.settings.date_reference_mode:
            self.db.settings.date_reference_mode = mode_val
            self.db.settings.save()
            self.on_changed()

    def _on_tech_toggled(self, checked: bool) -> None:
        self.db.settings.show_technical_details = bool(checked)
        self.db.settings.save()
        self.on_changed()

    def refresh_data(self) -> None:
        self.cb_regime.blockSignals(True)
        idx = self.cb_regime.findData(self.db.settings.date_reference_mode)
        if idx >= 0:
            self.cb_regime.setCurrentIndex(idx)
        self.cb_regime.blockSignals(False)

        self.chk_tech.blockSignals(True)
        self.chk_tech.setChecked(bool(getattr(self.db.settings, "show_technical_details", True)))
        self.chk_tech.blockSignals(False)

        self._syncing_zoom_ui = True
        try:
            z = clamp_ui_zoom(getattr(self.db.settings, "ui_zoom_factor", 1.0))
            pct = max(60, min(150, int(round(z * 100))))
            self.slider_zoom.setValue(pct)
            self.lbl_zoom_val.setText(f"{pct}%")
            self.chk_zoom_auto.setChecked(bool(getattr(self.db.settings, "ui_zoom_auto", False)))
        finally:
            self._syncing_zoom_ui = False


class ConfiguracoesHubView(QWidget):
    """Tela 'Minha conta' em layout Master-Detail de 2 colunas estilo Arthas."""

    SECTION_META = {
        "perfil": ("Perfil", "Seus dados e os perfis da família."),
        "banco": ("Segurança e Banco de Dados", "Base local SQLite, backups automáticos, restauração e perfis."),
        "avisos": ("Avisos e notificações", "Alertas de vencimentos, faturas próximas e ciclo de backup."),
        "preferencias": ("Preferências", "Regime contábil de competência/caixa e opções de exibição."),
        "ferramentas": ("Privacidade e ferramentas", "Importação, exportação, auditoria e manutenção local."),
        "open_finance": ("Open Finance (Pluggy)", "Sincronização bancária automática e credenciais."),
        "ia": ("Inteligência Artificial", "Chave local Gemini (BYOK) para lançamento rápido por texto."),
        "investimentos": ("Investimentos e CDI", "Taxa CDI anual padrão para cálculo diário de Caixinhas CDB."),
    }

    def __init__(
        self,
        banco_view: ConfiguracoesView,
        ferramentas_view: FerramentasView,
        db: ConnectionManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_repo = ProfileRepository(db)
        self.banco_view = banco_view
        self._env_cb = getattr(banco_view, "on_environment_changed", lambda: None)
        self.open_finance_tab = OpenFinanceConfigTab(
            db,
            on_environment_changed=self._env_cb,
            parent=self,
        )
        self.ferramentas_view = ferramentas_view
        self.ia_tab = AIConfigTab(db, self)
        self.invest_tab = InvestimentosConfigTab(
            db,
            on_environment_changed=self._env_cb,
            parent=self,
        )
        self._active_section: str = "perfil"
        self._nav_rows: dict[str, _AccountNavRow] = {}
        self._build_ui()
        self.select_section("perfil")

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        # Cabeçalho superior estilo Arthas ("Minha conta")
        hdr_col = QVBoxLayout()
        hdr_col.setContentsMargins(0, 0, 0, 0)
        hdr_col.setSpacing(4)
        self.lbl_page_title = QLabel("Minha conta")
        self.lbl_page_title.setObjectName("SectionTitle")
        self.lbl_page_title.setStyleSheet("font-size: 24px; font-weight: 700;")
        self.lbl_page_subtitle = QLabel(
            "Seus dados, a segurança da conta, os avisos e as preferências, num lugar só."
        )
        self.lbl_page_subtitle.setObjectName("MutedText")
        self.lbl_page_subtitle.setStyleSheet("font-size: 13px;")
        hdr_col.addWidget(self.lbl_page_title)
        hdr_col.addWidget(self.lbl_page_subtitle)
        outer.addLayout(hdr_col)

        # Container cinza suave de 2 colunas (Master à esquerda + Detail à direita)
        self.workspace_frame = QFrame()
        self.workspace_frame.setObjectName("AccountWorkspaceFrame")
        ws_lay = QHBoxLayout(self.workspace_frame)
        ws_lay.setContentsMargins(24, 24, 24, 24)
        ws_lay.setSpacing(28)

        # Coluna Esquerda: Card Branco de Navegação (264px)
        self.nav_card = QFrame()
        self.nav_card.setObjectName("AccountNavCard")
        self.nav_card.setFixedWidth(264)
        self.nav_card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        nav_v = QVBoxLayout(self.nav_card)
        nav_v.setContentsMargins(12, 16, 12, 12)
        nav_v.setSpacing(4)

        # Identidade no topo do card esquerdo (Avatar 40x40 + Nome + E-mail)
        id_row = QHBoxLayout()
        id_row.setContentsMargins(6, 0, 6, 12)
        id_row.setSpacing(12)
        self.lbl_nav_avatar = QLabel("PE")
        self.lbl_nav_avatar.setObjectName("AccountNavAvatar")
        self.lbl_nav_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        id_col = QVBoxLayout()
        id_col.setContentsMargins(0, 0, 0, 0)
        id_col.setSpacing(1)
        self.lbl_nav_name = QLabel("PESSOAL")
        self.lbl_nav_name.setStyleSheet("font-size: 12px; font-weight: 700;")
        self.lbl_nav_email = QLabel("pessoal@plutos.local")
        self.lbl_nav_email.setObjectName("MutedText")
        self.lbl_nav_email.setStyleSheet("font-size: 11px;")
        id_col.addWidget(self.lbl_nav_name)
        id_col.addWidget(self.lbl_nav_email)
        id_row.addWidget(self.lbl_nav_avatar)
        id_row.addLayout(id_col, 1)
        nav_v.addLayout(id_row)

        nav_defs = [
            ("perfil", "Perfil", "user", "", None),
            ("banco", "Segurança", "shield", "Local", "warning"),
            ("avisos", "Avisos e notificações", "bell", "Ativos", None),
            ("preferencias", "Preferências", "tool", "Vencimento", None),
            ("ferramentas", "Privacidade e suporte", "lock", "", None),
            ("open_finance", "Open Finance", "bank", "Pluggy", None),
            ("ia", "Inteligência Artificial", "sparkles", "BYOK", None),
            ("investimentos", "Investimentos e CDI", "trending_up", "10,75%", None),
        ]
        for key, label, ico, st_txt, pill_var in nav_defs:
            row_w = _AccountNavRow(
                key=key,
                label=label,
                icon_name=ico,
                on_clicked=self.select_section,
                status_text=st_txt,
                pill_variant=pill_var,
                parent=self.nav_card,
            )
            nav_v.addWidget(row_w)
            self._nav_rows[key] = row_w

        sep_nav = QFrame()
        sep_nav.setObjectName("ModalSeparator")
        sep_nav.setFixedHeight(1)
        nav_v.addSpacing(4)
        nav_v.addWidget(sep_nav)
        nav_v.addSpacing(2)

        self.btn_nav_logout = QPushButton("  Sair")
        self.btn_nav_logout.setObjectName("NavButton")
        self.btn_nav_logout.setIcon(get_line_icon("logout", size=16))
        self.btn_nav_logout.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_logout.clicked.connect(lambda: self.window().close())
        nav_v.addWidget(self.btn_nav_logout)

        ws_lay.addWidget(self.nav_card, 0, Qt.AlignmentFlag.AlignTop)

        # Coluna Direita: Título da Seção Ativa + Stack de Detalhes (topo alinhado com nav_card)
        detail_col = QVBoxLayout()
        detail_col.setContentsMargins(0, 0, 0, 0)
        detail_col.setSpacing(12)

        d_hdr = QVBoxLayout()
        d_hdr.setContentsMargins(0, 0, 0, 2)
        d_hdr.setSpacing(2)
        self.lbl_detail_title = QLabel("Perfil")
        self.lbl_detail_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.lbl_detail_subtitle = QLabel("Seus dados e os perfis da família.")
        self.lbl_detail_subtitle.setObjectName("MutedText")
        self.lbl_detail_subtitle.setStyleSheet("font-size: 12px;")
        d_hdr.addWidget(self.lbl_detail_title)
        d_hdr.addWidget(self.lbl_detail_subtitle)
        detail_col.addLayout(d_hdr)

        self.detail_stack = QStackedWidget()
        self.detail_stack.setObjectName("AccountDetailStack")
        self.detail_stack.setStyleSheet("QStackedWidget#AccountDetailStack { background: transparent; }")

        self.perfil_tab = AccountProfileTab(
            self.db,
            self.banco_view,
            on_changed=self._notify_and_refresh,
            on_open_security=lambda: self.select_section("banco"),
            parent=self,
        )
        self.avisos_tab = AccountAlertsTab(
            self.db,
            on_changed=self._notify_and_refresh,
            parent=self,
        )
        self.preferencias_tab = AccountPreferencesTab(
            self.db,
            on_changed=self._notify_and_refresh,
            on_open_invest=lambda: self.select_section("investimentos"),
            parent=self,
        )

        # QTabWidget preservado (tabBar oculto) para 100% de compatibilidade com contratos legados
        self.tabs = QTabWidget()
        self.tabs.tabBar().setVisible(False)
        self.tabs.addTab(self.banco_view, "Banco, Backup e Perfis")
        self.tabs.addTab(self.open_finance_tab, "Open Finance (Pluggy)")
        self.tabs.addTab(self.ferramentas_view, "Ferramentas")
        self.tabs.addTab(self.ia_tab, "Inteligência Artificial")
        self.tabs.addTab(self.invest_tab, "Investimentos && CDI")
        self.tabs.currentChanged.connect(lambda _i: self._refresh_active_tab_widget())

        self.detail_stack.addWidget(self.perfil_tab)
        self.detail_stack.addWidget(self.avisos_tab)
        self.detail_stack.addWidget(self.preferencias_tab)
        self.detail_stack.addWidget(self.tabs)

        detail_col.addWidget(self.detail_stack, 1)
        ws_lay.addLayout(detail_col, 1)

        outer.addWidget(self.workspace_frame, 1)

    @staticmethod
    def _compute_initials(name: str) -> str:
        parts = [p for p in name.strip().split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return "PL"

    def _notify_and_refresh(self) -> None:
        if callable(self._env_cb):
            self._env_cb()
        self.refresh_data()

    def _refresh_active_tab_widget(self) -> None:
        current = self.tabs.currentWidget()
        if hasattr(current, "refresh_data"):
            current.refresh_data()

    def select_section(self, key: str) -> None:
        if key not in self.SECTION_META:
            return
        self._active_section = key
        title, sub = self.SECTION_META[key]
        self.lbl_detail_title.setText(title)
        self.lbl_detail_subtitle.setText(sub)

        if key == "perfil":
            self.detail_stack.setCurrentWidget(self.perfil_tab)
        elif key == "avisos":
            self.detail_stack.setCurrentWidget(self.avisos_tab)
        elif key == "preferencias":
            self.detail_stack.setCurrentWidget(self.preferencias_tab)
        elif key in TAB_KEYS:
            self.tabs.setCurrentIndex(TAB_KEYS.index(key))
            self.detail_stack.setCurrentWidget(self.tabs)

        self.refresh_data()

    def select_tab(self, key: str) -> None:
        if key in TAB_KEYS or key in self.SECTION_META:
            self.select_section(key)

    def refresh_data(self) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        active_prof = self.profile_repo.get_active_profile()

        disp_name = (self.db.settings.user_display_name or "").strip() or active_prof.name.upper()
        disp_email = (
            (self.db.settings.user_email or "").strip()
            or f"{active_prof.name.strip().lower().replace(' ', '.')}@plutos.local"
        )
        self.lbl_nav_avatar.setText(self._compute_initials(disp_name))
        self.lbl_nav_name.setText(disp_name.upper())
        self.lbl_nav_email.setText(disp_email)
        self.btn_nav_logout.setIcon(get_line_icon("logout", color=pal.text_secondary, size=16))

        # Atualiza subtítulos dinâmicos das linhas laterais (como no Arthas)
        mode_map = {
            DateReferenceMode.LANCAMENTO.value: "Competência",
            DateReferenceMode.VENCIMENTO.value: "Vencimento",
            DateReferenceMode.LANCAMENTO_DISTRIBUIR.value: "Distribuído",
            DateReferenceMode.EFETIVACAO.value: "Efetivação",
        }
        if "preferencias" in self._nav_rows:
            self._nav_rows["preferencias"].set_status_text(
                mode_map.get(self.db.settings.date_reference_mode, "Vencimento")
            )
        if "avisos" in self._nav_rows:
            self._nav_rows["avisos"].set_status_text(
                "Ativos" if self.db.settings.backup_enabled else "Desligados"
            )
        if "investimentos" in self._nav_rows:
            cdi = float(getattr(self.db.settings, "cdi_taxa_anual", 10.75) or 10.75)
            self._nav_rows["investimentos"].set_status_text(f"{cdi:.2f}%".replace(".", ","))

        for k, row_w in self._nav_rows.items():
            row_w.set_active(k == self._active_section, pal)

        self.perfil_tab.refresh_data()
        self.avisos_tab.refresh_data()
        self.preferencias_tab.refresh_data()
        if hasattr(self.banco_view, "refresh_data"):
            self.banco_view.refresh_data()
        current = self.tabs.currentWidget()
        if current is not self.banco_view and hasattr(current, "refresh_data"):
            current.refresh_data()
