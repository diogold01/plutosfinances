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
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
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
from app.ui.components import Badge, EmptyStateWidget
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
        self.setMinimumWidth(480)
        self._build_ui()
        if budget is not None:
            self._populate(budget)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.cb_tipo = QComboBox()
        self.cb_tipo.addItem("Orçamento de Despesas", "D")
        self.cb_tipo.addItem("Meta de Receitas", "R")
        self.cb_tipo.currentIndexChanged.connect(self._reload_targets)
        form.addRow("Natureza:", self.cb_tipo)

        target_row = QHBoxLayout()
        self.rb_cat = QRadioButton("Por Categoria / Sub")
        self.rb_tag = QRadioButton("Por Tag")
        self.rb_cat.setChecked(True)
        self.rb_cat.toggled.connect(self._on_target_mode_changed)
        target_row.addWidget(self.rb_cat)
        target_row.addWidget(self.rb_tag)
        target_row.addStretch()
        form.addRow("Alvo:", target_row)

        self.cb_cat = QComboBox()
        self.cb_cat.currentIndexChanged.connect(self._on_cat_changed)
        form.addRow("Categoria:", self.cb_cat)

        self.cb_sub = QComboBox()
        form.addRow("Subcategoria:", self.cb_sub)

        self.cb_tag = QComboBox()
        for t in self.tag_repo.list_tags(self.profile_id):
            self.cb_tag.addItem(
                create_color_badge_icon(t.color_hex, "#", size=16),
                f"#{t.nome}",
                t.id,
            )
        form.addRow("Tag:", self.cb_tag)

        self.sp_meta = QDoubleSpinBox()
        self.sp_meta.setRange(0.01, 999_999_999.99)
        self.sp_meta.setDecimals(2)
        self.sp_meta.setPrefix("R$ ")
        self.sp_meta.setValue(1000.00)
        form.addRow("Valor da Meta (R$)*:", self.sp_meta)

        self.sp_alerta = QDoubleSpinBox()
        self.sp_alerta.setRange(10.0, 100.0)
        self.sp_alerta.setDecimals(0)
        self.sp_alerta.setSuffix(" %")
        self.sp_alerta.setValue(80.0)
        form.addRow("Alerta ao atingir:", self.sp_alerta)

        self.chk_resumo = QCheckBox("Exibir na Visão Geral (Dashboard)")
        self.chk_resumo.setChecked(True)
        form.addRow("", self.chk_resumo)

        self.chk_month_only = QCheckBox("Aplicar novo valor de meta apenas neste mês")
        if self.budget is None:
            self.chk_month_only.setVisible(False)
        form.addRow("", self.chk_month_only)

        layout.addLayout(form)
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
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        lbl_t = QLabel("Orçamentos mensais")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Acompanhamento de metas de gastos e receitas por categoria, subcategoria ou tag"
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

        # KPIs
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.k1, self.lbl_k1, self.lbl_k1_sub = self._make_kpi(
            "Total Orçado (Despesas)", PRIMARY_BLUE
        )
        self.k2, self.lbl_k2, self.lbl_k2_sub = self._make_kpi(
            "Utilizado no Mês", EXPENSE_RED
        )
        self.k3, self.lbl_k3, self.lbl_k3_sub = self._make_kpi(
            "Saldo Disponível", INCOME_GREEN
        )
        self.k4, self.lbl_k4, self.lbl_k4_sub = self._make_kpi(
            "Alertas / Estourados", WARNING_ORANGE
        )
        kpi_row.addWidget(self.k1, 1)
        kpi_row.addWidget(self.k2, 1)
        kpi_row.addWidget(self.k3, 1)
        kpi_row.addWidget(self.k4, 1)
        root.addLayout(kpi_row)

        # Stack Tabela / Empty State
        self.stack = QStackedWidget()

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Alvo",
                "Tipo",
                "Meta",
                "Efetivado",
                "Pendente",
                "Restante",
                "Progresso",
                "Situação",
            ]
        )
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(7, 135)
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

    def _make_kpi(
        self, title: str, accent_hex: str
    ) -> Tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("KpiCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        lbl_t = QLabel(title.upper())
        lbl_t.setObjectName("MutedText")
        lbl_t.setStyleSheet("font-size: 11px; font-weight: 600; letter-spacing: 0.5px;")
        lbl_v = QLabel("R$ 0,00")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        lbl_v.setFont(f)
        lbl_v.setStyleSheet(f"color: {accent_hex};")
        lbl_s = QLabel("")
        lbl_s.setObjectName("MutedText")
        lbl_s.setStyleSheet("font-size: 11px;")
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        lay.addWidget(lbl_s)
        return card, lbl_v, lbl_s

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
        all_b = self.budget_service.list_budgets_progress(
            year,
            month,
            profile_id=profile_id,
            mode=self.db.settings.date_reference_mode,
        )
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

        if not self._budgets:
            self.table.setRowCount(0)
            self.stack.setCurrentWidget(self.empty_widget)
            self._on_selection_changed()
            return

        self.stack.setCurrentWidget(self.table)
        self.table.setRowCount(0)

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

            # Barra de progresso padronizada de 8px em pílula (Redesign Plutos)
            prog_container = QWidget()
            prog_lay = QHBoxLayout(prog_container)
            prog_lay.setContentsMargins(6, 4, 6, 4)
            prog_lay.setSpacing(8)

            bar = QProgressBar()
            bar.setRange(0, 100)
            val_pct = min(100, int(round(b.percentual)))
            bar.setValue(val_pct)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar_color = (
                EXPENSE_RED
                if b.percentual > 100.0
                else (WARNING_ORANGE if b.percentual >= b.perc_alerta else INCOME_GREEN)
            )
            bar.setStyleSheet(
                f"QProgressBar {{ background-color: rgba(123, 129, 144, 0.15); border: none; border-radius: 99px; }}"
                f"QProgressBar::chunk {{ background-color: {bar_color}; border-radius: 99px; }}"
            )
            lbl_pct = QLabel(f"{b.percentual:.1f}%")
            lbl_pct.setFixedWidth(46)
            lbl_pct.setStyleSheet(f"color: {pal.text_secondary}; font-size: 11px; font-weight: 600;")
            prog_lay.addWidget(bar, 1)
            prog_lay.addWidget(lbl_pct)
            self.table.setCellWidget(idx, 6, prog_container)

            # Situação em Badge pill
            variant = (
                "success"
                if b.status_label == "Dentro da Meta"
                else ("danger" if b.status_label == "Estourado" else "warning")
            )
            badge = Badge(b.status_label, variant=variant)
            b_wrap = QWidget()
            b_lay = QHBoxLayout(b_wrap)
            b_lay.setContentsMargins(0, 0, 0, 0)
            b_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_lay.addWidget(badge)
            self.table.setCellWidget(idx, 7, b_wrap)

            # Seta item com cor 100% transparente para ordenação/busca textual sem fantasma visual
            it_st = QTableWidgetItem(b.status_label)
            it_st.setForeground(QColor(0, 0, 0, 0))
            it_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 7, it_st)

        self._on_selection_changed()

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
