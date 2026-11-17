"""Tela Nativa de Orçamentos Mensais (`OrcamentosView`)."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import (
    EXPENSE_RED,
    INCOME_GREEN,
    PRIMARY_BLUE,
    ThemePalette,
    WARNING_ORANGE,
)
from app.database.connection_manager import ConnectionManager
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.tag_repository import TagRepository
from app.domain.services.budget_service import BudgetProgressDTO, BudgetService
from app.ui.bank_icons import create_color_badge_icon
from app.ui.components import (
    Badge,
    BudgetPaceProgressBar,
    EmptyStateWidget,
    KpiCard,
    SegmentedBar,
    compute_month_pace_pct,
)
from app.ui.icons import get_line_icon
from app.ui.style_manager import format_currency


class BudgetFormDialog(QDialog):
    """Modal para criar ou editar um Orçamento Mensal."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        budget: Optional[BudgetProgressDTO] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.budget = budget
        self.cat_repo = CategoryRepository(db)
        self.tag_repo = TagRepository(db)

        self.setWindowTitle(
            "Editar Orçamento" if budget else "Novo Orçamento Mensal"
        )
        self.setMinimumWidth(560)
        self._build_ui()
        if budget is not None:
            self._populate(budget)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        lbl_nat = QLabel("Natureza")
        lbl_nat.setObjectName("FormLabel")
        lbl_alvo = QLabel("Alvo do Orçamento")
        lbl_alvo.setObjectName("FormLabel")
        grid.addWidget(lbl_nat, 0, 0)
        grid.addWidget(lbl_alvo, 0, 1)

        self.cb_tipo = QComboBox()
        self.cb_tipo.addItem("Orçamento de Despesas", "D")
        self.cb_tipo.addItem("Meta de Receitas", "R")
        self.cb_tipo.currentIndexChanged.connect(self._reload_targets)
        grid.addWidget(self.cb_tipo, 1, 0)

        target_row = QHBoxLayout()
        target_row.setSpacing(14)
        self.rb_cat = QRadioButton("Por Categoria / Sub")
        self.rb_tag = QRadioButton("Por Tag")
        self.rb_cat.setChecked(True)
        self.rb_cat.toggled.connect(self._on_target_mode_changed)
        target_row.addWidget(self.rb_cat)
        target_row.addWidget(self.rb_tag)
        target_row.addStretch()
        grid.addLayout(target_row, 1, 1)

        lbl_cat = QLabel("Categoria")
        lbl_cat.setObjectName("FormLabel")
        lbl_sub = QLabel("Subcategoria")
        lbl_sub.setObjectName("FormLabel")
        grid.addWidget(lbl_cat, 2, 0)
        grid.addWidget(lbl_sub, 2, 1)

        self.cb_cat = QComboBox()
        self.cb_cat.currentIndexChanged.connect(self._on_cat_changed)
        self.cb_sub = QComboBox()
        grid.addWidget(self.cb_cat, 3, 0)
        grid.addWidget(self.cb_sub, 3, 1)

        lbl_tag = QLabel("Tag")
        lbl_tag.setObjectName("FormLabel")
        grid.addWidget(lbl_tag, 4, 0, 1, 2)

        self.cb_tag = QComboBox()
        for t in self.tag_repo.list_tags(self.profile_id):
            self.cb_tag.addItem(
                create_color_badge_icon(t.color_hex, "#", size=16),
                f"#{t.nome}",
                t.id,
            )
        grid.addWidget(self.cb_tag, 5, 0, 1, 2)

        lbl_meta = QLabel("Valor da Meta (R$) *")
        lbl_meta.setObjectName("FormLabel")
        lbl_alerta = QLabel("Alerta ao atingir")
        lbl_alerta.setObjectName("FormLabel")
        grid.addWidget(lbl_meta, 6, 0)
        grid.addWidget(lbl_alerta, 6, 1)

        self.sp_meta = QDoubleSpinBox()
        self.sp_meta.setRange(0.01, 999_999_999.99)
        self.sp_meta.setDecimals(2)
        self.sp_meta.setPrefix("R$ ")
        self.sp_meta.setValue(1000.00)

        self.sp_alerta = QDoubleSpinBox()
        self.sp_alerta.setRange(10.0, 100.0)
        self.sp_alerta.setDecimals(0)
        self.sp_alerta.setSuffix(" %")
        self.sp_alerta.setValue(80.0)
        grid.addWidget(self.sp_meta, 7, 0)
        grid.addWidget(self.sp_alerta, 7, 1)

        self.chk_resumo = QCheckBox("Exibir na Visão Geral (Dashboard)")
        self.chk_resumo.setChecked(True)
        grid.addWidget(self.chk_resumo, 8, 0, 1, 2)

        self.chk_month_only = QCheckBox("Aplicar novo valor de meta apenas neste mês")
        if self.budget is None:
            self.chk_month_only.setVisible(False)
        grid.addWidget(self.chk_month_only, 9, 0, 1, 2)

        layout.addLayout(grid)

        sep = QFrame()
        sep.setObjectName("ModalSeparator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_save = buttons.button(QDialogButtonBox.StandardButton.Save)
        btn_save.setText("Salvar Orçamento")
        btn_save.setObjectName("PrimaryButton")
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reload_targets()
        self._on_target_mode_changed()

    def _reload_targets(self) -> None:
        kind = "RECEITA" if self.cb_tipo.currentData() == "R" else "DESPESA"
        self._categories = self.cat_repo.list_categories(kind, self.profile_id)
        self.cb_cat.clear()
        for c in self._categories:
            self.cb_cat.addItem(
                create_color_badge_icon(c.color_hex, c.name[:1], size=18),
                c.name,
                c.id,
            )
        self._on_cat_changed()

    def _on_target_mode_changed(self) -> None:
        by_cat = self.rb_cat.isChecked()
        self.cb_cat.setEnabled(by_cat)
        self.cb_sub.setEnabled(by_cat)
        self.cb_tag.setEnabled(not by_cat)

    def _on_cat_changed(self) -> None:
        self.cb_sub.clear()
        self.cb_sub.addItem("Todas as subcategorias", None)
        cat_id = self.cb_cat.currentData()
        if not cat_id:
            return
        for c in self._categories:
            if c.id == str(cat_id):
                for s in c.subcategories:
                    self.cb_sub.addItem(s.name, s.id)
                break

    def _populate(self, b: BudgetProgressDTO) -> None:
        idx_t = self.cb_tipo.findData(b.tipo)
        if idx_t >= 0:
            self.cb_tipo.setCurrentIndex(idx_t)

        if b.id_tag:
            self.rb_tag.setChecked(True)
            idx = self.cb_tag.findData(b.id_tag)
            if idx >= 0:
                self.cb_tag.setCurrentIndex(idx)
        else:
            self.rb_cat.setChecked(True)
            if b.id_categoria:
                idx_c = self.cb_cat.findData(b.id_categoria)
                if idx_c >= 0:
                    self.cb_cat.setCurrentIndex(idx_c)
                    self._on_cat_changed()
                if b.id_subcategoria:
                    idx_s = self.cb_sub.findData(b.id_subcategoria)
                    if idx_s >= 0:
                        self.cb_sub.setCurrentIndex(idx_s)

        self.sp_meta.setValue(b.meta_mes)
        self.sp_alerta.setValue(b.perc_alerta)
        self.chk_resumo.setChecked(b.exibir_resumo)
        self._on_target_mode_changed()


class OrcamentosView(QWidget):
    """Tela de Orçamentos Mensais com barras de progresso e badges de status."""

    def __init__(
        self,
        db: ConnectionManager,
        get_context: Callable[[], Tuple[str, int, int, str]],
        on_data_mutated: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.get_context = get_context
        self.on_data_mutated = on_data_mutated
        self.budget_service = BudgetService(db)
        self._budgets: List[BudgetProgressDTO] = []
        self._nature_filter: str = "ALL"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        lbl_t = QLabel("Orçamentos mensais")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Acompanhamento de metas, ritmo esperado no mês e projeção de fechamento"
        )
        lbl_s.setObjectName("MutedText")
        title_col.addWidget(lbl_t)
        title_col.addWidget(lbl_s)
        header_row.addLayout(title_col)
        header_row.addStretch()

        self.btn_new = QPushButton("Novo orçamento")
        self.btn_new.setObjectName("PrimaryButton")
        self.btn_new.setIcon(get_line_icon("plus", color="#FFFFFF", size=16))
        self.btn_new.clicked.connect(self.open_new_budget_dialog)
        header_row.addWidget(self.btn_new)
        root.addLayout(header_row)

        # Barra segmentada (Todos | Despesas | Receitas) + Ritmo do mês
        seg_row = QHBoxLayout()
        self.seg_nature = SegmentedBar(
            [("ALL", "Todos"), ("D", "Despesas"), ("R", "Receitas")],
            active_key="ALL",
        )
        self.seg_nature.changed.connect(self._on_nature_changed)
        seg_row.addWidget(self.seg_nature)
        seg_row.addStretch()

        self.lbl_month_pace = QLabel("Dia 1 de 30 · 0% do mês")
        self.lbl_month_pace.setObjectName("MutedText")
        self.lbl_month_pace.setStyleSheet("font-size: 12px; font-weight: 600;")
        seg_row.addWidget(self.lbl_month_pace)

        self._view_mode = "cards"
        self.seg_view_mode = SegmentedBar(
            [("cards", "Cards"), ("table", "Tabela")],
            active_key="cards",
        )
        self.seg_view_mode.changed.connect(self.set_view_mode)
        seg_row.addWidget(self.seg_view_mode)
        root.addLayout(seg_row)

        # KPIs com tint semântico e micro-ícones
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.k1, self.lbl_k1, self.lbl_k1_sub = self._make_kpi(
            "Total Orçado (Despesas)", PRIMARY_BLUE, icon_name="target", tint="info"
        )
        self.k2, self.lbl_k2, self.lbl_k2_sub = self._make_kpi(
            "Utilizado no Mês", EXPENSE_RED, icon_name="arrow-down", tint="negative"
        )
        self.k3, self.lbl_k3, self.lbl_k3_sub = self._make_kpi(
            "Saldo Disponível", INCOME_GREEN, icon_name="wallet", tint="positive"
        )
        self.k4, self.lbl_k4, self.lbl_k4_sub = self._make_kpi(
            "Alertas / Estourados", WARNING_ORANGE, icon_name="chart-bar", tint="warning"
        )
        kpi_row.addWidget(self.k1, 1)
        kpi_row.addWidget(self.k2, 1)
        kpi_row.addWidget(self.k3, 1)
        kpi_row.addWidget(self.k4, 1)
        root.addLayout(kpi_row)

        # Card Progresso Geral do Orçamento
        self.overall_card = QFrame()
        self.overall_card.setObjectName("CardSurface")
        ov_lay = QVBoxLayout(self.overall_card)
        ov_lay.setContentsMargins(18, 12, 18, 12)
        ov_lay.setSpacing(6)
        ov_top = QHBoxLayout()
        lbl_ov_t = QLabel("Progresso geral do orçamento")
        lbl_ov_t.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.lbl_overall_pct = QLabel("0%")
        self.lbl_overall_pct.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {INCOME_GREEN};")
        ov_top.addWidget(lbl_ov_t)
        ov_top.addStretch()
        ov_top.addWidget(self.lbl_overall_pct)
        ov_lay.addLayout(ov_top)
        self.overall_pace_bar = BudgetPaceProgressBar(show_caption=False)
        ov_lay.addWidget(self.overall_pace_bar)
        root.addWidget(self.overall_card)

        # Stack Tabela / Empty State
        self.stack = QStackedWidget()

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Alvo",
                "Tipo",
                "Meta",
                "Efetivado",
                "Pendente",
                "Restante",
                "Ritmo",
                "Projeção",
                "Situação",
            ]
        )
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(8, 125)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _: self.edit_selected_budget())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.cards_host = QWidget()
        self.cards_host.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 2, 4, 4)
        self.cards_layout.setSpacing(10)
        self.cards_scroll.setWidget(self.cards_host)
        self.stack.addWidget(self.cards_scroll)

        self.stack.addWidget(self.table)

        self.empty_widget = EmptyStateWidget(
            title="Nenhum orçamento cadastrado",
            subtitle="Defina metas de gastos por categoria ou tag para manter suas despesas sob controle.",
            icon_name="chart-bar",
            action_text="+ Novo Orçamento",
            action_callback=self.open_new_budget_dialog,
        )
        self.stack.addWidget(self.empty_widget)

        root.addWidget(self.stack, stretch=1)

        # Barra inferior de ações discretas
        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        self.btn_edit = QPushButton("Editar meta")
        self.btn_edit.setObjectName("SecondaryButton")
        self.btn_edit.setIcon(get_line_icon("edit", size=15))
        self.btn_edit.clicked.connect(self.edit_selected_budget)
        self.btn_edit.setEnabled(False)

        self.btn_del = QPushButton("Excluir orçamento")
        self.btn_del.setObjectName("SecondaryButton")
        self.btn_del.setIcon(get_line_icon("trash", size=15))
        self.btn_del.clicked.connect(self.delete_selected_budget)
        self.btn_del.setEnabled(False)

        act_row.addWidget(self.btn_edit)
        act_row.addWidget(self.btn_del)
        act_row.addStretch()
        root.addLayout(act_row)

    def _on_nature_changed(self, key: str) -> None:
        self._nature_filter = key if key in ("ALL", "D", "R") else "ALL"
        self.refresh_data()

    def _make_kpi(
        self,
        title: str,
        accent_hex: str,
        *,
        icon_name: Optional[str] = None,
        tint: Optional[str] = None,
    ) -> Tuple[KpiCard, QLabel, QLabel]:
        card = KpiCard(
            title=title.upper(),
            value="R$ 0,00",
            variant="neutral",
            subtitle="",
            icon_name=icon_name,
            accent_color=accent_hex,
            tint=tint,
        )
        card.lbl_value.setStyleSheet(f"color: {accent_hex}; font-size: 22px; font-weight: 700;")
        card.lbl_subtitle.setStyleSheet("font-size: 11px;")
        return card, card.lbl_value, card.lbl_subtitle

    def _on_selection_changed(self) -> None:
        has_sel = self.table.currentRow() >= 0 and len(self._budgets) > 0
        self.btn_edit.setEnabled(has_sel)
        self.btn_del.setEnabled(has_sel)

    def _on_context_menu(self, pos) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._budgets)):
            return
        menu = QMenu(self)
        act_edit = menu.addAction(get_line_icon("edit", size=16), "Editar orçamento")
        act_del = menu.addAction(get_line_icon("trash", size=16), "Excluir orçamento")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == act_edit:
            self.edit_selected_budget()
        elif chosen == act_del:
            self.delete_selected_budget()

    def keyPressEvent(self, event) -> None:
        if self.table.hasFocus():
            if event.key() == Qt.Key.Key_Delete:
                self.delete_selected_budget()
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.edit_selected_budget()
                event.accept()
                return
        super().keyPressEvent(event)

    def refresh_data(self) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        profile_id, month, year, search_text = self.get_context()
        elapsed_days, days_in_month, expected_pct = compute_month_pace_pct(year, month)
        self.lbl_month_pace.setText(
            f"Dia {elapsed_days} de {days_in_month} · {expected_pct:.0f}% do mês"
        )

        all_b = self.budget_service.list_budgets_progress(
            year,
            month,
            profile_id=profile_id,
            mode=self.db.settings.date_reference_mode,
        )
        if self._nature_filter in ("D", "R"):
            all_b = [b for b in all_b if b.tipo == self._nature_filter]
        if search_text.strip():
            q = search_text.strip().lower()
            all_b = [b for b in all_b if q in b.nome_alvo.lower()]
        self._budgets = all_b

        desp_b = [b for b in self._budgets if b.tipo == "D"]
        tot_meta = sum(b.meta_mes for b in desp_b)
        tot_used = sum(b.utilizado for b in desp_b)
        tot_rem = tot_meta - tot_used
        alerts = sum(1 for b in self._budgets if b.status_label != "Dentro da Meta")

        self.lbl_k1.setText(format_currency(tot_meta))
        self.lbl_k1_sub.setText(f"{len(desp_b)} orçamentos de despesas")
        self.lbl_k2.setText(format_currency(tot_used))
        pct_tot = (tot_used / tot_meta * 100.0) if tot_meta > 0 else 0.0
        self.lbl_k2_sub.setText(f"{pct_tot:.1f}% da meta total")
        self.lbl_k3.setText(format_currency(tot_rem))
        self.lbl_k3_sub.setText("Margem disponível no mês")
        self.lbl_k4.setText(str(alerts))
        self.lbl_k4_sub.setText("Orçamentos em alerta ou estourados")

        self.overall_card.setVisible(bool(desp_b and tot_meta > 0))
        if desp_b and tot_meta > 0:
            ov_color = (
                EXPENSE_RED
                if pct_tot > 100.0
                else (WARNING_ORANGE if pct_tot >= 80.0 else INCOME_GREEN)
            )
            self.lbl_overall_pct.setText(f"{pct_tot:.0f}%")
            self.lbl_overall_pct.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {ov_color};")
            self.overall_pace_bar.set_values(pct_tot, expected_pct, ov_color)

        if not self._budgets:
            self.table.setRowCount(0)
            while self.cards_layout.count():
                it = self.cards_layout.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            self.stack.setCurrentWidget(self.empty_widget)
            self._on_selection_changed()
            return

        self.stack.setCurrentWidget(
            self.cards_scroll if self._view_mode == "cards" else self.table
        )
        self.table.setRowCount(0)
        while self.cards_layout.count():
            it = self.cards_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        f_bold = QFont()
        f_bold.setBold(True)

        for idx, b in enumerate(self._budgets):
            self.table.insertRow(idx)
            it_name = QTableWidgetItem(
                create_color_badge_icon(b.cor_hex, b.nome_alvo[:1], size=18),
                b.nome_alvo,
            )
            self.table.setItem(idx, 0, it_name)

            it_tipo = QTableWidgetItem("Despesa" if b.tipo == "D" else "Receita")
            it_tipo.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_tipo.setForeground(QColor("#7B8190"))
            self.table.setItem(idx, 1, it_tipo)

            for col_i, val in (
                (2, b.meta_mes),
                (3, b.efetivado),
                (4, b.pendente),
                (5, b.restante),
            ):
                it = QTableWidgetItem(format_currency(val))
                it.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                if col_i == 3:
                    it.setFont(f_bold)
                self.table.setItem(idx, col_i, it)

            # 6: Barra de ritmo com marcador vertical de ritmo esperado (QPainter)
            bar_color = (
                EXPENSE_RED
                if b.percentual > 100.0
                else (WARNING_ORANGE if b.percentual >= b.perc_alerta else INCOME_GREEN)
            )
            pace_wrap = QWidget()
            pace_lay = QHBoxLayout(pace_wrap)
            pace_lay.setContentsMargins(6, 2, 6, 2)
            pace_bar = BudgetPaceProgressBar(
                percentual=b.percentual,
                expected_pct=expected_pct,
                bar_color=bar_color,
                show_caption=True,
            )
            pace_lay.addWidget(pace_bar)
            self.table.setCellWidget(idx, 6, pace_wrap)

            # 7: Projeção de fechamento pelo ritmo diário
            proj_val = (
                round(b.utilizado / (expected_pct / 100.0), 2)
                if expected_pct > 0.0 and expected_pct < 100.0
                else b.utilizado
            )
            it_proj = QTableWidgetItem(format_currency(proj_val))
            it_proj.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            if b.tipo == "D" and proj_val > b.meta_mes:
                it_proj.setForeground(QColor(EXPENSE_RED))
            self.table.setItem(idx, 7, it_proj)

            # 8: Situação em Badge pill (Em dia / Atenção / Estourou)
            if b.status_label == "Dentro da Meta":
                ui_status, variant = "Em dia", "success"
            elif b.status_label == "Estourado":
                ui_status, variant = "Estourou", "danger"
            else:
                ui_status, variant = "Atenção", "warning"
            badge = Badge(ui_status, variant=variant)
            b_wrap = QWidget()
            b_lay = QHBoxLayout(b_wrap)
            b_lay.setContentsMargins(0, 0, 0, 0)
            b_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_lay.addWidget(badge)
            self.table.setCellWidget(idx, 8, b_wrap)

            # Seta item com cor 100% transparente para ordenação/busca textual sem fantasma visual
            it_st = QTableWidgetItem(ui_status)
            it_st.setForeground(QColor(0, 0, 0, 0))
            it_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 8, it_st)

            # Card correspondente na visão em Cards
            b_card = QFrame()
            b_card.setObjectName("CardSurface")
            bc_lay = QVBoxLayout(b_card)
            bc_lay.setContentsMargins(16, 12, 16, 12)
            bc_lay.setSpacing(8)

            bc_top = QHBoxLayout()
            bc_top.setSpacing(10)
            ico_b = QLabel()
            ico_b.setPixmap(create_color_badge_icon(b.cor_hex, b.nome_alvo[:1], size=20).pixmap(20, 20))
            bc_top.addWidget(ico_b)

            lbl_bn = QLabel(b.nome_alvo)
            lbl_bn.setStyleSheet("font-size: 14px; font-weight: 700;")
            bc_top.addWidget(lbl_bn)

            lbl_bt = QLabel("Despesa" if b.tipo == "D" else "Receita")
            lbl_bt.setObjectName("MutedText")
            lbl_bt.setStyleSheet("font-size: 11px;")
            bc_top.addWidget(lbl_bt)
            bc_top.addStretch()

            lbl_bvals = QLabel(
                f"Efetivado: <b>{format_currency(b.efetivado)}</b>  ·  Meta: {format_currency(b.meta_mes)}  ·  "
                f"Restante: {format_currency(b.restante)}  ·  Projeção: {format_currency(proj_val)}"
            )
            lbl_bvals.setStyleSheet("font-size: 12px;")
            bc_top.addWidget(lbl_bvals)
            bc_top.addSpacing(8)
            bc_top.addWidget(Badge(ui_status, variant=variant))
            bc_lay.addLayout(bc_top)

            card_pace = BudgetPaceProgressBar(
                percentual=b.percentual,
                expected_pct=expected_pct,
                bar_color=bar_color,
                show_caption=True,
            )
            bc_lay.addWidget(card_pace)

            def _on_card_click(_ev, row_i=idx) -> None:
                self.table.selectRow(row_i)
                self._on_selection_changed()

            def _on_card_dbl(_ev, row_i=idx) -> None:
                self.table.selectRow(row_i)
                self.edit_selected_budget()

            b_card.mousePressEvent = _on_card_click  # type: ignore[method-assign]
            b_card.mouseDoubleClickEvent = _on_card_dbl  # type: ignore[method-assign]
            self.cards_layout.addWidget(b_card)

        self.cards_layout.addStretch()
        self._on_selection_changed()

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = "table" if mode == "table" else "cards"
        if hasattr(self, "seg_view_mode"):
            self.seg_view_mode.set_active(self._view_mode, emit=False)
        if not self._budgets:
            self.stack.setCurrentWidget(self.empty_widget)
        elif self._view_mode == "table":
            self.stack.setCurrentWidget(self.table)
        else:
            self.stack.setCurrentWidget(self.cards_scroll)

    def open_new_budget_dialog(self) -> None:
        profile_id, _, _, _ = self.get_context()
        dlg = BudgetFormDialog(self.db, profile_id=profile_id, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        by_cat = dlg.rb_cat.isChecked()
        id_cat = str(dlg.cb_cat.currentData()) if (by_cat and dlg.cb_cat.currentData()) else None
        id_sub = str(dlg.cb_sub.currentData()) if (by_cat and dlg.cb_sub.currentData()) else None
        id_tag = str(dlg.cb_tag.currentData()) if ((not by_cat) and dlg.cb_tag.currentData()) else None
        if not id_cat and not id_tag:
            QMessageBox.warning(
                self, "Alvo inválido", "Selecione uma categoria ou tag válida."
            )
            return
        self.budget_service.create_budget(
            meta=float(dlg.sp_meta.value()),
            id_categoria=id_cat,
            id_subcategoria=id_sub,
            id_tag=id_tag,
            tipo=str(dlg.cb_tipo.currentData() or "D"),
            perc_alerta=float(dlg.sp_alerta.value()),
            somar_sub=(id_sub is None),
            exibir_resumo=dlg.chk_resumo.isChecked(),
            profile_id=profile_id,
        )
        self.on_data_mutated()
        self.refresh_data()

    def edit_selected_budget(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._budgets)):
            return
        b = self._budgets[row]
        profile_id, month, year, _ = self.get_context()
        dlg = BudgetFormDialog(
            self.db, profile_id=profile_id, budget=b, parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.budget_service.update_budget(
            b.id,
            meta=float(dlg.sp_meta.value()),
            perc_alerta=float(dlg.sp_alerta.value()),
            exibir_resumo=dlg.chk_resumo.isChecked(),
            year=year,
            month=month,
            override_month_only=dlg.chk_month_only.isChecked(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def delete_selected_budget(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._budgets)):
            return
        b = self._budgets[row]
        ans = QMessageBox.question(
            self,
            "Excluir Orçamento",
            f"Deseja excluir o orçamento de '{b.nome_alvo}'?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.budget_service.delete_budget(b.id)
        self.on_data_mutated()
        self.refresh_data()
