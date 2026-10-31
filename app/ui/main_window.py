"""Janela Principal Nativa do Windows (`MainWindow` com `DesktopHeader` e `SideMenu`)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.config.app_settings import DateReferenceMode, IMAGES_DIR
from app.config.theme_palette import ThemePalette
from app.database.backup_service import BackupResult, BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.profile_repository import ProfileRepository
from app.database.repositories.tag_repository import TagRepository
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService
from app.ui.bank_icons import create_color_badge_icon
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import (
    apply_app_theme,
    format_currency,
    format_date_br,
    format_month_year,
)
from app.ui.views.calendario_view import CalendarioView
from app.ui.views.cartoes_view import CartoesView
from app.ui.views.categorias_view import CategoriasView
from app.ui.gemini_button import GeminiButton
from app.ui.views.configuracoes_hub_view import ConfiguracoesHubView
from app.ui.views.configuracoes_view import ConfiguracoesView
from app.ui.views.contas_view import ContasView
from app.ui.views.dashboard_view import DashboardView
from app.ui.views.ferramentas_view import FerramentasView
from app.ui.views.graficos_view import GraficosView
from app.ui.views.objetivos_view import ObjetivosView
from app.ui.views.orcamentos_view import OrcamentosView
from app.ui.views.relatorios_view import RelatoriosView
from app.ui.views.tags_view import TagsView
from app.ui.views.transacoes_view import TransacoesView


class MainWindow(QMainWindow):
    """
    Janela principal nativa Desktop (PySide6 / Qt6) reproduzindo a ergonomia,
    paleta de cores, barra lateral de 216px (`SideMenu`) e cabeçalho fixo (`DesktopHeader`)
    do design system oficial do Plutos.
    """

    NAV_ITEMS = [
        ("dashboard", "Visão geral"),
        ("contas", "Contas bancárias"),
        ("transacoes", "Transações"),
        ("cartoes", "Cartões de crédito"),
        ("orcamentos", "Orçamentos"),
        ("objetivos", "Objetivos"),
        ("relatorios", "Relatórios"),
        ("graficos", "Gráficos"),
        ("categorias", "Categorias"),
        ("tags", "Tags"),
        ("calendario", "Calendário"),
        ("configuracoes", "Configurações"),
    ]

    NAV_ICONS: Dict[str, str] = {
        "dashboard": "home",
        "contas": "bank",
        "transacoes": "list",
        "cartoes": "card",
        "orcamentos": "pie",
        "objetivos": "target",
        "relatorios": "file",
        "graficos": "chart",
        "categorias": "folder",
        "tags": "tag",
        "calendario": "cal",
        "ferramentas": "tool",
        "configuracoes": "db",
    }

    def __init__(
        self,
        db: ConnectionManager,
        backup_service: BackupSchedulerService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.backup_service = backup_service
        self.profile_repo = ProfileRepository(db)
        self.account_repo = AccountRepository(db)
        self.cat_repo = CategoryRepository(db)
        self.tag_repo = TagRepository(db)
        self.tx_service = TransactionService(db)
        self.card_service = CreditCardService(db, self.tx_service)

        today = date.today()
        self.current_month: int = today.month
        self.current_year: int = today.year
        self.active_profile_id: str = self.profile_repo.get_active_profile().id
        self._unread_notifications: List[Tuple[str, str, str, str]] = []

        from app.version import APP_TITLE
        self.setWindowTitle(APP_TITLE)
        self.resize(
            self.db.settings.window_width,
            self.db.settings.window_height,
        )
        logo_path = IMAGES_DIR / "ic_logo_plutos.png"
        if not logo_path.exists():
            logo_path = IMAGES_DIR / "ic_logo_mf.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))

        self._nav_buttons: Dict[str, QPushButton] = {}
        self._views: Dict[str, QWidget] = {}
        self.current_nav_key: str = "dashboard"

        self._build_ui()
        self.backup_service.add_backup_listener(self._on_backup_cycle_finished)
        self.backup_service.add_advance_warning_listener(self._on_backup_advance_warning)

        self._notification_timer = QTimer(self)
        self._notification_timer.setInterval(15000)
        self._notification_timer.timeout.connect(self._check_system_notifications)
        self._notification_timer.start()

        self._refresh_header_state()
        self._check_system_notifications()
        self.navigate_to("dashboard")

    def get_active_context(self) -> tuple[str, int, int, str]:
        """Retorna `(profile_id, mes, ano, texto_busca_global)` para a view ativa."""
        return (
            self.active_profile_id,
            self.current_month,
            self.current_year,
            self.ed_global_search.text(),
        )

    def _build_ui(self) -> None:
        central = QWidget()
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        # Layout horizontal principal: Sidebar à esquerda (full height) + Conteúdo à direita
        main_h = QHBoxLayout(central)
        main_h.setContentsMargins(0, 0, 0, 0)
        main_h.setSpacing(0)

        # -------------------------------------------------------------
        # 1. Barra Lateral de Navegação (SideMenu / 216px)
        # -------------------------------------------------------------
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("SideMenu")
        self.sidebar_frame.setFixedWidth(216)
        s_lay = QVBoxLayout(self.sidebar_frame)
        s_lay.setContentsMargins(12, 16, 12, 12)
        s_lay.setSpacing(6)

        # Cabeçalho da Sidebar: Logo Plutos
        logo_container = QWidget()
        logo_h = QHBoxLayout(logo_container)
        logo_h.setContentsMargins(4, 0, 4, 12)
        logo_h.setSpacing(10)

        self.lbl_logo_badge = QLabel("P")
        self.lbl_logo_badge.setObjectName("BrandBadge")
        self.lbl_logo_badge.setFixedSize(28, 28)
        self.lbl_logo_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_logo_title = QLabel("Plutos")
        self.lbl_logo_title.setObjectName("BrandTitle")

        self.btn_hamburger = QPushButton()
        self.btn_hamburger.setObjectName("IconButton")
        self.btn_hamburger.setFixedSize(28, 28)
        self.btn_hamburger.setIcon(get_line_icon("menu", color=pal.text_secondary, size=16))
        self.btn_hamburger.setToolTip("Recolher / Expandir menu lateral")
        self.btn_hamburger.clicked.connect(self.toggle_sidebar)

        logo_h.addWidget(self.lbl_logo_badge)
        logo_h.addWidget(self.lbl_logo_title)
        logo_h.addStretch()
        logo_h.addWidget(self.btn_hamburger)
        s_lay.addWidget(logo_container)

        # Lista de Itens de Navegação com Scroll transparente
        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("SideMenuScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_container = QWidget()
        nav_container.setObjectName("SideMenuContainer")
        nav_v = QVBoxLayout(nav_container)
        nav_v.setContentsMargins(0, 0, 0, 0)
        nav_v.setSpacing(2)

        for key, label in self.NAV_ITEMS:
            icon_name = self.NAV_ICONS.get(key, "plus")
            btn = QPushButton(f"  {label}")
            btn.setObjectName("NavButton")
            btn.setIcon(get_line_icon(icon_name, color=pal.text_secondary, size=18))
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self.navigate_to(k))
            nav_v.addWidget(btn)
            self._nav_buttons[key] = btn

        nav_v.addStretch()
        nav_scroll.setWidget(nav_container)
        s_lay.addWidget(nav_scroll, stretch=1)

        # Alternador de tema no rodapé da Sidebar
        self.btn_theme_toggle_side = QPushButton()
        self.btn_theme_toggle_side.setObjectName("GhostButton")
        self.btn_theme_toggle_side.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_toggle_side.clicked.connect(self.toggle_theme_mode)
        s_lay.addWidget(self.btn_theme_toggle_side)

        main_h.addWidget(self.sidebar_frame)

        # -------------------------------------------------------------
        # 2. Conteúdo à Direita: Header Superior + Stack de Views + Status
        # -------------------------------------------------------------
        content_v = QVBoxLayout()
        content_v.setContentsMargins(0, 0, 0, 0)
        content_v.setSpacing(0)

        # Barra Superior Fixa (DesktopHeader)
        self.header_frame = QFrame()
        self.header_frame.setObjectName("DesktopHeader")
        self.header_frame.setFixedHeight(54)
        h_lay = QHBoxLayout(self.header_frame)
        h_lay.setContentsMargins(16, 8, 20, 8)
        h_lay.setSpacing(10)

        # Campo de Busca Global (.srch)
        self.ed_global_search = QLineEdit()
        self.ed_global_search.setObjectName("SearchInput")
        self.ed_global_search.setPlaceholderText("Buscar no Plutos...")
        self.ed_global_search.addAction(
            get_line_icon("search", color=pal.text_secondary, size=16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.ed_global_search.setClearButtonEnabled(True)
        self.ed_global_search.setMinimumWidth(200)
        self.ed_global_search.setMaximumWidth(280)
        self.ed_global_search.textChanged.connect(lambda _: self.refresh_current_view())
        h_lay.addWidget(self.ed_global_search)

        h_lay.addStretch()

        # Seletor de Período Mensal Centralizado (< Novembro / 2026 >)
        self.period_pill = QFrame()
        self.period_pill.setObjectName("PeriodPill")
        p_lay = QHBoxLayout(self.period_pill)
        p_lay.setContentsMargins(4, 2, 4, 2)
        p_lay.setSpacing(2)

        self.btn_prev_month = QPushButton()
        self.btn_prev_month.setObjectName("IconPillButton")
        self.btn_prev_month.setFixedSize(28, 28)
        self.btn_prev_month.setIcon(get_line_icon("l", color=pal.text_secondary, size=14))
        self.btn_prev_month.setToolTip("Mês anterior")
        self.btn_prev_month.clicked.connect(self.go_previous_month)

        self.btn_period_label = QPushButton()
        self.btn_period_label.setObjectName("PeriodLabelButton")
        self.btn_period_label.setToolTip("Clique para retornar ao mês atual")
        self.btn_period_label.clicked.connect(self.go_current_month)

        self.btn_next_month = QPushButton()
        self.btn_next_month.setObjectName("IconPillButton")
        self.btn_next_month.setFixedSize(28, 28)
        self.btn_next_month.setIcon(get_line_icon("rt", color=pal.text_secondary, size=14))
        self.btn_next_month.setToolTip("Próximo mês")
        self.btn_next_month.clicked.connect(self.go_next_month)

        p_lay.addWidget(self.btn_prev_month)
        p_lay.addWidget(self.btn_period_label)
        p_lay.addWidget(self.btn_next_month)
        h_lay.addWidget(self.period_pill)

        h_lay.addStretch()

        # Ações do Topbar à Direita
        # 0. Assistente Gemini (lançamento rápido por IA), ao lado esquerdo de "+ Novo"
        self.btn_gemini = GeminiButton()
        self.btn_gemini.clicked.connect(self._quick_ai_entry)
        h_lay.addWidget(self.btn_gemini)

        # 1. Botão Primário "+ Novo"
        self.btn_fab_add = QPushButton("Novo")
        self.btn_fab_add.setObjectName("PrimaryButton")
        self.btn_fab_add.setIcon(get_line_icon("plus", color="#FFFFFF", size=16))
        self.btn_fab_add.setFixedHeight(34)
        self.btn_fab_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fab_add.setToolTip("Criação rápida de lançamentos e cadastros")
        self.btn_fab_add.clicked.connect(self._show_quick_add_menu)
        h_lay.addWidget(self.btn_fab_add)

        # 2. Seletor de Modo de Data de Referência (Discreto)
        self.cb_date_ref = QComboBox()
        self.cb_date_ref.setToolTip("Modo de Data de Referência")
        self.cb_date_ref.setFixedHeight(34)
        self.cb_date_ref.addItem("Ref: Vencimento", DateReferenceMode.VENCIMENTO.value)
        self.cb_date_ref.addItem("Ref: Lançamento", DateReferenceMode.LANCAMENTO.value)
        self.cb_date_ref.addItem(
            "Ref: Lançamento (Distribuir)",
            DateReferenceMode.LANCAMENTO_DISTRIBUIR.value,
        )
        self.cb_date_ref.addItem("Ref: Efetivação", DateReferenceMode.EFETIVACAO.value)
        idx_ref = self.cb_date_ref.findData(self.db.settings.date_reference_mode)
        if idx_ref >= 0:
            self.cb_date_ref.setCurrentIndex(idx_ref)
        self.cb_date_ref.currentIndexChanged.connect(self._on_date_ref_changed)
        h_lay.addWidget(self.cb_date_ref)

        # 3. Status da Base SQLite
        self.btn_db_status = QPushButton()
        self.btn_db_status.setObjectName("SecondaryButton")
        self.btn_db_status.setIcon(get_line_icon("db", color=pal.text_secondary, size=16))
        self.btn_db_status.setFixedHeight(34)
        self.btn_db_status.setToolTip("Clique para gerenciar o arquivo SQLite ou Backups")
        self.btn_db_status.clicked.connect(lambda: self.navigate_to("configuracoes"))
        h_lay.addWidget(self.btn_db_status)

        # 4. Botão de Atualização / Refresh (F5)
        self.btn_refresh = QPushButton()
        self.btn_refresh.setObjectName("IconButton")
        self.btn_refresh.setFixedSize(34, 34)
        self.btn_refresh.setIcon(get_line_icon("refresh", color=pal.text_secondary, size=16))
        self.btn_refresh.setToolTip("Recarregar dados e atualizar telas (F5)")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_current_view)
        h_lay.addWidget(self.btn_refresh)
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_current_view)
        for seq in ("Ctrl+K", "Ctrl+J"):
            QShortcut(QKeySequence(seq), self, activated=self._quick_ai_entry)

        # 5. Central de Notificações / Alertas
        self.btn_notifications = QPushButton()
        self.btn_notifications.setObjectName("IconButton")
        self.btn_notifications.setFixedSize(34, 34)
        self.btn_notifications.setIcon(get_line_icon("bell", color=pal.text_secondary, size=16))
        self.btn_notifications.setToolTip("Central de Notificações")
        self.btn_notifications.clicked.connect(self._show_notifications_menu)
        h_lay.addWidget(self.btn_notifications)

        # 6. Alternador de Tema Rápido
        self.btn_theme_toggle = QPushButton()
        self.btn_theme_toggle.setObjectName("IconButton")
        self.btn_theme_toggle.setFixedSize(34, 34)
        self.btn_theme_toggle.setToolTip("Alternar modo claro / escuro")
        self.btn_theme_toggle.clicked.connect(self.toggle_theme_mode)
        h_lay.addWidget(self.btn_theme_toggle)

        # 7. Seletor de Perfil Ativo
        self.cb_profile = QComboBox()
        self.cb_profile.setIconSize(QSize(18, 18))
        self.cb_profile.setFixedHeight(34)
        self.cb_profile.setMinimumWidth(125)
        self.cb_profile.currentIndexChanged.connect(self._on_profile_combo_changed)
        h_lay.addWidget(self.cb_profile)

        content_v.addWidget(self.header_frame)

        # Área de Visualização (Stacked Views)
        self.stack = QStackedWidget()
        content_v.addWidget(self.stack, stretch=1)

        # Barra de Status inferior
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        main_h.addLayout(content_v, stretch=1)
        self.setCentralWidget(central)

        self._init_views()
        self._update_theme_button_label()

    def _init_views(self) -> None:
        self.dashboard_view = DashboardView(
            self.db,
            get_context=self.get_active_context,
            navigate_to=self.navigate_to,
            parent=self,
        )
        self.contas_view = ContasView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.transacoes_view = TransacoesView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.cartoes_view = CartoesView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.orcamentos_view = OrcamentosView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.objetivos_view = ObjetivosView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.relatorios_view = RelatoriosView(
            self.db,
            get_context=self.get_active_context,
            parent=self,
        )
        self.graficos_view = GraficosView(
            self.db,
            get_context=self.get_active_context,
            parent=self,
        )
        self.categorias_view = CategoriasView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.tags_view = TagsView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.calendario_view = CalendarioView(
            self.db,
            get_context=self.get_active_context,
            parent=self,
        )
        self.ferramentas_view = FerramentasView(
            self.db,
            get_context=self.get_active_context,
            on_data_mutated=self._on_any_data_mutated,
            parent=self,
        )
        self.config_view = ConfiguracoesView(
            self.db,
            backup_service=self.backup_service,
            on_environment_changed=self._on_environment_changed,
            parent=self,
        )

        self._views["dashboard"] = self.dashboard_view
        self._views["contas"] = self.contas_view
        self._views["transacoes"] = self.transacoes_view
        self._views["cartoes"] = self.cartoes_view
        self._views["orcamentos"] = self.orcamentos_view
        self._views["objetivos"] = self.objetivos_view
        self._views["relatorios"] = self.relatorios_view
        self._views["graficos"] = self.graficos_view
        self._views["categorias"] = self.categorias_view
        self._views["tags"] = self.tags_view
        self._views["calendario"] = self.calendario_view
        self.config_hub_view = ConfiguracoesHubView(
            self.config_view, self.ferramentas_view, self.db, parent=self
        )
        self._views["configuracoes"] = self.config_hub_view

        for item in self.NAV_ITEMS:
            key, label = item[0], item[1]
            if key not in self._views:
                self._views[key] = self._build_stage_overview_widget(key, label)
            self.stack.addWidget(self._views[key])

    def _build_stage_overview_widget(self, key: str, label: str) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        card = QFrame()
        card.setObjectName("CardSurface")
        c_lay = QVBoxLayout(card)
        c_lay.setContentsMargins(24, 24, 24, 24)
        c_lay.setSpacing(10)

        lbl_t = QLabel(label)
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        lbl_t.setFont(f)
        c_lay.addWidget(lbl_t)

        lbl_desc = QLabel(
            "Os módulos base da Etapa 3 (<b>Contas Bancárias e Saldos Mensais</b>, "
            "<b>Categorias e Subcategorias</b>, <b>Tags</b>, <b>Perfis</b>, "
            "<b>Seletor de Base SQLite</b> e <b>Backup Online Automático 3h/6 arquivos</b>) "
            "já estão 100% operacionais no menu lateral.<br><br>"
            "Este módulo será detalhado nas próximas etapas do plano modular (Etapas 4, 5 e 6)."
        )
        lbl_desc.setWordWrap(True)
        c_lay.addWidget(lbl_desc)

        quick_row = QHBoxLayout()
        btn_go_contas = QPushButton("Ir para Contas Bancárias")
        btn_go_contas.setObjectName("PrimaryButton")
        btn_go_contas.clicked.connect(lambda: self.navigate_to("contas"))
        btn_go_cat = QPushButton("Ir para Categorias")
        btn_go_cat.setObjectName("SecondaryButton")
        btn_go_cat.clicked.connect(lambda: self.navigate_to("categorias"))
        btn_go_cfg = QPushButton("Gerenciar Banco SQLite & Backups")
        btn_go_cfg.setObjectName("SecondaryButton")
        btn_go_cfg.clicked.connect(lambda: self.navigate_to("configuracoes"))
        quick_row.addWidget(btn_go_contas)
        quick_row.addWidget(btn_go_cat)
        quick_row.addWidget(btn_go_cfg)
        quick_row.addStretch()
        c_lay.addLayout(quick_row)

        lay.addWidget(card)
        lay.addStretch()
        return page

    def navigate_to(self, key: str) -> None:
        if key == "ferramentas":  # atalho legado: agora é uma sub-aba de Configurações
            key = "configuracoes"
            self.config_hub_view.select_tab("ferramentas")
        if key not in self._views:
            return
        self.current_nav_key = key
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        for k, label in self.NAV_ITEMS:
            icon_name = self.NAV_ICONS.get(k, "plus")
            btn = self._nav_buttons.get(k)
            if not btn:
                continue
            is_active = (k == key)
            btn.setProperty("active", "true" if is_active else "false")
            icon_color = pal.primary if is_active else pal.text_secondary
            btn.setIcon(get_line_icon(icon_name, color=icon_color, size=18))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        target_widget = self._views[key]
        self.stack.setCurrentWidget(target_widget)
        self.refresh_current_view()

    def refresh_current_view(self) -> None:
        self._refresh_header_state()
        current = self.stack.currentWidget()
        if hasattr(current, "refresh_data"):
            current.refresh_data()
        self._update_status_bar()
        self._check_system_notifications()

    def _refresh_header_state(self) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        # Oculta seletor mensal em telas atemporais de cadastro global
        timeless_views = {"tags", "categorias", "configuracoes", "ferramentas"}
        self.period_pill.setVisible(self.current_nav_key not in timeless_views)

        self.btn_period_label.setText(
            format_month_year(self.current_month, self.current_year)
        )
        self.btn_prev_month.setIcon(get_line_icon("l", color=pal.text_secondary, size=14))
        self.btn_next_month.setIcon(get_line_icon("rt", color=pal.text_secondary, size=14))
        self.btn_refresh.setIcon(get_line_icon("refresh", color=pal.text_secondary, size=16))

        db_path = self.db.ensure_connected()
        self.btn_db_status.setText(f"  {db_path.name}")
        self.btn_db_status.setIcon(get_line_icon("db", color=pal.text_secondary, size=16))

        profiles = self.profile_repo.list_profiles(include_archived=False)
        active_prof = self.profile_repo.get_active_profile()
        self.active_profile_id = active_prof.id

        self.cb_profile.blockSignals(True)
        self.cb_profile.clear()
        for idx, p in enumerate(profiles):
            self.cb_profile.addItem(
                create_color_badge_icon(p.color_hex, p.name[:1], size=18),
                p.name,
                p.id,
            )
            if p.id == active_prof.id:
                self.cb_profile.setCurrentIndex(idx)
        self.cb_profile.blockSignals(False)
        self._update_status_bar()

    def _update_status_bar(self) -> None:
        db_path = self.db.ensure_connected()
        mut = self.db.get_mutation_counter()
        pending = (
            "Pendente de backup"
            if self.backup_service.has_pending_modifications()
            else "Backup em dia"
        )
        if getattr(self.db.settings, "show_technical_details", True):
            self.status_bar.showMessage(
                f"Base SQLite Ativa: {db_path}  |  Mutações Gravadas: {mut}  |  "
                f"Backup Online (3h / 6 arq.): {pending}"
            )
        else:
            self.status_bar.showMessage(
                f"Base: {db_path.name}  |  Status do Backup: {pending}"
            )

    def _on_any_data_mutated(self) -> None:
        self._refresh_header_state()
        self._check_system_notifications()

    def _on_environment_changed(self) -> None:
        self._refresh_header_state()
        self._check_system_notifications()
        self.refresh_current_view()

    def _on_profile_combo_changed(self, idx: int) -> None:
        if idx < 0:
            return
        prof_id = str(self.cb_profile.currentData())
        self.profile_repo.set_active_profile(prof_id)
        self.active_profile_id = prof_id
        self.refresh_current_view()

    def _on_date_ref_changed(self, idx: int) -> None:
        if idx < 0:
            return
        mode_val = str(self.cb_date_ref.currentData())
        self.db.settings.date_reference_mode = mode_val
        self.db.settings.save()
        self.refresh_current_view()

    def go_previous_month(self) -> None:
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._refresh_header_state()
        self.refresh_current_view()

    def go_next_month(self) -> None:
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._refresh_header_state()
        self.refresh_current_view()

    def go_current_month(self) -> None:
        today = date.today()
        self.current_month = today.month
        self.current_year = today.year
        self._refresh_header_state()
        self.refresh_current_view()

    def toggle_sidebar(self) -> None:
        collapsed = self.sidebar_frame.width() > 80
        self.sidebar_frame.setFixedWidth(56 if collapsed else 216)
        for key, label in self.NAV_ITEMS:
            btn = self._nav_buttons[key]
            btn.setText("" if collapsed else f"  {label}")
            btn.setToolTip(label if collapsed else "")
        self.lbl_logo_title.setVisible(not collapsed)
        self.btn_theme_toggle_side.setVisible(not collapsed)
        self.db.settings.sidebar_collapsed = collapsed
        self.db.settings.save()

    def toggle_theme_mode(self) -> None:
        new_mode = (
            "dark" if self.db.settings.theme_mode.lower() == "light" else "light"
        )
        self.db.settings.theme_mode = new_mode
        self.db.settings.save()
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_app_theme(app, new_mode)
        self._update_theme_button_label()
        self.navigate_to(self.current_nav_key)
        self.refresh_current_view()

    def _update_theme_button_label(self) -> None:
        is_dark = self.db.settings.theme_mode.lower() == "dark"
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        theme_icon = "sun" if is_dark else "moon"
        self.btn_theme_toggle.setIcon(get_line_icon(theme_icon, color=pal.text_secondary, size=16))
        self.btn_theme_toggle.setToolTip(
            "Alternar para Tema Claro" if is_dark else "Alternar para Tema Escuro"
        )
        self.btn_theme_toggle_side.setIcon(get_line_icon(theme_icon, color=pal.text_secondary, size=16))
        self.btn_theme_toggle_side.setText(
            "  Modo Claro" if is_dark else "  Modo Escuro"
        )

    def _show_quick_add_menu(self) -> None:
        menu = QMenu(self)
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        # Grupo 1: Lançamentos
        lbl_section1 = QWidgetAction(menu)
        hdr1 = QLabel("LANÇAMENTOS")
        hdr1.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: 600; padding: 6px 14px 2px 14px;"
        )
        lbl_section1.setDefaultWidget(hdr1)
        menu.addAction(lbl_section1)

        act_ai = QAction(get_line_icon("plus", color=pal.primary, size=16), "Lançamento rápido (IA)  Ctrl+K", self)
        act_ai.triggered.connect(self._quick_ai_entry)
        menu.addAction(act_ai)

        act_desp = QAction(get_line_icon("dn", color=pal.expense_red, size=16), "Despesa", self)
        act_desp.setShortcut(QKeySequence("D"))
        act_desp.triggered.connect(self._quick_new_expense)
        menu.addAction(act_desp)

        act_desp_cc = QAction(get_line_icon("card", color=pal.primary, size=16), "Despesa no cartão", self)
        act_desp_cc.setShortcut(QKeySequence("C"))
        act_desp_cc.triggered.connect(self._quick_new_card_expense)
        menu.addAction(act_desp_cc)

        act_rec = QAction(get_line_icon("up", color=pal.income_green, size=16), "Receita", self)
        act_rec.setShortcut(QKeySequence("R"))
        act_rec.triggered.connect(self._quick_new_income)
        menu.addAction(act_rec)

        act_transf = QAction(get_line_icon("swap", color=pal.transfer_indigo, size=16), "Transferência", self)
        act_transf.setShortcut(QKeySequence("T"))
        act_transf.triggered.connect(self._quick_new_transfer)
        menu.addAction(act_transf)

        menu.addSeparator()

        # Grupo 2: Cadastros
        lbl_section2 = QWidgetAction(menu)
        hdr2 = QLabel("CADASTROS")
        hdr2.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: 600; padding: 6px 14px 2px 14px;"
        )
        lbl_section2.setDefaultWidget(hdr2)
        menu.addAction(lbl_section2)

        act_conta = QAction(get_line_icon("bank", color=pal.text_secondary, size=16), "Conta ou carteira", self)
        act_conta.triggered.connect(self._quick_new_account)
        menu.addAction(act_conta)

        act_cartao = QAction(get_line_icon("card", color=pal.text_secondary, size=16), "Cartão de crédito", self)
        act_cartao.triggered.connect(self._quick_new_card)
        menu.addAction(act_cartao)

        act_cat = QAction(get_line_icon("folder", color=pal.text_secondary, size=16), "Categoria", self)
        act_cat.triggered.connect(lambda: self.navigate_to("categorias"))
        menu.addAction(act_cat)

        act_tag = QAction(get_line_icon("tag", color=pal.text_secondary, size=16), "Tag", self)
        act_tag.triggered.connect(lambda: self.navigate_to("tags"))
        menu.addAction(act_tag)

        # Regra de design: Backup NÃO fica nesse menu!

        menu.exec(self.btn_fab_add.mapToGlobal(self.btn_fab_add.rect().bottomLeft()))

    def _quick_ai_entry(self) -> None:
        """Abre o Lançamento Rápido por IA (Ctrl+K / Ctrl+J)."""
        from app.ui.dialogs.ai_quick_entry_dialog import AIQuickEntryDialog

        def _saved() -> None:
            self._on_any_data_mutated()
            self.refresh_current_view()

        dlg = AIQuickEntryDialog(self.db, self.active_profile_id, _saved, parent=self)
        dlg.manual_requested.connect(self._quick_new_expense)
        dlg.exec()

    def _quick_new_expense(self) -> None:
        self.navigate_to("transacoes")
        self.transacoes_view.open_new_expense_dialog(card_mode=False)

    def _quick_new_card_expense(self) -> None:
        self.navigate_to("transacoes")
        self.transacoes_view.open_new_expense_dialog(card_mode=True)

    def _quick_new_income(self) -> None:
        self.navigate_to("transacoes")
        self.transacoes_view.open_new_income_dialog()

    def _quick_new_transfer(self) -> None:
        self.navigate_to("transacoes")
        self.transacoes_view.open_new_transfer_dialog()

    def _quick_new_account(self) -> None:
        self.navigate_to("contas")
        self.contas_view.open_new_account_dialog()

    def _quick_new_card(self) -> None:
        self.navigate_to("cartoes")
        self.cartoes_view.open_new_card_dialog()

    def _on_backup_cycle_finished(self, result: BackupResult) -> None:
        self._update_status_bar()
        self._check_system_notifications()

    def _on_backup_advance_warning(self, seconds_left: float) -> None:
        self._check_system_notifications()

    def _check_system_notifications(self) -> None:
        today = date.today()
        tomorrow = date.fromordinal(today.toordinal() + 1)
        notifications: List[Tuple[str, str, str, str]] = []

        # 1. Alerta de Backup Automático Iminente (<= 5 minutos) ou Mutações Pendentes
        if self.backup_service.is_advance_warning_active():
            sec_left = self.backup_service.get_seconds_until_next_cycle() or 0
            m = int(sec_left / 60)
            s = int(sec_left % 60)
            notifications.append(
                (
                    "⚠️",
                    "Backup Automático Iminente (5 min)",
                    f"Ciclo automático de 3h iniciará em ~{m}m {s:02d}s.",
                    "configuracoes",
                )
            )
        elif self.backup_service.has_pending_modifications():
            mut_count = self.db.get_mutation_counter()
            notifications.append(
                (
                    "💾",
                    "Modificações Pendentes de Backup",
                    f"{mut_count} mutações registradas aguardando o próximo ciclo.",
                    "configuracoes",
                )
            )

        # 2. Contas a pagar e receber vencendo hoje ou amanhã
        try:
            occs = self.tx_service.list_occurrences(today.year, today.month)
            for o in occs:
                if not o.efetivada and o.ref_date in (today, tomorrow):
                    when = "hoje" if o.ref_date == today else "amanhã"
                    if o.is_expense:
                        notifications.append(
                            (
                                "💸",
                                f"Conta a Pagar ({when})",
                                f"{o.descricao}: {format_currency(o.total)}",
                                "transacoes",
                            )
                        )
                    elif o.is_income:
                        notifications.append(
                            (
                                "💰",
                                f"Receita Prevista ({when})",
                                f"{o.descricao}: {format_currency(o.total)}",
                                "transacoes",
                            )
                        )
        except Exception:
            pass

        # 3. Faturas de Cartão de Crédito fechando nos próximos 3 dias
        try:
            cards = self.card_service.list_cards(self.active_profile_id)
            for card in cards:
                closing_date = self.card_service.compute_closing_date(card, today.year, today.month)
                delta_days = (closing_date - today).days
                if 0 <= delta_days <= 3:
                    notifications.append(
                        (
                            "💳",
                            "Fatura de Cartão Fechando",
                            f"{card.nome} fecha em {delta_days} dia(s) ({format_date_br(closing_date.isoformat())}).",
                            "cartoes",
                        )
                    )
        except Exception:
            pass

        self._unread_notifications = notifications
        self._update_notification_badge()

    def _update_notification_badge(self) -> None:
        count = len(self._unread_notifications)
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        if count > 0:
            has_urgent = any("Backup Automático Iminente" in n[1] for n in self._unread_notifications)
            bell_color = pal.warning_orange if has_urgent else pal.primary
            self.btn_notifications.setIcon(get_line_icon("bell", color=bell_color, size=16))
            self.btn_notifications.setText(f" {count}")
            self.btn_notifications.setToolTip(f"{count} notificações ativas — clique para visualizar")
        else:
            self.btn_notifications.setIcon(get_line_icon("bell", color=pal.text_secondary, size=16))
            self.btn_notifications.setText("")
            self.btn_notifications.setToolTip("Nenhuma notificação pendente")

    def _show_notifications_menu(self) -> None:
        self._check_system_notifications()
        menu = QMenu(self)
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        lbl_section = QWidgetAction(menu)
        hdr = QLabel("NOTIFICAÇÕES")
        hdr.setStyleSheet(
            f"color: {pal.text_secondary}; font-size: 11px; font-weight: 600; padding: 6px 14px 2px 14px;"
        )
        lbl_section.setDefaultWidget(hdr)
        menu.addAction(lbl_section)

        if not self._unread_notifications:
            clean_act = QAction(get_line_icon("check", color=pal.income_green, size=16), "Tudo em dia! Nenhuma notificação.", self)
            clean_act.setEnabled(False)
            menu.addAction(clean_act)
        else:
            for _icon_glyph, title, details, target_nav in self._unread_notifications:
                act = QAction(get_line_icon("bell", color=pal.warning_orange, size=16), f"{title} — {details}", self)
                act.triggered.connect(lambda _, k=target_nav: self.navigate_to(k))
                menu.addAction(act)

        menu.addSeparator()
        backup_now_act = QAction(get_line_icon("db", color=pal.primary, size=16), "Fazer backup agora", self)
        backup_now_act.triggered.connect(self._run_manual_backup_from_notifications)
        menu.addAction(backup_now_act)

        if self.isVisible():
            menu.exec(self.btn_notifications.mapToGlobal(self.btn_notifications.rect().bottomLeft()))

    def _run_manual_backup_from_notifications(self) -> None:
        self.backup_service.run_backup_cycle(force=True)
        self._refresh_header_state()
        self._check_system_notifications()
