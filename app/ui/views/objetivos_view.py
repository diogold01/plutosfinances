"""Tela Nativa de Objetivos / Metas Financeiras (`ObjetivosView`)."""

from __future__ import annotations

from datetime import date
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import (
    CATEGORY_SWATCHES,
    EXPENSE_RED,
    INCOME_GREEN,
    PRIMARY_BLUE,
    ThemePalette,
)
from app.database.connection_manager import ConnectionManager
from app.domain.services.goal_service import GoalDTO, GoalService
from app.ui.bank_icons import create_color_badge_icon
from app.ui.components import Badge, EmptyStateWidget, KpiCard
from app.ui.icons import get_line_icon
from app.ui.style_manager import format_currency, format_date_br


class GoalFormDialog(QDialog):
    """Modal moderno para criar ou editar um Objetivo / Meta Financeira."""

    def __init__(
        self,
        goal: Optional[GoalDTO] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.goal = goal
        self.setWindowTitle(
            "Editar Objetivo Financeiro" if goal else "Novo Objetivo"
        )
        self.setMinimumWidth(460)
        self._build_ui()
        if goal is not None:
            self._populate(goal)

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        # Cabeçalho
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_title = QLabel("Editar Objetivo" if self.goal else "Novo Objetivo")
        lbl_title.setObjectName("SectionTitle")
        lbl_sub = QLabel("Defina uma meta de valor e prazo para acompanhar seus aportes.")
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        lay.addLayout(title_box)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("Ex.: Reserva de Emergência, Viagem, Carro...")
        form.addRow("Descrição:", self.ed_desc)

        self.sp_meta = QDoubleSpinBox()
        self.sp_meta.setRange(0.01, 999_999_999.99)
        self.sp_meta.setDecimals(2)
        self.sp_meta.setPrefix("R$ ")
        self.sp_meta.setValue(10000.00)
        form.addRow("Valor Alvo:", self.sp_meta)

        self.sp_inicial = QDoubleSpinBox()
        self.sp_inicial.setRange(0.0, 999_999_999.99)
        self.sp_inicial.setDecimals(2)
        self.sp_inicial.setPrefix("R$ ")
        self.sp_inicial.setValue(0.0)
        form.addRow("Saldo Inicial:", self.sp_inicial)

        target_dt = date(date.today().year + 1, date.today().month, 1)
        self.dt_expec = QDateEdit(QDate(target_dt.year, target_dt.month, target_dt.day))
        self.dt_expec.setCalendarPopup(True)
        self.dt_expec.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Expectativa:", self.dt_expec)

        self.ed_motivacao = QLineEdit()
        self.ed_motivacao.setPlaceholderText("Ex.: Segurança financeira de 6 meses")
        form.addRow("Motivação:", self.ed_motivacao)

        self.cb_cor = QComboBox()
        for hex_code in CATEGORY_SWATCHES:
            self.cb_cor.addItem(
                create_color_badge_icon(hex_code, "", size=16), hex_code, hex_code
            )
        form.addRow("Cor de Destaque:", self.cb_cor)

        self.chk_realizado = QCheckBox("Marcar objetivo como concluído")
        if self.goal is None:
            self.chk_realizado.setVisible(False)
        form.addRow("", self.chk_realizado)

        lay.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_save = bb.button(QDialogButtonBox.StandardButton.Save)
        btn_save.setText("Salvar Objetivo")
        btn_save.setObjectName("PrimaryButton")
        btn_cancel = bb.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")

        bb.accepted.connect(self._validate_and_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _populate(self, g: GoalDTO) -> None:
        self.ed_desc.setText(g.descricao)
        self.sp_meta.setValue(g.meta)
        self.sp_inicial.setValue(g.saldo_inicial)
        if g.data_expectativa:
            d = g.data_expectativa
            self.dt_expec.setDate(QDate(d.year, d.month, d.day))
        self.ed_motivacao.setText(g.motivacao)
        idx_c = self.cb_cor.findData(g.color_hex)
        if idx_c >= 0:
            self.cb_cor.setCurrentIndex(idx_c)
        self.chk_realizado.setChecked(g.realizado)

    def _validate_and_accept(self) -> None:
        if not self.ed_desc.text().strip():
            QMessageBox.warning(self, "Campo obrigatório", "Informe a descrição do objetivo.")
            return
        self.accept()


class DepositDialog(QDialog):
    """Modal para registrar Aporte ou Retirada em um Objetivo."""

    def __init__(self, goal: GoalDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.goal = goal
        self.setWindowTitle(f"Aporte — {goal.descricao}")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_title = QLabel(f"Registrar Aporte: {self.goal.descricao}")
        lbl_title.setObjectName("SectionTitle")
        lbl_sub = QLabel("Valores positivos aumentam o acumulado; negativos representam resgates.")
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        lay.addLayout(title_box)

        form = QFormLayout()
        form.setSpacing(12)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(-999_999_999.99, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(
            self.goal.aporte_mensal_sugerido if self.goal.aporte_mensal_sugerido > 0 else 500.00
        )
        form.addRow("Valor do Aporte:", self.sp_valor)

        today = date.today()
        self.dt_dep = QDateEdit(QDate(today.year, today.month, today.day))
        self.dt_dep.setCalendarPopup(True)
        self.dt_dep.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Data:", self.dt_dep)

        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Ex.: Depósito mensal, 13º salário, etc.")
        form.addRow("Observação:", self.ed_obs)

        lay.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("Confirmar Aporte")
        btn_ok.setObjectName("PrimaryButton")
        btn_cancel = bb.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")

        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class ObjetivosView(QWidget):
    """Tela nativa de Objetivos (Metas Financeiras) e Histórico de Depósitos."""

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
        self.goal_service = GoalService(db)
        self._goals: List[GoalDTO] = []
        self._selected_goal: Optional[GoalDTO] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Cabeçalho da tela
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        lbl_t = QLabel("Objetivos")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Planejamento de metas de médio e longo prazo com acompanhamento de depósitos"
        )
        lbl_s.setObjectName("MutedText")
        title_col.addWidget(lbl_t)
        title_col.addWidget(lbl_s)
        header_row.addLayout(title_col)
        header_row.addStretch()

        self.btn_new = QPushButton("+ Novo Objetivo")
        self.btn_new.setObjectName("PrimaryButton")
        self.btn_new.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        self.btn_new.clicked.connect(self.open_new_goal_dialog)
        header_row.addWidget(self.btn_new)
        root.addLayout(header_row)

        # KPIs do Topo
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(16)
        self.kpi_meta = KpiCard(
            title="Total das Metas",
            value="R$ 0,00",
            subtitle="0 objetivos cadastrados",
            icon_name="target",
            accent_color=PRIMARY_BLUE,
        )
        self.kpi_acum = KpiCard(
            title="Total Acumulado",
            value="R$ 0,00",
            subtitle="Saldos iniciais e aportes",
            icon_name="trending_up",
            accent_color=INCOME_GREEN,
        )
        self.kpi_rest = KpiCard(
            title="Valor Restante",
            value="R$ 0,00",
            subtitle="Falta acumular para a meta",
            icon_name="pie_chart",
            accent_color=EXPENSE_RED,
        )
        kpi_row.addWidget(self.kpi_meta, 1)
        kpi_row.addWidget(self.kpi_acum, 1)
        kpi_row.addWidget(self.kpi_rest, 1)
        root.addLayout(kpi_row)

        # Stack central para alternar entre Tabela e Empty State
        self.stack = QStackedWidget()

        # Splitter principal: Lista de objetivos à esquerda | Histórico de depósitos à direita
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # Card Esquerdo: Lista de Objetivos
        left_card = QFrame()
        left_card.setObjectName("CardSurface")
        l_lay = QVBoxLayout(left_card)
        l_lay.setContentsMargins(16, 16, 16, 16)
        l_lay.setSpacing(12)

        l_head = QHBoxLayout()
        lbl_card_title = QLabel("Metas em Acompanhamento")
        f_title = QFont()
        f_title.setBold(True)
        f_title.setPointSize(10)
        lbl_card_title.setFont(f_title)
        l_head.addWidget(lbl_card_title)
        l_head.addStretch()
        l_lay.addLayout(l_head)

        self.tbl_goals = QTableWidget(0, 5)
        self.tbl_goals.setHorizontalHeaderLabels(
            ["Objetivo", "Meta", "Acumulado", "Progresso", "Expectativa"]
        )
        self.tbl_goals.setShowGrid(False)
        self.tbl_goals.verticalHeader().setVisible(False)
        self.tbl_goals.verticalHeader().setDefaultSectionSize(40)
        ghdr = self.tbl_goals.horizontalHeader()
        ghdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ghdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ghdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        ghdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        ghdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_goals.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_goals.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tbl_goals.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_goals.itemSelectionChanged.connect(self._on_goal_selected)
        l_lay.addWidget(self.tbl_goals, stretch=1)

        # Ações discretas para o objetivo selecionado
        l_btns = QHBoxLayout()
        l_btns.setSpacing(8)
        self.btn_edit = QPushButton("Editar")
        self.btn_edit.setObjectName("SecondaryButton")
        self.btn_edit.setIcon(get_line_icon("pencil", size=14))
        self.btn_edit.clicked.connect(self.edit_selected_goal)

        self.btn_del = QPushButton("Excluir")
        self.btn_del.setObjectName("SecondaryButton")
        self.btn_del.setIcon(get_line_icon("trash", size=14))
        self.btn_del.clicked.connect(self.delete_selected_goal)

        l_btns.addWidget(self.btn_edit)
        l_btns.addWidget(self.btn_del)
        l_btns.addStretch()
        l_lay.addLayout(l_btns)

        self.splitter.addWidget(left_card)

        # Card Direito: Detalhes do Objetivo e Aportes
        right_card = QFrame()
        right_card.setObjectName("CardSurface")
        r_lay = QVBoxLayout(right_card)
        r_lay.setContentsMargins(16, 16, 16, 16)
        r_lay.setSpacing(12)

        r_head = QHBoxLayout()
        r_title_col = QVBoxLayout()
        r_title_col.setSpacing(2)
        self.lbl_detail_title = QLabel("Selecione um objetivo")
        self.lbl_detail_title.setFont(f_title)
        self.lbl_detail_sub = QLabel("")
        self.lbl_detail_sub.setObjectName("MutedText")
        r_title_col.addWidget(self.lbl_detail_title)
        r_title_col.addWidget(self.lbl_detail_sub)
        r_head.addLayout(r_title_col)
        r_head.addStretch()

        self.btn_add_dep = QPushButton("+ Aporte")
        self.btn_add_dep.setObjectName("SecondaryButton")
        self.btn_add_dep.setIcon(get_line_icon("plus", size=14))
        self.btn_add_dep.clicked.connect(self.open_add_deposit_dialog)
        r_head.addWidget(self.btn_add_dep)
        r_lay.addLayout(r_head)

        self.tbl_deps = QTableWidget(0, 3)
        self.tbl_deps.setHorizontalHeaderLabels(
            ["Data", "Observação", "Valor"]
        )
        self.tbl_deps.setShowGrid(False)
        self.tbl_deps.verticalHeader().setVisible(False)
        self.tbl_deps.verticalHeader().setDefaultSectionSize(36)
        dhdr = self.tbl_deps.horizontalHeader()
        dhdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        dhdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        dhdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_deps.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        r_lay.addWidget(self.tbl_deps, stretch=1)

        self.splitter.addWidget(right_card)
        self.splitter.setSizes([580, 440])

        self.stack.addWidget(self.splitter)

        # Estado Vazio
        self.empty_widget = EmptyStateWidget(
            title="Nenhum objetivo cadastrado",
            subtitle="Defina sua primeira meta financeira para acompanhar prazos e depósitos.",
            action_label="+ Novo Objetivo",
            on_action=self.open_new_goal_dialog,
            icon_name="target",
        )
        self.stack.addWidget(self.empty_widget)

        root.addWidget(self.stack, stretch=1)

    def refresh_data(self) -> None:
        profile_id, _, _, search_text = self.get_context()
        goals = self.goal_service.list_goals(profile_id=profile_id)
        if search_text.strip():
            q = search_text.strip().lower()
            goals = [
                g
                for g in goals
                if q in g.descricao.lower() or q in g.motivacao.lower()
            ]
        self._goals = goals

        tot_meta = sum(g.meta for g in goals)
        tot_acum = sum(g.saldo_acumulado for g in goals)
        tot_rest = sum(g.restante for g in goals)

        self.kpi_meta.set_value(format_currency(tot_meta))
        self.kpi_meta.set_subtitle(f"{len(goals)} objetivo(s) cadastrado(s)")

        self.kpi_acum.set_value(format_currency(tot_acum))
        self.kpi_acum.set_subtitle("Saldos iniciais e aportes")

        self.kpi_rest.set_value(format_currency(tot_rest))
        self.kpi_rest.set_subtitle("Restante para concluir as metas")

        if not goals:
            self.tbl_goals.setRowCount(0)
            self.stack.setCurrentWidget(self.empty_widget)
            self._show_goal(None)
            self.btn_edit.setEnabled(False)
            self.btn_del.setEnabled(False)
            return

        self.stack.setCurrentWidget(self.splitter)
        self.btn_edit.setEnabled(True)
        self.btn_del.setEnabled(True)

        self.tbl_goals.blockSignals(True)
        self.tbl_goals.setRowCount(0)
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        for idx, g in enumerate(goals):
            self.tbl_goals.insertRow(idx)

            # 0: Objetivo com badge de cor e status
            it_name = QTableWidgetItem(
                create_color_badge_icon(g.color_hex, "", size=14), g.descricao
            )
            f_b = QFont()
            f_b.setBold(True)
            it_name.setFont(f_b)
            self.tbl_goals.setItem(idx, 0, it_name)

            # 1: Meta
            it_m = QTableWidgetItem(format_currency(g.meta))
            it_m.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.tbl_goals.setItem(idx, 1, it_m)

            # 2: Acumulado
            it_a = QTableWidgetItem(format_currency(g.saldo_acumulado))
            it_a.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_a.setForeground(QColor(INCOME_GREEN))
            self.tbl_goals.setItem(idx, 2, it_a)

            # 3: Progresso com barra de 6px elegante
            prog_container = QWidget()
            prog_lay = QHBoxLayout(prog_container)
            prog_lay.setContentsMargins(6, 4, 6, 4)
            prog_lay.setSpacing(8)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(min(100, round(g.percentual))))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setStyleSheet(
                f"QProgressBar {{ background-color: rgba(123, 129, 144, 0.15); border: none; border-radius: 99px; }}"
                f"QProgressBar::chunk {{ background-color: {g.color_hex}; border-radius: 99px; }}"
            )

            lbl_pct = QLabel(f"{g.percentual:.0f}%")
            lbl_pct.setFixedWidth(40)
            lbl_pct.setStyleSheet(f"color: {pal.text_secondary}; font-size: 11px;")
            lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            prog_lay.addWidget(bar, 1)
            prog_lay.addWidget(lbl_pct)
            self.tbl_goals.setCellWidget(idx, 3, prog_container)

            # 4: Expectativa
            exp_txt = (
                format_date_br(g.data_expectativa.isoformat())
                if g.data_expectativa
                else "—"
            )
            it_e = QTableWidgetItem(exp_txt)
            it_e.setForeground(QColor(pal.text_secondary))
            it_e.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tbl_goals.setItem(idx, 4, it_e)

        self.tbl_goals.blockSignals(False)

        # Seleção
        sel_row = 0
        if self._selected_goal is not None:
            for i, g in enumerate(goals):
                if g.id == self._selected_goal.id:
                    sel_row = i
                    break
        self.tbl_goals.selectRow(sel_row)
        self._show_goal(goals[sel_row])

    def _on_goal_selected(self) -> None:
        row = self.tbl_goals.currentRow()
        if 0 <= row < len(self._goals):
            self._show_goal(self._goals[row])

    def _show_goal(self, g: Optional[GoalDTO]) -> None:
        self._selected_goal = g
        self.tbl_deps.setRowCount(0)
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        if g is None:
            self.lbl_detail_title.setText("Nenhum objetivo selecionado")
            self.lbl_detail_sub.setText("")
            self.btn_add_dep.setEnabled(False)
            return

        self.btn_add_dep.setEnabled(True)
        status_txt = " · Concluído" if g.realizado else ""
        self.lbl_detail_title.setText(f"{g.descricao} ({g.percentual:.0f}%{status_txt})")
        self.lbl_detail_sub.setText(
            f"Inicial: {format_currency(g.saldo_inicial)} · "
            f"Aportes: {format_currency(g.total_aportes)} · "
            f"Sugestão: {format_currency(g.aporte_mensal_sugerido)}/mês"
        )

        for idx, d in enumerate(g.deposits):
            self.tbl_deps.insertRow(idx)
            it_dt = QTableWidgetItem(format_date_br(d.data.isoformat()))
            it_dt.setForeground(QColor(pal.text_secondary))
            self.tbl_deps.setItem(idx, 0, it_dt)

            self.tbl_deps.setItem(idx, 1, QTableWidgetItem(d.obs or "Aporte"))

            it_v = QTableWidgetItem(format_currency(d.valor))
            it_v.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_v.setForeground(
                QColor(INCOME_GREEN if d.valor >= 0 else EXPENSE_RED)
            )
            self.tbl_deps.setItem(idx, 2, it_v)

    def open_new_goal_dialog(self) -> None:
        profile_id, _, _, _ = self.get_context()
        dlg = GoalFormDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        qd = dlg.dt_expec.date()
        self.goal_service.create_goal(
            descricao=dlg.ed_desc.text().strip(),
            meta=float(dlg.sp_meta.value()),
            saldo_inicial=float(dlg.sp_inicial.value()),
            data_expectativa=date(qd.year(), qd.month(), qd.day()),
            motivacao=dlg.ed_motivacao.text().strip(),
            color_hex=str(dlg.cb_cor.currentData() or "#E5603D"),
            profile_id=profile_id,
        )
        self.on_data_mutated()
        self.refresh_data()

    def edit_selected_goal(self) -> None:
        if self._selected_goal is None:
            return
        g = self._selected_goal
        dlg = GoalFormDialog(goal=g, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        qd = dlg.dt_expec.date()
        self.goal_service.update_goal(
            g.id,
            descricao=dlg.ed_desc.text().strip(),
            meta=float(dlg.sp_meta.value()),
            saldo_inicial=float(dlg.sp_inicial.value()),
            data_expectativa=date(qd.year(), qd.month(), qd.day()),
            motivacao=dlg.ed_motivacao.text().strip(),
            color_hex=str(dlg.cb_cor.currentData() or "#E5603D"),
            realizado=dlg.chk_realizado.isChecked(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def delete_selected_goal(self) -> None:
        if self._selected_goal is None:
            return
        g = self._selected_goal
        ans = QMessageBox.question(
            self,
            "Excluir Objetivo",
            f"Deseja excluir o objetivo '{g.descricao}' e todo o seu histórico de depósitos?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.goal_service.delete_goal(g.id)
        self.on_data_mutated()
        self.refresh_data()

    def open_add_deposit_dialog(self) -> None:
        if self._selected_goal is None:
            return
        dlg = DepositDialog(self._selected_goal, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        qd = dlg.dt_dep.date()
        self.goal_service.add_deposit(
            self._selected_goal.id,
            valor=float(dlg.sp_valor.value()),
            data_deposito=date(qd.year(), qd.month(), qd.day()),
            obs=dlg.ed_obs.text().strip(),
        )
        self.on_data_mutated()
        self.refresh_data()
