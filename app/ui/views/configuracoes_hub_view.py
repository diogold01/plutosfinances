"""Hub unificado de Configurações: Banco/Backup/Perfis, Ferramentas e Inteligência Artificial (BYOK)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import gemini_key_store as key_store
from app.database.connection_manager import ConnectionManager
from app.domain.services.ai_service import AIService
from app.ui.ai_worker import AITestWorker
from app.ui.views.configuracoes_view import ConfiguracoesView
from app.ui.views.ferramentas_view import FerramentasView

GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.8-flash"]
TAB_KEYS = ("banco", "ferramentas", "ia")


class AIConfigTab(QWidget):
    """Aba de Inteligência Artificial: chave BYOK, modelo e teste de conexão."""

    def __init__(self, db: ConnectionManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = db
        self._worker: Optional[AITestWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
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
        self.ferramentas_view = ferramentas_view
        self.ia_tab = AIConfigTab(db, self)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.addTab(banco_view, "Banco, Backup e Perfis")
        self.tabs.addTab(ferramentas_view, "Ferramentas")
        self.tabs.addTab(self.ia_tab, "Inteligência Artificial")
        self.tabs.currentChanged.connect(lambda _i: self.refresh_data())
        root.addWidget(self.tabs)

    def select_tab(self, key: str) -> None:
        if key in TAB_KEYS:
            self.tabs.setCurrentIndex(TAB_KEYS.index(key))

    def refresh_data(self) -> None:
        current = self.tabs.currentWidget()
        if hasattr(current, "refresh_data"):
            current.refresh_data()
