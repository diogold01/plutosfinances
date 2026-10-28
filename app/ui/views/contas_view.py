"""Tela de Contas Bancárias e Saldos Mensais (`ContasView`)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
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
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
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
)
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import (
    AccountBalanceSummaryDTO,
    AccountRepository,
)
from app.database.repositories.category_repository import CategoryRepository
from app.ui.bank_icons import (
    create_color_badge_icon,
    get_bank_icon,
    list_available_bank_icons,
)
from app.ui.components import EmptyStateWidget
from app.ui.icons import get_line_icon
from app.ui.style_manager import format_currency, format_month_year


class AccountFormDialog(QDialog):
    """Modal para criação e edição de Conta Bancária com seletor dos 160 ícones de bancos."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        mes: int,
        ano: int,
        existing: Optional[AccountBalanceSummaryDTO] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.mes = mes
        self.ano = ano
        self.existing = existing
        self.cat_repo = CategoryRepository(db)
        self.account_repo = AccountRepository(db)
        self.selected_image_key = (
            existing.image_key if existing else "ic_nubank.png"
        )

        self.setWindowTitle(
            "Editar Conta" if existing else "Nova Conta Bancária / Carteira"
        )
        self.setMinimumSize(560, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.ed_descricao = QLineEdit()
        self.ed_descricao.setPlaceholderText("Ex.: Nubank, Itaú Conta Corrente, Carteira...")
        if self.existing:
            self.ed_descricao.setText(self.existing.descricao)
        form.addRow("Descrição da Conta*:", self.ed_descricao)

        self.cb_categoria = QComboBox()
        self._categories = self.cat_repo.list_account_categories(self.profile_id)
        for cat in self._categories:
            self.cb_categoria.addItem(
                create_color_badge_icon(cat.color_hex, size=18),
                cat.nome,
                cat.id,
            )
        if self.existing:
            idx = self.cb_categoria.findData(self.existing.id_categoria)
            if idx >= 0:
                self.cb_categoria.setCurrentIndex(idx)
        form.addRow("Categoria da Conta:", self.cb_categoria)

        self.sp_saldo_inicial = QDoubleSpinBox()
        self.sp_saldo_inicial.setRange(-999_999_999.99, 999_999_999.99)
        self.sp_saldo_inicial.setDecimals(2)
        self.sp_saldo_inicial.setPrefix("R$ ")
        if self.existing:
            self.sp_saldo_inicial.setValue(self.existing.saldo_inicial)
        form.addRow(
            f"Saldo Inicial ({format_month_year(self.mes, self.ano)}):",
            self.sp_saldo_inicial,
        )

        self.sp_cheque_especial = QDoubleSpinBox()
        self.sp_cheque_especial.setRange(0.0, 999_999_999.99)
        self.sp_cheque_especial.setDecimals(2)
        self.sp_cheque_especial.setPrefix("R$ ")
        if self.existing:
            self.sp_cheque_especial.setValue(self.existing.cheque_especial)
        form.addRow("Limite Cheque Especial:", self.sp_cheque_especial)

        flags_row = QHBoxLayout()
        self.chk_resumo = QCheckBox("Exibir no Resumo")
        self.chk_resumo.setChecked(
            (self.existing.exibir_resumo == "S") if self.existing else True
        )
        self.chk_somar = QCheckBox("Somar no Saldo Total")
        self.chk_somar.setChecked(
            (self.existing.somar_total == "S") if self.existing else True
        )
        self.chk_padrao = QCheckBox("Conta Padrão")
        self.chk_padrao.setChecked(
            (self.existing.padrao == "S") if self.existing else False
        )
        self.chk_fav = QCheckBox("Favorita ★")
        self.chk_fav.setChecked(
            bool(self.existing.fav) if self.existing else False
        )
        flags_row.addWidget(self.chk_resumo)
        flags_row.addWidget(self.chk_somar)
        flags_row.addWidget(self.chk_padrao)
        flags_row.addWidget(self.chk_fav)
        form.addRow("Opções:", flags_row)

        root.addLayout(form)

        # Seletor de Ícone de Instituição Bancária
        bank_lbl = QLabel("Instituição Bancária:")
        bank_lbl.setStyleSheet("font-weight: 600;")
        root.addWidget(bank_lbl)

        self.ed_search_bank = QLineEdit()
        self.ed_search_bank.setPlaceholderText("Filtrar banco (ex.: Nubank, Itaú, Inter, XP, Caixa)...")
        self.ed_search_bank.textChanged.connect(self._filter_banks)
        root.addWidget(self.ed_search_bank)

        self.list_banks = QListWidget()
        self.list_banks.setIconSize(QSize(28, 28))
        self.list_banks.setMinimumHeight(180)
        self._all_banks = list_available_bank_icons()
        for fname, label, _ in self._all_banks:
            item = QListWidgetItem(get_bank_icon(fname, 28), f"{label}")
            item.setData(Qt.ItemDataRole.UserRole, fname)
            self.list_banks.addItem(item)
            if fname == self.selected_image_key:
                self.list_banks.setCurrentItem(item)
        self.list_banks.currentItemChanged.connect(self._on_bank_selected)
        root.addWidget(self.list_banks)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_save = buttons.button(QDialogButtonBox.StandardButton.Save)
        btn_save.setText("Salvar Conta")
        btn_save.setObjectName("PrimaryButton")
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _filter_banks(self, text: str) -> None:
        query = text.strip().lower()
        for i in range(self.list_banks.count()):
            it = self.list_banks.item(i)
            it.setHidden(bool(query and query not in it.text().lower()))

    def _on_bank_selected(
        self, current: Optional[QListWidgetItem], _prev: Optional[QListWidgetItem]
    ) -> None:
        if current is not None:
            self.selected_image_key = str(current.data(Qt.ItemDataRole.UserRole))

    def _on_save(self) -> None:
        desc = self.ed_descricao.text().strip()
        if not desc:
            QMessageBox.warning(
                self, "Campo Obrigatório", "Informe a descrição da conta."
            )
            return

        cat_id = str(self.cb_categoria.currentData() or "3")
        cat_text = self.cb_categoria.currentText().lower()
        is_inv = "S" if "invest" in cat_text else "N"

        if self.existing is None:
            self.account_repo.create_account(
                descricao=desc,
                id_categoria=cat_id,
                saldo_inicial=self.sp_saldo_inicial.value(),
                cheque_especial=self.sp_cheque_especial.value(),
                exibir_resumo="S" if self.chk_resumo.isChecked() else "N",
                somar_total="S" if self.chk_somar.isChecked() else "N",
                padrao="S" if self.chk_padrao.isChecked() else "N",
                investimento=is_inv,
                fav=1 if self.chk_fav.isChecked() else 0,
                image_key=self.selected_image_key,
                profile_id=self.profile_id,
                mes_inicial=self.mes,
                ano_inicial=self.ano,
            )
        else:
            self.account_repo.update_account(
                account_id=self.existing.id,
                descricao=desc,
                id_categoria=cat_id,
                cheque_especial=self.sp_cheque_especial.value(),
                exibir_resumo="S" if self.chk_resumo.isChecked() else "N",
                somar_total="S" if self.chk_somar.isChecked() else "N",
                padrao="S" if self.chk_padrao.isChecked() else "N",
                investimento=is_inv,
                fav=1 if self.chk_fav.isChecked() else 0,
                image_key=self.selected_image_key,
                profile_id=self.profile_id,
            )
            self.account_repo.set_monthly_opening_balance(
                account_id=self.existing.id,
                mes=self.mes,
                ano=self.ano,
                saldo_inicial=self.sp_saldo_inicial.value(),
                cheque_especial=self.sp_cheque_especial.value(),
            )
        self.accept()


class BalanceReconcileDialog(QDialog):
    """Modal para ajustar o Saldo Inicial do mês ou Reconciliar o Saldo Atual Confirmado."""

    def __init__(
        self,
        account_repo: AccountRepository,
        summary: AccountBalanceSummaryDTO,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.account_repo = account_repo
        self.summary = summary
        self.setWindowTitle(f"Reconciliação de Saldo — {summary.descricao}")
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        info = QLabel(
            f"<b>Conta:</b> {self.summary.descricao}<br>"
            f"<b>Período:</b> {format_month_year(self.summary.mes, self.summary.ano)}<br>"
            f"<b>Saldo Inicial:</b> {format_currency(self.summary.saldo_inicial)}<br>"
            f"<b>Saldo Confirmado:</b> {format_currency(self.summary.saldo_atual)}"
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("Reconciliar Saldo Confirmado Final do Mês", "reconcile")
        self.cb_mode.addItem("Definir Saldo Inicial do Mês (SI)", "opening")
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Modo de Ajuste:", self.cb_mode)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(-999_999_999.99, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(self.summary.saldo_atual)
        form.addRow("Novo Valor:", self.sp_valor)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("Confirmar Ajuste")
        btn_ok.setObjectName("PrimaryButton")
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_mode_changed(self) -> None:
        if self.cb_mode.currentData() == "reconcile":
            self.sp_valor.setValue(self.summary.saldo_atual)
        else:
            self.sp_valor.setValue(self.summary.saldo_inicial)

    def _on_apply(self) -> None:
        val = self.sp_valor.value()
        if self.cb_mode.currentData() == "reconcile":
            self.account_repo.reconcile_account_balance(
                self.summary.id, self.summary.mes, self.summary.ano, val
            )
        else:
            self.account_repo.set_monthly_opening_balance(
                self.summary.id, self.summary.mes, self.summary.ano, val
            )
        self.accept()


class ContasView(QWidget):
    """Vista de Contas Bancárias, Saldos Mensais e Reconciliação."""

    def __init__(
        self,
        db: ConnectionManager,
        get_context: Callable[[], tuple[str, int, int, str]],
        on_data_mutated: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.get_context = get_context
        self.on_data_mutated = on_data_mutated
        self.account_repo = AccountRepository(db)
        self._summaries: list[AccountBalanceSummaryDTO] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Barra de título + Ações
        top_bar = QHBoxLayout()
        title_box = QVBoxLayout()
        self.lbl_title = QLabel("Contas bancárias")
        self.lbl_title.setObjectName("SectionTitle")
        self.lbl_subtitle = QLabel(
            "Contas correntes, carteiras, investimentos e saldos mensais"
        )
        self.lbl_subtitle.setObjectName("MutedText")
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        top_bar.addLayout(title_box)
        top_bar.addStretch()

        # Botão Primário Único
        self.btn_new = QPushButton("Nova conta")
        self.btn_new.setObjectName("PrimaryButton")
        self.btn_new.setIcon(get_line_icon("plus", color="#FFFFFF", size=16))
        self.btn_new.clicked.connect(self.open_new_account_dialog)

        # Ações Secundárias Discretas
        self.btn_reconcile = QPushButton("Ajustar saldo")
        self.btn_reconcile.setObjectName("SecondaryButton")
        self.btn_reconcile.setIcon(get_line_icon("refresh", size=16))
        self.btn_reconcile.clicked.connect(self._on_reconcile_selected)
        self.btn_reconcile.setEnabled(False)

        self.btn_edit = QPushButton("Editar")
        self.btn_edit.setObjectName("SecondaryButton")
        self.btn_edit.setIcon(get_line_icon("edit", size=16))
        self.btn_edit.clicked.connect(self._on_edit_selected)
        self.btn_edit.setEnabled(False)

        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.setObjectName("SecondaryButton")
        self.btn_delete.setIcon(get_line_icon("trash", size=16))
        self.btn_delete.clicked.connect(self._on_delete_selected)
        self.btn_delete.setEnabled(False)

        top_bar.addWidget(self.btn_new)
        top_bar.addWidget(self.btn_reconcile)
        top_bar.addWidget(self.btn_edit)
        top_bar.addWidget(self.btn_delete)
        root.addLayout(top_bar)

        # 4 Cards KPI de Resumo
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self.card_atual, self.lbl_val_atual = self._create_kpi_card(
            "Saldo Confirmado", "R$ 0,00", INCOME_GREEN
        )
        self.card_previsto, self.lbl_val_previsto = self._create_kpi_card(
            "Saldo Previsto", "R$ 0,00", PRIMARY_BLUE
        )
        self.card_invest, self.lbl_val_invest = self._create_kpi_card(
            "Total Investimentos", "R$ 0,00", PRIMARY_BLUE
        )
        self.card_cheque, self.lbl_val_cheque = self._create_kpi_card(
            "Cheque Especial Disp.", "R$ 0,00", "#7B8190"
        )
        cards_row.addWidget(self.card_atual)
        cards_row.addWidget(self.card_previsto)
        cards_row.addWidget(self.card_invest)
        cards_row.addWidget(self.card_cheque)
        root.addLayout(cards_row)

        # Tabela em Stack com Empty State
        self.stack = QStackedWidget()

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Conta",
                "Categoria",
                "Saldo Inicial",
                "Entradas",
                "Saídas",
                "Saldo Atual",
                "Saldo Previsto",
                "Cheque Especial",
            ]
        )
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setIconSize(QSize(26, 26))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(lambda _: self._on_edit_selected())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 8):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.stack.addWidget(self.table)

        self.empty_widget = EmptyStateWidget(
            title="Nenhuma conta cadastrada",
            subtitle="Adicione suas contas bancárias, contas de pagamento ou carteiras para acompanhar seus saldos.",
            icon_name="bank",
            action_text="+ Nova Conta",
            action_callback=self.open_new_account_dialog,
        )
        self.stack.addWidget(self.empty_widget)

        root.addWidget(self.stack, stretch=1)

    def _create_kpi_card(
        self, title: str, initial_val: str, accent_hex: str
    ) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("KpiCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(4)
        lbl_t = QLabel(title.upper())
        lbl_t.setObjectName("MutedText")
        lbl_t.setStyleSheet("font-size: 11px; font-weight: 600; letter-spacing: 0.5px;")
        lbl_v = QLabel(initial_val)
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        lbl_v.setFont(f)
        lbl_v.setStyleSheet(f"color: {accent_hex};")
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        return card, lbl_v

    def _on_selection_changed(self) -> None:
        has_sel = self.table.currentRow() >= 0 and len(self._summaries) > 0
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)
        self.btn_reconcile.setEnabled(has_sel)

    def _on_context_menu(self, pos) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._summaries)):
            return
        menu = QMenu(self)
        act_edit = menu.addAction(get_line_icon("edit", size=16), "Editar conta")
        act_rec = menu.addAction(get_line_icon("refresh", size=16), "Ajustar saldo")
        menu.addSeparator()
        act_del = menu.addAction(get_line_icon("trash", size=16), "Excluir conta")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == act_edit:
            self._on_edit_selected()
        elif chosen == act_rec:
            self._on_reconcile_selected()
        elif chosen == act_del:
            self._on_delete_selected()

    def keyPressEvent(self, event) -> None:
        if self.table.hasFocus():
            if event.key() == Qt.Key.Key_Delete:
                self._on_delete_selected()
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._on_edit_selected()
                event.accept()
                return
        super().keyPressEvent(event)

    def refresh_data(self) -> None:
        profile_id, mes, ano, search = self.get_context()
        self._summaries = self.account_repo.list_accounts_with_balances(
            profile_id=profile_id, mes=mes, ano=ano
        )

        if search:
            q = search.lower()
            self._summaries = [
                s
                for s in self._summaries
                if q in s.descricao.lower() or q in s.categoria_nome.lower()
            ]

        if not self._summaries:
            self.table.setRowCount(0)
            self.stack.setCurrentWidget(self.empty_widget)
            self._on_selection_changed()
            return

        self.stack.setCurrentWidget(self.table)
        self.table.setRowCount(0)

        tot_atual = 0.0
        tot_previsto = 0.0
        tot_invest = 0.0
        tot_cheque = 0.0

        f_bold = QFont()
        f_bold.setBold(True)

        for row, s in enumerate(self._summaries):
            self.table.insertRow(row)

            if s.somar_total == "S":
                tot_atual += s.saldo_atual
                tot_previsto += s.saldo_previsto
                tot_cheque += s.cheque_especial

            if s.investimento == "S":
                tot_invest += s.saldo_atual

            # 0: Conta com logo do banco
            it_desc = QTableWidgetItem(
                get_bank_icon(s.image_key, size=24), s.descricao
            )
            self.table.setItem(row, 0, it_desc)

            # 1: Categoria
            it_cat = QTableWidgetItem(s.categoria_nome)
            it_cat.setForeground(QColor("#7B8190"))
            self.table.setItem(row, 1, it_cat)

            # 2: Saldo Inicial
            it_si = QTableWidgetItem(format_currency(s.saldo_inicial, s.currency))
            it_si.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 2, it_si)

            # 3: Entradas
            entradas = s.receitas_efetivadas + s.transf_credito_efet
            it_ent = QTableWidgetItem(format_currency(entradas, s.currency))
            it_ent.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_ent.setForeground(QColor(INCOME_GREEN))
            self.table.setItem(row, 3, it_ent)

            # 4: Saídas
            saidas = s.despesas_pagas + s.transf_debito_efet
            it_sai = QTableWidgetItem(format_currency(saidas, s.currency))
            it_sai.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_sai.setForeground(QColor(EXPENSE_RED))
            self.table.setItem(row, 4, it_sai)

            # 5: Saldo Atual
            it_cur = QTableWidgetItem(format_currency(s.saldo_atual, s.currency))
            it_cur.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_cur.setFont(f_bold)
            it_cur.setForeground(
                QColor(INCOME_GREEN if s.saldo_atual >= 0 else EXPENSE_RED)
            )
            self.table.setItem(row, 5, it_cur)

            # 6: Saldo Previsto
            it_prev = QTableWidgetItem(format_currency(s.saldo_previsto, s.currency))
            it_prev.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_prev.setFont(f_bold)
            it_prev.setForeground(
                QColor(INCOME_GREEN if s.saldo_previsto >= 0 else EXPENSE_RED)
            )
            self.table.setItem(row, 6, it_prev)

            # 7: Cheque Especial
            it_chq = QTableWidgetItem(format_currency(s.cheque_especial, s.currency))
            it_chq.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_chq.setForeground(QColor("#7B8190"))
            self.table.setItem(row, 7, it_chq)

        self.lbl_val_atual.setText(format_currency(tot_atual))
        self.lbl_val_previsto.setText(format_currency(tot_previsto))
        self.lbl_val_invest.setText(format_currency(tot_invest))
        self.lbl_val_cheque.setText(format_currency(tot_atual + tot_cheque))
        self._on_selection_changed()

    def open_new_account_dialog(self) -> None:
        profile_id, mes, ano, _ = self.get_context()
        dlg = AccountFormDialog(
            self.db, profile_id, mes, ano, existing=None, parent=self
        )
        if dlg.exec():
            if self.on_data_mutated:
                self.on_data_mutated()
            self.refresh_data()

    def _on_edit_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._summaries)):
            return
        summary = self._summaries[row]
        profile_id, mes, ano, _ = self.get_context()
        dlg = AccountFormDialog(
            self.db, profile_id, mes, ano, existing=summary, parent=self
        )
        if dlg.exec():
            if self.on_data_mutated:
                self.on_data_mutated()
            self.refresh_data()

    def _on_delete_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._summaries)):
            return
        summary = self._summaries[row]
        ans = QMessageBox.question(
            self,
            "Excluir Conta",
            f"Deseja excluir a conta '{summary.descricao}'?\n"
            f"Atenção: lançamentos vinculados a esta conta precisarão ser reatribuídos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.account_repo.delete_account(summary.id)
            if self.on_data_mutated:
                self.on_data_mutated()
            self.refresh_data()

    def _on_reconcile_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self._summaries)):
            return
        summary = self._summaries[row]
        dlg = BalanceReconcileDialog(self.account_repo, summary, parent=self)
        if dlg.exec():
            if self.on_data_mutated:
                self.on_data_mutated()
            self.refresh_data()
