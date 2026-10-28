"""Tela Nativa de Transações / Extrato Mensal (`TransacoesView`)."""

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
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
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
    TRANSFER_AMBER,
    WARNING_ORANGE,
)
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.tag_repository import TagRepository
from app.domain.models import (
    ALL_KINDS,
    FIXED_CODES,
    KIND_DESPESA,
    KIND_RECEITA,
    KIND_TRANSFERENCIA,
    REC_FIXA_DESPESA,
    REC_FIXA_MENSAL,
    REC_PARCELADA,
    REC_UNICA,
    Occurrence,
    SplitDTO,
    fixed_code_for,
)
from app.domain.services.credit_card_service import (
    CreditCardService,
    brand_icon_filename,
)
from app.domain.services.transaction_service import TransactionService
from app.ui.bank_icons import create_color_badge_icon, get_card_brand_icon
from app.ui.components import Badge, EmptyStateWidget
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import format_currency, format_date_br


def _qdate_to_py(qd: QDate) -> date:
    return date(qd.year(), qd.month(), qd.day())


def _py_to_qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


class SplitEditorDialog(QDialog):
    """Modal para configurar o Rateio Multi-Categoria (`despesas_cat_valor`)."""

    def __init__(
        self,
        cat_repo: CategoryRepository,
        profile_id: str,
        total_amount: float,
        existing_splits: List[SplitDTO],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.cat_repo = cat_repo
        self.profile_id = profile_id
        self.total_amount = max(0.01, float(total_amount))
        self.splits: List[SplitDTO] = list(existing_splits)
        self.setWindowTitle("Rateio Multi-Categoria da Despesa")
        self.setMinimumWidth(640)
        self.setMinimumHeight(420)

        self._categories = self.cat_repo.list_categories("DESPESA", profile_id)
        self._build_ui()
        self._refresh_table()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)

        info = QLabel(
            f"Divida a despesa em duas ou mais categorias/subcategorias. "
            f"Valor de referência: <b>{format_currency(self.total_amount)}</b>"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        # Linha de adição de item de rateio
        add_row = QHBoxLayout()
        self.cb_cat = QComboBox()
        for c in self._categories:
            self.cb_cat.addItem(
                create_color_badge_icon(c.color_hex, c.name[:1], size=18),
                c.name,
                c.id,
            )
        self.cb_cat.currentIndexChanged.connect(self._on_cat_changed)

        self.cb_sub = QComboBox()
        self._on_cat_changed()

        self.sp_val = QDoubleSpinBox()
        self.sp_val.setRange(0.01, 999_999_999.99)
        self.sp_val.setDecimals(2)
        self.sp_val.setPrefix("R$ ")
        self.sp_val.setValue(round(self.total_amount / 2.0, 2))

        btn_add = QPushButton("Adicionar Parte")
        btn_add.setObjectName("PrimaryButton")
        btn_add.setIcon(get_line_icon("plus", color="#FFFFFF", size=16))
        btn_add.clicked.connect(self._add_split_item)

        add_row.addWidget(QLabel("Categoria:"))
        add_row.addWidget(self.cb_cat, stretch=2)
        add_row.addWidget(QLabel("Subcategoria:"))
        add_row.addWidget(self.cb_sub, stretch=2)
        add_row.addWidget(self.sp_val, stretch=1)
        add_row.addWidget(btn_add)
        lay.addLayout(add_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Categoria", "Subcategoria", "Valor", "Proporção"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        lay.addWidget(self.table, stretch=1)

        bottom_row = QHBoxLayout()
        btn_remove = QPushButton("Remover Selecionado")
        btn_remove.setObjectName("SecondaryButton")
        btn_remove.setIcon(get_line_icon("trash", size=16))
        btn_remove.clicked.connect(self._remove_selected)
        bottom_row.addWidget(btn_remove)

        bottom_row.addStretch()
        self.lbl_sum = QLabel()
        bottom_row.addWidget(self.lbl_sum)
        lay.addLayout(bottom_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("Confirmar Rateio")
        btn_ok.setObjectName("PrimaryButton")
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _on_cat_changed(self) -> None:
        self.cb_sub.clear()
        cat_id = self.cb_cat.currentData()
        if not cat_id:
            return
        for c in self._categories:
            if c.id == str(cat_id):
                for s in c.subcategories:
                    self.cb_sub.addItem(s.name, s.id)
                break

    def _add_split_item(self) -> None:
        cat_id = str(self.cb_cat.currentData() or "")
        cat_name = self.cb_cat.currentText()
        sub_id = str(self.cb_sub.currentData() or "")
        sub_name = self.cb_sub.currentText()
        val = round(float(self.sp_val.value()), 2)
        if not cat_id or val <= 0:
            return
        self.splits.append(
            SplitDTO(
                id_categoria=cat_id,
                id_subcategoria=sub_id,
                valor=val,
                categoria_nome=cat_name,
                subcategoria_nome=sub_name,
            )
        )
        self._refresh_table()

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.splits):
            self.splits.pop(row)
            self._refresh_table()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        total_split = sum(s.valor for s in self.splits)
        for idx, s in enumerate(self.splits):
            self.table.insertRow(idx)
            self.table.setItem(idx, 0, QTableWidgetItem(s.categoria_nome or s.id_categoria))
            self.table.setItem(idx, 1, QTableWidgetItem(s.subcategoria_nome or s.id_subcategoria))
            it_val = QTableWidgetItem(format_currency(s.valor))
            it_val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(idx, 2, it_val)
            pct = (s.valor / total_split * 100.0) if total_split > 0 else 0.0
            it_pct = QTableWidgetItem(f"{pct:.1f}%")
            it_pct.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 3, it_pct)
        diff = round(self.total_amount - total_split, 2)
        self.lbl_sum.setText(
            f"Soma do Rateio: <b>{format_currency(total_split)}</b>  |  "
            f"Diferença: <b>{format_currency(diff)}</b>"
        )
        rem = max(0.01, round(self.total_amount - total_split, 2))
        self.sp_val.setValue(rem)

    def _on_accept(self) -> None:
        if not self.splits:
            QMessageBox.warning(
                self,
                "Rateio vazio",
                "Adicione ao menos uma categoria ao rateio ou cancele.",
            )
            return
        self.accept()


class ExpenseDialog(QDialog):
    """Modal nativo para Nova / Editar Despesa (Conta ou Cartão, Parcelada/Fixa e Rateio)."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        default_date: date,
        card_mode: bool = False,
        preselect_card_id: Optional[str] = None,
        occurrence: Optional[Occurrence] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.default_date = default_date
        self.occurrence = occurrence
        self.account_repo = AccountRepository(db)
        self.cat_repo = CategoryRepository(db)
        self.tag_repo = TagRepository(db)
        self.card_service = CreditCardService(db)
        self.custom_splits: List[SplitDTO] = (
            list(occurrence.splits) if (occurrence and len(occurrence.splits) > 1) else []
        )

        is_edit = occurrence is not None
        self.setWindowTitle(
            "Editar Despesa"
            if is_edit
            else ("Nova Despesa de Cartão" if card_mode else "Nova Despesa")
        )
        self.setMinimumWidth(560)

        self._accounts = self.account_repo.list_accounts(profile_id)
        self._cards = self.card_service.list_cards(profile_id)
        self._categories = self.cat_repo.list_categories("DESPESA", profile_id)
        self._tags = self.tag_repo.list_tags(profile_id)

        self._build_ui(card_mode=card_mode, preselect_card_id=preselect_card_id)
        if occurrence is not None:
            self._populate_from_occurrence(occurrence)

    def _build_ui(
        self, card_mode: bool, preselect_card_id: Optional[str]
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        # Tipo de Lançamento (Despesa vs Receita)
        self.cb_kind = QComboBox()
        self.cb_kind.addItem(get_line_icon("arrow-down", color=EXPENSE_RED, size=16), "Despesa", KIND_DESPESA)
        self.cb_kind.addItem(get_line_icon("arrow-up", color=INCOME_GREEN, size=16), "Receita", KIND_RECEITA)
        self.cb_kind.currentIndexChanged.connect(self._on_kind_changed)
        form.addRow("Tipo:", self.cb_kind)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("Ex.: Supermercado, Aluguel, Combustível...")
        form.addRow("Descrição*:", self.ed_desc)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(50.00)
        form.addRow("Valor (R$)*:", self.sp_valor)

        # Meio de Pagamento: Conta vs Cartão de Crédito
        dest_row = QHBoxLayout()
        self.rb_conta = QRadioButton("Conta Bancária")
        self.rb_cartao = QRadioButton("Cartão de Crédito")
        if card_mode and self._cards:
            self.rb_cartao.setChecked(True)
        else:
            self.rb_conta.setChecked(True)
        self.rb_conta.toggled.connect(self._on_dest_mode_changed)
        dest_row.addWidget(self.rb_conta)
        dest_row.addWidget(self.rb_cartao)
        dest_row.addStretch()
        form.addRow("Meio de Pagamento:", dest_row)

        self.cb_conta = QComboBox()
        for acc in self._accounts:
            self.cb_conta.addItem(acc.name, acc.id)
        form.addRow("Conta Bancária:", self.cb_conta)

        self.cb_cartao = QComboBox()
        for idx, c in enumerate(self._cards):
            card_icon = get_card_brand_icon(brand_icon_filename(c.brand_key), size=18)
            self.cb_cartao.addItem(
                card_icon,
                f"{c.nome} (Fecha dia {c.dia_fecha} / Vence dia {c.dia_venc})",
                c.id,
            )
            if preselect_card_id and c.id == preselect_card_id:
                self.cb_cartao.setCurrentIndex(idx)
        form.addRow("Cartão de Crédito:", self.cb_cartao)

        # Datas
        dates_row = QHBoxLayout()
        self.dt_venc = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_venc.setCalendarPopup(True)
        self.dt_venc.setDisplayFormat("dd/MM/yyyy")

        self.dt_evento = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_evento.setCalendarPopup(True)
        self.dt_evento.setDisplayFormat("dd/MM/yyyy")

        dates_row.addWidget(QLabel("Vencimento:"))
        dates_row.addWidget(self.dt_venc)
        dates_row.addSpacing(12)
        dates_row.addWidget(QLabel("Data da Compra:"))
        dates_row.addWidget(self.dt_evento)
        form.addRow("Datas:", dates_row)

        # Categoria + Botão de Rateio Multi-Categoria
        cat_row = QHBoxLayout()
        self.cb_cat = QComboBox()
        for c in self._categories:
            self.cb_cat.addItem(
                create_color_badge_icon(c.color_hex, c.name[:1], size=18),
                c.name,
                c.id,
            )
        self.cb_cat.currentIndexChanged.connect(self._on_cat_changed)
        self.cb_sub = QComboBox()
        self._on_cat_changed()

        self.btn_split = QPushButton("Rateio Multi-Categoria")
        self.btn_split.setObjectName("SecondaryButton")
        self.btn_split.setIcon(get_line_icon("pie-chart", size=16))
        self.btn_split.setAutoDefault(False)
        self.btn_split.setDefault(False)
        self.btn_split.clicked.connect(self._open_split_dialog)

        cat_row.addWidget(self.cb_cat, stretch=2)
        cat_row.addWidget(self.cb_sub, stretch=2)
        cat_row.addWidget(self.btn_split)
        form.addRow("Categoria / Sub:", cat_row)

        self.lbl_split_status = QLabel("")
        self.lbl_split_status.setStyleSheet(f"color: {PRIMARY_BLUE}; font-weight: 600;")
        form.addRow("", self.lbl_split_status)

        # Recorrência
        rec_row = QHBoxLayout()
        self.cb_rec = QComboBox()
        self.cb_rec.addItem("Única (À vista)", REC_UNICA)
        self.cb_rec.addItem("Parcelada (Ex.: 2x a 120x)", REC_PARCELADA)
        self.cb_rec.addItem("Fixa Mensal (Recorrente)", REC_FIXA_DESPESA)
        self.cb_rec.currentIndexChanged.connect(self._on_rec_changed)

        self.sp_parcelas = QSpinBox()
        self.sp_parcelas.setRange(2, 240)
        self.sp_parcelas.setValue(2)
        self.sp_parcelas.setSuffix(" parcelas")

        self.chk_val_parcela = QCheckBox("Valor informado já é de cada parcela")

        rec_row.addWidget(self.cb_rec)
        rec_row.addWidget(self.sp_parcelas)
        rec_row.addWidget(self.chk_val_parcela)
        form.addRow("Recorrência:", rec_row)

        if self.occurrence is not None:
            if self.occurrence.is_installment:
                self.cb_rec.setCurrentIndex(1)
                self.sp_parcelas.setValue(self.occurrence.num_parcelas)
                self.cb_rec.setEnabled(False)
                self.sp_parcelas.setEnabled(False)
                self.chk_val_parcela.setEnabled(False)
            elif self.occurrence.is_fixed:
                self.cb_rec.setCurrentIndex(2)
            else:
                self.cb_rec.setCurrentIndex(0)
            self._on_rec_changed()

            # Escopo de edição para séries parceladas/fixas
            self.cb_scope = QComboBox()
            if self.occurrence.is_installment:
                self.cb_scope.addItem("Toda a série (todas as parcelas)", "all")
                self.cb_scope.addItem("Somente esta parcela", "this")
                self.cb_scope.setCurrentIndex(0)
            elif self.occurrence.is_recurring:
                self.cb_scope.addItem("Toda a série (todas as fixas)", "all")
                self.cb_scope.addItem("Somente esta ocorrência (exceção deste mês)", "this")
                self.cb_scope.setCurrentIndex(0)
            else:
                self.cb_scope.addItem("Somente esta ocorrência", "this")
            form.addRow("Escopo da Edição:", self.cb_scope)
        else:
            self._on_rec_changed()

        # Status de pagamento
        self.chk_pago = QCheckBox("Já está paga / efetivada")
        form.addRow("Situação:", self.chk_pago)

        # Compra em nome de terceiro / Empréstimo de cartão
        terc_row = QHBoxLayout()
        self.chk_terceiro = QCheckBox(
            "Compra em nome de terceiro / Empréstimo de cartão"
        )
        self.ed_terceiro_pessoa = QLineEdit()
        self.ed_terceiro_pessoa.setPlaceholderText(
            "Pessoa / Familiar (Ex.: Pedro - Irmão)"
        )
        self.ed_terceiro_pessoa.setEnabled(False)
        self.chk_terceiro.toggled.connect(self.ed_terceiro_pessoa.setEnabled)
        if self.occurrence is not None:
            self.chk_terceiro.setChecked(not self.occurrence.contabilizar)
            self.chk_terceiro.setEnabled(False)
            self.ed_terceiro_pessoa.setEnabled(False)
        terc_row.addWidget(self.chk_terceiro, stretch=1)
        terc_row.addWidget(self.ed_terceiro_pessoa, stretch=1)
        form.addRow("Terceiros:", terc_row)

        # Tags (multi-seleção compacta)
        self.list_tags = QListWidget()
        self.list_tags.setMaximumHeight(76)
        for t in self._tags:
            it = QListWidgetItem(
                create_color_badge_icon(t.color_hex, "#", size=16),
                t.name,
            )
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.list_tags.addItem(it)
        form.addRow("Tags:", self.list_tags)

        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Observações adicionais (opcional)")
        form.addRow("Observações:", self.ed_obs)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_save = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.btn_save.setText("Salvar Despesa")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setDefault(True)
        self.btn_save.setAutoDefault(True)
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_dest_mode_changed()
        self._update_split_badge()

    def selected_kind(self) -> str:
        if hasattr(self, "cb_kind"):
            return str(self.cb_kind.currentData() or KIND_DESPESA)
        return KIND_DESPESA

    def _on_kind_changed(self) -> None:
        is_income = self.selected_kind() == KIND_RECEITA
        if is_income:
            self.setWindowTitle("Editar Receita" if self.occurrence else "Nova Receita")
            if hasattr(self, "btn_save") and self.btn_save:
                self.btn_save.setText("Salvar Receita")
            self.chk_pago.setText("Já foi recebida / efetivada")
            self.rb_conta.setChecked(True)
            self.rb_cartao.setEnabled(False)
            self.cb_cartao.setEnabled(False)
            self.btn_split.setEnabled(False)
            self.chk_terceiro.setEnabled(False)
            self.ed_terceiro_pessoa.setEnabled(False)
            self.dt_evento.setEnabled(False)
            self._categories = self.cat_repo.list_categories("RECEITA", self.profile_id)
        else:
            self.setWindowTitle(
                "Editar Despesa"
                if self.occurrence
                else ("Nova Despesa de Cartão" if getattr(self, "card_mode", False) else "Nova Despesa")
            )
            if hasattr(self, "btn_save") and self.btn_save:
                self.btn_save.setText("Salvar Despesa")
            self.chk_pago.setText("Já está paga / efetivada")
            self.rb_cartao.setEnabled(True)
            self.btn_split.setEnabled(True)
            self.dt_evento.setEnabled(True)
            self._on_dest_mode_changed()
            if self.occurrence is None:
                self.chk_terceiro.setEnabled(True)
                self.ed_terceiro_pessoa.setEnabled(self.chk_terceiro.isChecked())
            self._categories = self.cat_repo.list_categories("DESPESA", self.profile_id)

        self.cb_cat.blockSignals(True)
        self.cb_cat.clear()
        for c in self._categories:
            self.cb_cat.addItem(
                create_color_badge_icon(c.color_hex, c.name[:1], size=18),
                c.name,
                c.id,
            )
        self.cb_cat.blockSignals(False)
        self._on_cat_changed()

    def _on_cat_changed(self) -> None:
        self.cb_sub.clear()
        cat_id = self.cb_cat.currentData()
        if not cat_id:
            return
        for c in self._categories:
            if c.id == str(cat_id):
                for s in c.subcategories:
                    self.cb_sub.addItem(s.name, s.id)
                break

    def _on_dest_mode_changed(self) -> None:
        is_card = self.rb_cartao.isChecked()
        self.cb_cartao.setEnabled(is_card)
        self.cb_conta.setEnabled(not is_card)
        if is_card:
            if self.occurrence is not None and self.occurrence.is_card:
                self.chk_pago.setChecked(self.occurrence.efetivada)
            else:
                self.chk_pago.setChecked(False)
            self.chk_pago.setEnabled(False)
        else:
            self.chk_pago.setEnabled(True)

    def _on_rec_changed(self) -> None:
        is_parc = self.cb_rec.currentData() == REC_PARCELADA
        self.sp_parcelas.setVisible(is_parc)
        self.chk_val_parcela.setVisible(is_parc)

    def _open_split_dialog(self) -> None:
        dlg = SplitEditorDialog(
            cat_repo=self.cat_repo,
            profile_id=self.profile_id,
            total_amount=float(self.sp_valor.value()),
            existing_splits=self.custom_splits,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.custom_splits = dlg.splits
            self._update_split_badge()

    def _update_split_badge(self) -> None:
        if len(self.custom_splits) > 1:
            self.lbl_split_status.setText(
                f"Rateio ativo em {len(self.custom_splits)} categorias "
                f"({', '.join(s.categoria_nome or s.id_categoria for s in self.custom_splits)})"
            )
            self.cb_cat.setEnabled(False)
            self.cb_sub.setEnabled(False)
        else:
            self.lbl_split_status.setText("")
            self.cb_cat.setEnabled(True)
            self.cb_sub.setEnabled(True)

    def _populate_from_occurrence(self, occ: Occurrence) -> None:
        if hasattr(self, "cb_kind"):
            idx_k = self.cb_kind.findData(occ.kind)
            if idx_k >= 0:
                self.cb_kind.setCurrentIndex(idx_k)

        self.ed_desc.setText(occ.descricao)
        self.sp_valor.setValue(occ.valor)
        if occ.is_card:
            self.rb_cartao.setChecked(True)
            idx = self.cb_cartao.findData(occ.id_cartao)
            if idx >= 0:
                self.cb_cartao.setCurrentIndex(idx)
        else:
            self.rb_conta.setChecked(True)
            idx = self.cb_conta.findData(occ.id_conta)
            if idx >= 0:
                self.cb_conta.setCurrentIndex(idx)

        self.dt_venc.setDate(_py_to_qdate(occ.data_vencimento))
        if occ.data_evento:
            self.dt_evento.setDate(_py_to_qdate(occ.data_evento))
        if occ.id_categoria:
            idx_c = self.cb_cat.findData(occ.id_categoria)
            if idx_c >= 0:
                self.cb_cat.setCurrentIndex(idx_c)
                self._on_cat_changed()
            if occ.id_subcategoria:
                idx_s = self.cb_sub.findData(occ.id_subcategoria)
                if idx_s >= 0:
                    self.cb_sub.setCurrentIndex(idx_s)
        self.chk_pago.setChecked(occ.efetivada)
        self.ed_obs.setText(occ.obs)
        selected_tag_ids = {tid for tid, _, _ in occ.tags}
        for i in range(self.list_tags.count()):
            item = self.list_tags.item(i)
            if str(item.data(Qt.ItemDataRole.UserRole)) in selected_tag_ids:
                item.setCheckState(Qt.CheckState.Checked)
        self._update_split_badge()

    def selected_tag_ids(self) -> List[str]:
        out: List[str] = []
        for i in range(self.list_tags.count()):
            item = self.list_tags.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return out

    def _validate_and_accept(self) -> None:
        if not self.ed_desc.text().strip():
            kind_name = "receita" if self.selected_kind() == KIND_RECEITA else "despesa"
            QMessageBox.warning(self, "Campo obrigatório", f"Informe a descrição da {kind_name}.")
            return
        if self.selected_kind() == KIND_DESPESA and self.rb_cartao.isChecked() and not self.cb_cartao.currentData():
            QMessageBox.warning(
                self,
                "Cartão necessário",
                "Cadastre um cartão de crédito antes de lançar despesas no cartão.",
            )
            return
        self.accept()


class IncomeDialog(QDialog):
    """Modal nativo para Nova / Editar Receita."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        default_date: date,
        occurrence: Optional[Occurrence] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.default_date = default_date
        self.occurrence = occurrence
        self.account_repo = AccountRepository(db)
        self.cat_repo = CategoryRepository(db)
        self.tag_repo = TagRepository(db)

        self.setWindowTitle("Editar Receita" if occurrence else "Nova Receita")
        self.setMinimumWidth(520)

        self._accounts = self.account_repo.list_accounts(profile_id)
        self._categories = self.cat_repo.list_categories("RECEITA", profile_id)
        self._tags = self.tag_repo.list_tags(profile_id)
        self._build_ui()
        if occurrence is not None:
            self._populate(occurrence)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        # Tipo de Lançamento (Receita vs Despesa)
        self.cb_kind = QComboBox()
        self.cb_kind.addItem(get_line_icon("arrow-up", color=INCOME_GREEN, size=16), "Receita", KIND_RECEITA)
        self.cb_kind.addItem(get_line_icon("arrow-down", color=EXPENSE_RED, size=16), "Despesa", KIND_DESPESA)
        self.cb_kind.currentIndexChanged.connect(self._on_kind_changed)
        form.addRow("Tipo:", self.cb_kind)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("Ex.: Salário, Dividendos, Reembolso...")
        form.addRow("Descrição*:", self.ed_desc)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(1000.00)
        form.addRow("Valor (R$)*:", self.sp_valor)

        self.cb_conta = QComboBox()
        for acc in self._accounts:
            self.cb_conta.addItem(acc.name, acc.id)
        form.addRow("Conta de Destino:", self.cb_conta)

        self.dt_venc = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_venc.setCalendarPopup(True)
        self.dt_venc.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Data Prevista / Recebimento:", self.dt_venc)

        cat_row = QHBoxLayout()
        self.cb_cat = QComboBox()
        for c in self._categories:
            self.cb_cat.addItem(
                create_color_badge_icon(c.color_hex, c.name[:1], size=18),
                c.name,
                c.id,
            )
        self.cb_cat.currentIndexChanged.connect(self._on_cat_changed)
        self.cb_sub = QComboBox()
        self._on_cat_changed()
        cat_row.addWidget(self.cb_cat, stretch=1)
        cat_row.addWidget(self.cb_sub, stretch=1)
        form.addRow("Categoria / Sub:", cat_row)

        # Recorrência
        rec_row = QHBoxLayout()
        self.cb_rec = QComboBox()
        self.cb_rec.addItem("Única", REC_UNICA)
        self.cb_rec.addItem("Parcelada", REC_PARCELADA)
        self.cb_rec.addItem("Fixa Mensal (Recorrente)", REC_FIXA_MENSAL)
        self.cb_rec.currentIndexChanged.connect(self._on_rec_changed)

        self.sp_parcelas = QSpinBox()
        self.sp_parcelas.setRange(2, 240)
        self.sp_parcelas.setValue(2)
        self.sp_parcelas.setSuffix(" parcelas")

        self.chk_val_parcela = QCheckBox("Valor já é de cada parcela")
        rec_row.addWidget(self.cb_rec)
        rec_row.addWidget(self.sp_parcelas)
        rec_row.addWidget(self.chk_val_parcela)
        form.addRow("Recorrência:", rec_row)

        if self.occurrence is not None:
            if self.occurrence.is_installment:
                self.cb_rec.setCurrentIndex(1)
                self.sp_parcelas.setValue(self.occurrence.num_parcelas)
                self.cb_rec.setEnabled(False)
                self.sp_parcelas.setEnabled(False)
                self.chk_val_parcela.setEnabled(False)
            elif self.occurrence.is_fixed:
                self.cb_rec.setCurrentIndex(2)
            else:
                self.cb_rec.setCurrentIndex(0)
            self._on_rec_changed()

            self.cb_scope = QComboBox()
            if self.occurrence.is_installment:
                self.cb_scope.addItem("Toda a série", "all")
                self.cb_scope.addItem("Somente esta parcela", "this")
                self.cb_scope.setCurrentIndex(0)
            elif self.occurrence.is_recurring:
                self.cb_scope.addItem("Toda a série (todas as fixas)", "all")
                self.cb_scope.addItem("Somente esta ocorrência", "this")
                self.cb_scope.setCurrentIndex(0)
            else:
                self.cb_scope.addItem("Somente esta ocorrência", "this")
            form.addRow("Escopo da Edição:", self.cb_scope)
        else:
            self._on_rec_changed()

        self.chk_recebido = QCheckBox("Já foi recebida / efetivada")
        form.addRow("Situação:", self.chk_recebido)

        self.list_tags = QListWidget()
        self.list_tags.setMaximumHeight(76)
        for t in self._tags:
            it = QListWidgetItem(
                create_color_badge_icon(t.color_hex, "#", size=16),
                t.name,
            )
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.list_tags.addItem(it)
        form.addRow("Tags:", self.list_tags)

        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Observações adicionais (opcional)")
        form.addRow("Observações:", self.ed_obs)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_save = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.btn_save.setText("Salvar Receita")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setDefault(True)
        self.btn_save.setAutoDefault(True)
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_kind(self) -> str:
        if hasattr(self, "cb_kind"):
            return str(self.cb_kind.currentData() or KIND_RECEITA)
        return KIND_RECEITA

    def _on_kind_changed(self) -> None:
        is_despesa = self.selected_kind() == KIND_DESPESA
        if is_despesa:
            self.setWindowTitle("Editar Despesa" if self.occurrence else "Nova Despesa")
            if hasattr(self, "btn_save") and self.btn_save:
                self.btn_save.setText("Salvar Despesa")
            self.chk_recebido.setText("Já está paga / efetivada")
            self._categories = self.cat_repo.list_categories("DESPESA", self.profile_id)
        else:
            self.setWindowTitle("Editar Receita" if self.occurrence else "Nova Receita")
            if hasattr(self, "btn_save") and self.btn_save:
                self.btn_save.setText("Salvar Receita")
            self.chk_recebido.setText("Já foi recebida / efetivada")
            self._categories = self.cat_repo.list_categories("RECEITA", self.profile_id)

        self.cb_cat.blockSignals(True)
        self.cb_cat.clear()
        for c in self._categories:
            self.cb_cat.addItem(
                create_color_badge_icon(c.color_hex, c.name[:1], size=18),
                c.name,
                c.id,
            )
        self.cb_cat.blockSignals(False)
        self._on_cat_changed()

    def _on_cat_changed(self) -> None:
        self.cb_sub.clear()
        cat_id = self.cb_cat.currentData()
        if not cat_id:
            return
        for c in self._categories:
            if c.id == str(cat_id):
                for s in c.subcategories:
                    self.cb_sub.addItem(s.name, s.id)
                break

    def _on_rec_changed(self) -> None:
        is_parc = self.cb_rec.currentData() == REC_PARCELADA
        self.sp_parcelas.setVisible(is_parc)
        self.chk_val_parcela.setVisible(is_parc)

    def _populate(self, occ: Occurrence) -> None:
        if hasattr(self, "cb_kind"):
            idx_k = self.cb_kind.findData(occ.kind)
            if idx_k >= 0:
                self.cb_kind.setCurrentIndex(idx_k)

        self.ed_desc.setText(occ.descricao)
        self.sp_valor.setValue(occ.valor)
        idx = self.cb_conta.findData(occ.id_conta)
        if idx >= 0:
            self.cb_conta.setCurrentIndex(idx)
        self.dt_venc.setDate(_py_to_qdate(occ.data_vencimento))
        if occ.id_categoria:
            idx_c = self.cb_cat.findData(occ.id_categoria)
            if idx_c >= 0:
                self.cb_cat.setCurrentIndex(idx_c)
                self._on_cat_changed()
            if occ.id_subcategoria:
                idx_s = self.cb_sub.findData(occ.id_subcategoria)
                if idx_s >= 0:
                    self.cb_sub.setCurrentIndex(idx_s)
        self.chk_recebido.setChecked(occ.efetivada)
        self.ed_obs.setText(occ.obs)
        selected_tag_ids = {tid for tid, _, _ in occ.tags}
        for i in range(self.list_tags.count()):
            item = self.list_tags.item(i)
            if str(item.data(Qt.ItemDataRole.UserRole)) in selected_tag_ids:
                item.setCheckState(Qt.CheckState.Checked)

    def selected_tag_ids(self) -> List[str]:
        out: List[str] = []
        for i in range(self.list_tags.count()):
            item = self.list_tags.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return out

    def _validate_and_accept(self) -> None:
        if not self.ed_desc.text().strip():
            kind_name = "despesa" if self.selected_kind() == KIND_DESPESA else "receita"
            QMessageBox.warning(self, "Campo obrigatório", f"Informe a descrição da {kind_name}.")
            return
        self.accept()


class TransferDialog(QDialog):
    """Modal nativo para Nova / Editar Transferência entre Contas."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        default_date: date,
        occurrence: Optional[Occurrence] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.default_date = default_date
        self.occurrence = occurrence
        self.account_repo = AccountRepository(db)

        self.setWindowTitle(
            "Editar Transferência" if occurrence else "Nova Transferência entre Contas"
        )
        self.setMinimumWidth(480)
        self._accounts = self.account_repo.list_accounts(profile_id)
        self._build_ui()
        if occurrence is not None:
            self._populate(occurrence)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.ed_desc = QLineEdit("Transferência entre contas")
        form.addRow("Descrição:", self.ed_desc)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(250.00)
        form.addRow("Valor (R$)*:", self.sp_valor)

        self.cb_origem = QComboBox()
        self.cb_destino = QComboBox()
        for acc in self._accounts:
            self.cb_origem.addItem(acc.name, acc.id)
            self.cb_destino.addItem(acc.name, acc.id)
        if self.cb_destino.count() > 1:
            self.cb_destino.setCurrentIndex(1)
        form.addRow("Conta de Origem (Saída)*:", self.cb_origem)
        form.addRow("Conta de Destino (Entrada)*:", self.cb_destino)

        self.dt_venc = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_venc.setCalendarPopup(True)
        self.dt_venc.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Data da Transferência:", self.dt_venc)

        if self.occurrence is None:
            rec_row = QHBoxLayout()
            self.cb_rec = QComboBox()
            self.cb_rec.addItem("Única", REC_UNICA)
            self.cb_rec.addItem("Parcelada", REC_PARCELADA)
            self.cb_rec.addItem("Fixa Mensal", REC_FIXA_MENSAL)
            self.sp_parcelas = QSpinBox()
            self.sp_parcelas.setRange(2, 120)
            self.sp_parcelas.setValue(2)
            self.sp_parcelas.setVisible(False)
            self.cb_rec.currentIndexChanged.connect(
                lambda: self.sp_parcelas.setVisible(
                    self.cb_rec.currentData() == REC_PARCELADA
                )
            )
            rec_row.addWidget(self.cb_rec)
            rec_row.addWidget(self.sp_parcelas)
            form.addRow("Recorrência:", rec_row)
        else:
            self.cb_scope = QComboBox()
            self.cb_scope.addItem("Somente esta ocorrência", "this")
            if self.occurrence.is_recurring:
                self.cb_scope.addItem("Toda a série", "all")
            form.addRow("Escopo da Edição:", self.cb_scope)

        self.chk_efetivada = QCheckBox("Transferência já efetivada")
        self.chk_efetivada.setChecked(True)
        form.addRow("Situação:", self.chk_efetivada)

        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Observações adicionais (opcional)")
        form.addRow("Observações:", self.ed_obs)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_save = buttons.button(QDialogButtonBox.StandardButton.Save)
        btn_save.setText("Salvar Transferência")
        btn_save.setObjectName("PrimaryButton")
        btn_save.setDefault(True)
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self, occ: Occurrence) -> None:
        self.ed_desc.setText(occ.descricao)
        self.sp_valor.setValue(occ.valor)
        idx_o = self.cb_origem.findData(occ.id_conta)
        if idx_o >= 0:
            self.cb_origem.setCurrentIndex(idx_o)
        idx_d = self.cb_destino.findData(occ.id_conta_destino)
        if idx_d >= 0:
            self.cb_destino.setCurrentIndex(idx_d)
        self.dt_venc.setDate(_py_to_qdate(occ.data_vencimento))
        self.chk_efetivada.setChecked(occ.efetivada)
        self.ed_obs.setText(occ.obs)

    def _validate_and_accept(self) -> None:
        orig = self.cb_origem.currentData()
        dest = self.cb_destino.currentData()
        if not orig or not dest or str(orig) == str(dest):
            QMessageBox.warning(
                self,
                "Contas inválidas",
                "Selecione duas contas distintas para origem e destino.",
            )
            return
        self.accept()


class TransacoesView(QWidget):
    """
    Tela principal de Transações / Extrato Mensal padronizada com o protótipo Plutos Redesign:
    - 4 Cards KPI superiores (Saldo Anterior, Receitas, Despesas, Resultado)
    - Filtros por Tipo, Conta/Cartão e Situação com contador de lançamentos
    - Tabela completa estilizada sem grades verticais, com badges de status e números tabulares
    - Estado vazio amigável quando não houver lançamentos no período
    - Ações contextuais de clique direito, atalhos de teclado (Espaço/Enter/Del) e barra inferior discreta
    """

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
        self.tx_service = TransactionService(db)
        self.card_service = CreditCardService(db, self.tx_service)
        self.account_repo = AccountRepository(db)

        self._occurrences: List[Occurrence] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # 1. Cabeçalho + Botões de Ação (Apenas 1 primário)
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        self.lbl_title = QLabel("Transações")
        self.lbl_title.setObjectName("SectionTitle")
        self.lbl_subtitle = QLabel(
            "Extrato mensal, compras no cartão, parcelamentos e fixas"
        )
        self.lbl_subtitle.setObjectName("MutedText")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_subtitle)
        header_row.addLayout(title_col)
        header_row.addStretch()

        # Botão Primário: Nova Despesa
        self.btn_new_expense = QPushButton("Nova Despesa")
        self.btn_new_expense.setObjectName("PrimaryButton")
        self.btn_new_expense.setIcon(get_line_icon("plus", color="#FFFFFF", size=16))
        self.btn_new_expense.clicked.connect(lambda: self.open_new_expense_dialog(False))

        # Ações Secundárias Discretas
        self.btn_new_card_exp = QPushButton("Despesa Cartão")
        self.btn_new_card_exp.setObjectName("SecondaryButton")
        self.btn_new_card_exp.setIcon(get_line_icon("card", size=16))
        self.btn_new_card_exp.clicked.connect(lambda: self.open_new_expense_dialog(True))

        self.btn_new_income = QPushButton("Nova Receita")
        self.btn_new_income.setObjectName("SecondaryButton")
        self.btn_new_income.setIcon(get_line_icon("plus", size=16))
        self.btn_new_income.clicked.connect(self.open_new_income_dialog)

        self.btn_new_transfer = QPushButton("Transferência")
        self.btn_new_transfer.setObjectName("SecondaryButton")
        self.btn_new_transfer.setIcon(get_line_icon("swap", size=16))
        self.btn_new_transfer.clicked.connect(self.open_new_transfer_dialog)

        header_row.addWidget(self.btn_new_expense)
        header_row.addWidget(self.btn_new_card_exp)
        header_row.addWidget(self.btn_new_income)
        header_row.addWidget(self.btn_new_transfer)
        root.addLayout(header_row)

        # 2. Cards KPI Superiores
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.card_prev, self.lbl_prev_val, self.lbl_prev_sub = self._make_kpi_card(
            "Saldo Anterior", PRIMARY_BLUE
        )
        self.card_inc, self.lbl_inc_val, self.lbl_inc_sub = self._make_kpi_card(
            "Receitas", INCOME_GREEN
        )
        self.card_exp, self.lbl_exp_val, self.lbl_exp_sub = self._make_kpi_card(
            "Despesas", EXPENSE_RED
        )
        self.card_res, self.lbl_res_val, self.lbl_res_sub = self._make_kpi_card(
            "Resultado", PRIMARY_BLUE
        )
        kpi_row.addWidget(self.card_prev, 1)
        kpi_row.addWidget(self.card_inc, 1)
        kpi_row.addWidget(self.card_exp, 1)
        kpi_row.addWidget(self.card_res, 1)
        root.addLayout(kpi_row)

        # 3. Barra de Filtros
        filter_bar = QFrame()
        filter_bar.setObjectName("CardSurface")
        f_lay = QHBoxLayout(filter_bar)
        f_lay.setContentsMargins(14, 10, 14, 10)
        f_lay.setSpacing(12)

        lbl_filter_icon = QLabel()
        lbl_filter_icon.setPixmap(get_line_pixmap("list", color="#7B8190", size=16))
        f_lay.addWidget(lbl_filter_icon)

        self.cb_filter_kind = QComboBox()
        self.cb_filter_kind.addItem("Todos os Tipos", "ALL")
        self.cb_filter_kind.addItem("Despesas", KIND_DESPESA)
        self.cb_filter_kind.addItem("Receitas", KIND_RECEITA)
        self.cb_filter_kind.addItem("Transferências", KIND_TRANSFERENCIA)
        self.cb_filter_kind.currentIndexChanged.connect(lambda _: self.refresh_data())

        self.cb_filter_source = QComboBox()
        self.cb_filter_source.setMinimumWidth(220)
        self.cb_filter_source.currentIndexChanged.connect(lambda _: self.refresh_data())

        self.cb_filter_status = QComboBox()
        self.cb_filter_status.addItem("Qualquer Situação", "ALL")
        self.cb_filter_status.addItem("Confirmadas / Efetivadas", "EFFECTIVE")
        self.cb_filter_status.addItem("Pendentes / Em Aberto", "PENDING")
        self.cb_filter_status.currentIndexChanged.connect(lambda _: self.refresh_data())

        f_lay.addWidget(QLabel("Tipo:"))
        f_lay.addWidget(self.cb_filter_kind)
        f_lay.addWidget(QLabel("Conta / Cartão:"))
        f_lay.addWidget(self.cb_filter_source)
        f_lay.addWidget(QLabel("Situação:"))
        f_lay.addWidget(self.cb_filter_status)
        f_lay.addStretch()

        self.lbl_count_badge = QLabel("0 lançamentos")
        self.lbl_count_badge.setObjectName("MutedText")
        self.lbl_count_badge.setStyleSheet("font-size: 12px; font-weight: 500;")
        f_lay.addWidget(self.lbl_count_badge)
        root.addWidget(filter_bar)

        # 4. Tabela de Lançamentos & Empty State em QStackedWidget
        self.stack = QStackedWidget()

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Data",
                "Descrição",
                "Parcela",
                "Categoria",
                "Conta / Cartão",
                "Tags",
                "Situação",
                "Valor",
            ]
        )
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.doubleClicked.connect(lambda _: self.edit_selected_occurrence())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 175)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(4, 165)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(5, 125)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(6, 115)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.stack.addWidget(self.table)

        self.empty_widget = EmptyStateWidget(
            title="Nenhum lançamento no período",
            subtitle="Não há receitas, despesas ou transferências registradas para os filtros selecionados.",
            icon_name="list",
            action_text="+ Nova Despesa",
            action_callback=lambda: self.open_new_expense_dialog(False),
        )
        self.stack.addWidget(self.empty_widget)

        root.addWidget(self.stack, stretch=1)

        # 5. Barra Inferior de Ações Discretas
        act_bar = QHBoxLayout()
        self.btn_toggle_eff = QPushButton("Confirmar / Desfazer")
        self.btn_toggle_eff.setObjectName("SecondaryButton")
        self.btn_toggle_eff.setIcon(get_line_icon("check", size=16))
        self.btn_toggle_eff.clicked.connect(self.toggle_selected_effective)
        self.btn_toggle_eff.setEnabled(False)

        self.btn_edit = QPushButton("Editar")
        self.btn_edit.setObjectName("SecondaryButton")
        self.btn_edit.setIcon(get_line_icon("edit", size=16))
        self.btn_edit.clicked.connect(self.edit_selected_occurrence)
        self.btn_edit.setEnabled(False)

        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.setObjectName("SecondaryButton")
        self.btn_delete.setIcon(get_line_icon("trash", size=16))
        self.btn_delete.clicked.connect(self.delete_selected_occurrence)
        self.btn_delete.setEnabled(False)

        act_bar.addWidget(self.btn_toggle_eff)
        act_bar.addWidget(self.btn_edit)
        act_bar.addWidget(self.btn_delete)
        act_bar.addStretch()

        self.btn_import_sheet = QPushButton("Importar")
        self.btn_import_sheet.setObjectName("SecondaryButton")
        self.btn_import_sheet.setIcon(get_line_icon("upload", size=16))
        self.btn_import_sheet.clicked.connect(self.quick_import_spreadsheet)

        self.btn_export_sheet = QPushButton("Exportar")
        self.btn_export_sheet.setObjectName("SecondaryButton")
        self.btn_export_sheet.setIcon(get_line_icon("download", size=16))
        self.btn_export_sheet.clicked.connect(self.quick_export_spreadsheet)

        act_bar.addWidget(self.btn_import_sheet)
        act_bar.addWidget(self.btn_export_sheet)
        root.addLayout(act_bar)

    def _make_kpi_card(
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
        has_sel = self.table.currentRow() >= 0 and len(self._occurrences) > 0
        self.btn_toggle_eff.setEnabled(has_sel)
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _on_table_context_menu(self, pos) -> None:
        occ = self._selected_occurrence()
        if occ is None:
            return
        menu = QMenu(self)

        act_toggle = menu.addAction(
            get_line_icon("check", size=16),
            "Desfazer Baixa" if occ.efetivada else "Confirmar Baixa",
        )
        act_toggle.triggered.connect(self.toggle_selected_effective)

        act_edit = menu.addAction(get_line_icon("edit", size=16), "Editar Lançamento")
        act_edit.triggered.connect(self.edit_selected_occurrence)

        menu.addSeparator()

        act_del = menu.addAction(get_line_icon("trash", size=16), "Excluir Lançamento")
        act_del.triggered.connect(self.delete_selected_occurrence)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def keyPressEvent(self, event) -> None:
        if self.table.hasFocus():
            if event.key() == Qt.Key.Key_Delete:
                self.delete_selected_occurrence()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Space:
                self.toggle_selected_effective()
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.edit_selected_occurrence()
                event.accept()
                return
        super().keyPressEvent(event)

    def _reload_source_combo(self, profile_id: str) -> None:
        current_data = self.cb_filter_source.currentData()
        self.cb_filter_source.blockSignals(True)
        self.cb_filter_source.clear()
        self.cb_filter_source.addItem("Todas as Contas e Cartões", "ALL")
        self.cb_filter_source.addItem("Apenas Contas Bancárias (Caixa)", "ACCOUNTS_ONLY")
        for acc in self.account_repo.list_accounts(profile_id):
            self.cb_filter_source.addItem(f"Conta: {acc.name}", f"ACC:{acc.id}")
        for card in self.card_service.list_cards(profile_id):
            self.cb_filter_source.addItem(f"Cartão: {card.nome}", f"CARD:{card.id}")
        idx = self.cb_filter_source.findData(current_data)
        if idx >= 0:
            self.cb_filter_source.setCurrentIndex(idx)
        self.cb_filter_source.blockSignals(False)

    def refresh_data(self) -> None:
        profile_id, month, year, search_text = self.get_context()
        self._reload_source_combo(profile_id)

        mode = self.db.settings.date_reference_mode
        kind_filter = str(self.cb_filter_kind.currentData() or "ALL")
        kinds = list(ALL_KINDS) if kind_filter == "ALL" else [kind_filter]

        source_filter = str(self.cb_filter_source.currentData() or "ALL")
        id_conta: Optional[str] = None
        id_cartao: Optional[str] = None
        source: Optional[str] = None
        if source_filter == "ACCOUNTS_ONLY":
            source = "contas"
        elif source_filter.startswith("ACC:"):
            id_conta = source_filter.split(":", 1)[1]
        elif source_filter.startswith("CARD:"):
            id_cartao = source_filter.split(":", 1)[1]

        status_filter = str(self.cb_filter_status.currentData() or "ALL")
        only_effective: Optional[bool] = None
        if status_filter == "EFFECTIVE":
            only_effective = True
        elif status_filter == "PENDING":
            only_effective = False

        self._occurrences = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            kinds=kinds,
            id_conta=id_conta,
            id_cartao=id_cartao,
            source=source,
            search=search_text,
            only_effective=only_effective,
            profile_id=profile_id,
        )

        # Resumo KPI
        summary = self.tx_service.summarize(self._occurrences)
        if id_conta:
            acc_sum = self.account_repo.get_account_summary(
                id_conta, month, year
            )
            saldo_ini = acc_sum.saldo_inicial
            saldo_cur = acc_sum.saldo_atual
            saldo_prev = acc_sum.saldo_previsto
        else:
            totals_acc = self.account_repo.get_consolidated_totals(
                profile_id, month, year
            )
            saldo_ini = totals_acc["saldo_inicial"]
            saldo_cur = totals_acc["saldo_atual"]
            saldo_prev = totals_acc["saldo_previsto"]

        self.lbl_prev_val.setText(format_currency(saldo_ini))
        self.lbl_prev_sub.setText(f"Saldo Atual: {format_currency(saldo_cur)}")

        self.lbl_inc_val.setText(format_currency(summary["receitas"]))
        self.lbl_inc_sub.setText(
            f"Recebido: {format_currency(summary['receitas_efetivadas'])} | "
            f"Pend.: {format_currency(summary['receitas_pendentes'])}"
        )

        self.lbl_exp_val.setText(format_currency(summary["despesas"]))
        self.lbl_exp_sub.setText(
            f"Pago: {format_currency(summary['despesas_pagas'])} | "
            f"Pend.: {format_currency(summary['despesas_pendentes'])}"
        )

        res_val = summary["resultado"]
        self.lbl_res_val.setText(format_currency(res_val))
        self.lbl_res_val.setStyleSheet(
            f"color: {INCOME_GREEN if res_val >= 0 else EXPENSE_RED};"
        )
        self.lbl_res_sub.setText(
            f"Saldo Previsto: {format_currency(saldo_prev)}"
        )

        self.lbl_count_badge.setText(f"{len(self._occurrences)} lançamentos")
        self._populate_table()

    def _populate_table(self) -> None:
        if not self._occurrences:
            self.table.setRowCount(0)
            self.stack.setCurrentWidget(self.empty_widget)
            self._on_selection_changed()
            return

        self.stack.setCurrentWidget(self.table)
        self.table.setRowCount(0)

        # Oculta coluna de Tags se nenhuma transação possuir tags no mês
        has_tags = any(bool(occ.tags) for occ in self._occurrences)
        self.table.setColumnHidden(5, not has_tags)

        f_bold = QFont()
        f_bold.setBold(True)

        for row_idx, occ in enumerate(self._occurrences):
            self.table.insertRow(row_idx)

            # 0: Data
            it_date = QTableWidgetItem(format_date_br(occ.ref_date.isoformat()))
            it_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 0, it_date)

            # 1: Descrição
            it_desc = QTableWidgetItem(occ.descricao)
            it_desc.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row_idx, 1, it_desc)

            # 2: Parcela
            parc_label = occ.parcela_label if occ.parcela_label else "—"
            it_rec = QTableWidgetItem(parc_label)
            it_rec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if parc_label == "—" or parc_label == "Única":
                it_rec.setForeground(QColor("#7B8190"))
            self.table.setItem(row_idx, 2, it_rec)

            # 3: Categoria
            if len(occ.splits) > 1:
                cat_txt = f"Rateio ({len(occ.splits)} categorias)"
                it_cat = QTableWidgetItem(
                    create_color_badge_icon("#7B8190", "R", size=16), cat_txt
                )
            elif occ.kind == KIND_TRANSFERENCIA:
                it_cat = QTableWidgetItem(
                    get_line_icon("swap", color="#C98A12", size=16),
                    "Transferência",
                )
            else:
                cat_txt = occ.categoria_nome or "Sem categoria"
                if occ.subcategoria_nome:
                    cat_txt = f"{occ.categoria_nome} ▸ {occ.subcategoria_nome}"
                cat_color = occ.categoria_cor or "#7B8190"
                initial = occ.categoria_nome[:1] if occ.categoria_nome else "•"
                it_cat = QTableWidgetItem(
                    create_color_badge_icon(cat_color, initial, size=16),
                    cat_txt,
                )
            it_cat.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row_idx, 3, it_cat)

            # 4: Conta / Cartão
            if occ.kind == KIND_TRANSFERENCIA:
                src_txt = f"{occ.conta_nome} → {occ.conta_destino_nome}"
            elif occ.is_card:
                src_txt = occ.cartao_nome or "Cartão de Crédito"
            else:
                src_txt = occ.conta_nome or "—"
            it_src = QTableWidgetItem(src_txt)
            it_src.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row_idx, 4, it_src)

            # 5: Tags
            tags_txt = ", ".join(f"#{n}" for _, n, _ in occ.tags) if occ.tags else "—"
            it_tags = QTableWidgetItem(tags_txt)
            it_tags.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if not occ.tags:
                it_tags.setForeground(QColor("#7B8190"))
            self.table.setItem(row_idx, 5, it_tags)

            # 6: Situação (Item de texto para ordenação/busca + Badge visual na célula)
            status_text = "Efetivado" if occ.efetivada else "Pendente"
            variant = "success" if occ.efetivada else "warning"
            it_status = QTableWidgetItem(status_text)
            it_status.setForeground(QColor(0, 0, 0, 0))
            it_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 6, it_status)

            badge = Badge(status_text, variant=variant)
            badge_wrap = QWidget()
            b_lay = QHBoxLayout(badge_wrap)
            b_lay.setContentsMargins(0, 0, 0, 0)
            b_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_lay.addWidget(badge)
            self.table.setCellWidget(row_idx, 6, badge_wrap)

            # 7: Valor
            if occ.kind == KIND_RECEITA:
                sign = "+ "
                val_color = QColor(INCOME_GREEN)
            elif occ.kind == KIND_DESPESA:
                sign = "− "
                val_color = QColor(EXPENSE_RED)
            else:
                sign = ""
                val_color = QColor(TRANSFER_AMBER)
            it_val = QTableWidgetItem(f"{sign}{format_currency(occ.total)}")
            it_val.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_val.setFont(f_bold)
            it_val.setForeground(val_color)
            self.table.setItem(row_idx, 7, it_val)

        self._on_selection_changed()

    def _selected_occurrence(self) -> Optional[Occurrence]:
        row = self.table.currentRow()
        if 0 <= row < len(self._occurrences):
            return self._occurrences[row]
        return None

    # ------------------------------------------------------------------ #
    # Diálogos e Ações de Mutação
    # ------------------------------------------------------------------ #
    def open_new_expense_dialog(
        self, card_mode: bool = False, preselect_card_id: Optional[str] = None
    ) -> None:
        profile_id, month, year, _ = self.get_context()
        default_dt = date(year, month, min(date.today().day, 28))
        dlg = ExpenseDialog(
            self.db,
            profile_id=profile_id,
            default_date=default_dt,
            card_mode=card_mode,
            preselect_card_id=preselect_card_id,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if dlg.selected_kind() == KIND_RECEITA:
            rec_code = str(dlg.cb_rec.currentData() or REC_UNICA)
            num_parc = int(dlg.sp_parcelas.value()) if rec_code == REC_PARCELADA else 1
            rec_income = fixed_code_for(KIND_RECEITA) if rec_code in FIXED_CODES[KIND_DESPESA] or rec_code == "M" else rec_code
            self.tx_service.create_income(
                descricao=dlg.ed_desc.text().strip(),
                valor=float(dlg.sp_valor.value()),
                data=_qdate_to_py(dlg.dt_venc.date()),
                id_conta=str(dlg.cb_conta.currentData()) if dlg.cb_conta.currentData() else None,
                profile_id=profile_id,
                id_categoria=str(dlg.cb_cat.currentData()) if dlg.cb_cat.currentData() else None,
                id_subcategoria=str(dlg.cb_sub.currentData()) if dlg.cb_sub.currentData() else None,
                recorrencia=rec_income,
                num_parcelas=num_parc,
                valor_por_parcela=dlg.chk_val_parcela.isChecked(),
                recebido=dlg.chk_pago.isChecked(),
                obs=dlg.ed_obs.text().strip(),
                tag_ids=dlg.selected_tag_ids(),
            )
            self.on_data_mutated()
            self.refresh_data()
            return

        is_card = dlg.rb_cartao.isChecked()
        rec_code = str(dlg.cb_rec.currentData() or REC_UNICA)
        num_parc = int(dlg.sp_parcelas.value()) if rec_code == REC_PARCELADA else 1
        self.tx_service.create_expense(
            descricao=dlg.ed_desc.text().strip(),
            valor=float(dlg.sp_valor.value()),
            data_vencimento=_qdate_to_py(dlg.dt_venc.date()),
            data_evento=_qdate_to_py(dlg.dt_evento.date()),
            profile_id=profile_id,
            id_conta=str(dlg.cb_conta.currentData()) if not is_card else None,
            id_cartao=str(dlg.cb_cartao.currentData()) if is_card else None,
            id_categoria=(
                str(dlg.cb_cat.currentData())
                if len(dlg.custom_splits) <= 1 and dlg.cb_cat.currentData()
                else None
            ),
            id_subcategoria=(
                str(dlg.cb_sub.currentData())
                if len(dlg.custom_splits) <= 1 and dlg.cb_sub.currentData()
                else None
            ),
            splits=dlg.custom_splits if len(dlg.custom_splits) > 1 else None,
            recorrencia=rec_code,
            num_parcelas=num_parc,
            valor_por_parcela=dlg.chk_val_parcela.isChecked(),
            pago=dlg.chk_pago.isChecked(),
            obs=dlg.ed_obs.text().strip(),
            tag_ids=dlg.selected_tag_ids(),
            terceiro_em_nome_de=(
                dlg.ed_terceiro_pessoa.text().strip()
                if dlg.chk_terceiro.isChecked()
                else None
            ),
            gerar_emprestimo_terceiro=dlg.chk_terceiro.isChecked(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def open_new_income_dialog(self) -> None:
        profile_id, month, year, _ = self.get_context()
        default_dt = date(year, month, min(date.today().day, 28))
        dlg = IncomeDialog(
            self.db,
            profile_id=profile_id,
            default_date=default_dt,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if dlg.selected_kind() == KIND_DESPESA:
            rec_code = str(dlg.cb_rec.currentData() or REC_UNICA)
            num_parc = int(dlg.sp_parcelas.value()) if rec_code == REC_PARCELADA else 1
            rec_exp = fixed_code_for(KIND_DESPESA) if rec_code in FIXED_CODES[KIND_RECEITA] or rec_code == "M" else rec_code
            self.tx_service.create_expense(
                descricao=dlg.ed_desc.text().strip(),
                valor=float(dlg.sp_valor.value()),
                data_vencimento=_qdate_to_py(dlg.dt_venc.date()),
                data_evento=_qdate_to_py(dlg.dt_venc.date()),
                profile_id=profile_id,
                id_conta=str(dlg.cb_conta.currentData()) if dlg.cb_conta.currentData() else None,
                id_categoria=str(dlg.cb_cat.currentData()) if dlg.cb_cat.currentData() else None,
                id_subcategoria=str(dlg.cb_sub.currentData()) if dlg.cb_sub.currentData() else None,
                recorrencia=rec_exp,
                num_parcelas=num_parc,
                valor_por_parcela=dlg.chk_val_parcela.isChecked(),
                pago=dlg.chk_recebido.isChecked(),
                obs=dlg.ed_obs.text().strip(),
                tag_ids=dlg.selected_tag_ids(),
            )
            self.on_data_mutated()
            self.refresh_data()
            return

        rec_code = str(dlg.cb_rec.currentData() or REC_UNICA)
        num_parc = int(dlg.sp_parcelas.value()) if rec_code == REC_PARCELADA else 1
        self.tx_service.create_income(
            descricao=dlg.ed_desc.text().strip(),
            valor=float(dlg.sp_valor.value()),
            data=_qdate_to_py(dlg.dt_venc.date()),
            id_conta=str(dlg.cb_conta.currentData()) if dlg.cb_conta.currentData() else None,
            profile_id=profile_id,
            id_categoria=str(dlg.cb_cat.currentData()) if dlg.cb_cat.currentData() else None,
            id_subcategoria=str(dlg.cb_sub.currentData()) if dlg.cb_sub.currentData() else None,
            recorrencia=rec_code,
            num_parcelas=num_parc,
            valor_por_parcela=dlg.chk_val_parcela.isChecked(),
            recebido=dlg.chk_recebido.isChecked(),
            obs=dlg.ed_obs.text().strip(),
            tag_ids=dlg.selected_tag_ids(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def open_new_transfer_dialog(self) -> None:
        profile_id, month, year, _ = self.get_context()
        default_dt = date(year, month, min(date.today().day, 28))
        dlg = TransferDialog(
            self.db,
            profile_id=profile_id,
            default_date=default_dt,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        rec_code = str(dlg.cb_rec.currentData() or REC_UNICA)
        num_parc = int(dlg.sp_parcelas.value()) if rec_code == REC_PARCELADA else 1
        self.tx_service.create_transfer(
            descricao=dlg.ed_desc.text().strip(),
            valor=float(dlg.sp_valor.value()),
            data=_qdate_to_py(dlg.dt_venc.date()),
            id_conta_origem=str(dlg.cb_origem.currentData()),
            id_conta_destino=str(dlg.cb_destino.currentData()),
            profile_id=profile_id,
            recorrencia=rec_code,
            num_parcelas=num_parc,
            efetivada=dlg.chk_efetivada.isChecked(),
            obs=dlg.ed_obs.text().strip(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def toggle_selected_effective(self) -> None:
        occ = self._selected_occurrence()
        if occ is None:
            QMessageBox.information(
                self, "Selecione um lançamento", "Clique em uma linha da tabela."
            )
            return
        self.tx_service.set_effective(occ, not occ.efetivada)
        self.on_data_mutated()
        self.refresh_data()

    def edit_selected_occurrence(self) -> None:
        occ = self._selected_occurrence()
        if occ is None:
            return
        profile_id, _, _, _ = self.get_context()

        if occ.kind == KIND_DESPESA:
            dlg = ExpenseDialog(
                self.db,
                profile_id=profile_id,
                default_date=occ.data_vencimento,
                card_mode=occ.is_card,
                occurrence=occ,
                parent=self,
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            scope = str(dlg.cb_scope.currentData() or "this") if hasattr(dlg, "cb_scope") else "this"
            new_kind = dlg.selected_kind()
            is_card = dlg.rb_cartao.isChecked() if new_kind == KIND_DESPESA else False
            rec_code = str(dlg.cb_rec.currentData() or REC_UNICA) if hasattr(dlg, "cb_rec") else None
            self.tx_service.update_occurrence(
                occ,
                scope=scope,
                new_kind=new_kind,
                recorrencia=rec_code,
                descricao=dlg.ed_desc.text().strip(),
                valor=float(dlg.sp_valor.value()),
                data_vencimento=_qdate_to_py(dlg.dt_venc.date()),
                data_evento=_qdate_to_py(dlg.dt_evento.date()) if hasattr(dlg, "dt_evento") else None,
                id_conta=(
                    str(dlg.cb_conta.currentData())
                    if not is_card and dlg.cb_conta.currentData()
                    else None
                ),
                id_cartao=(
                    str(dlg.cb_cartao.currentData())
                    if is_card and dlg.cb_cartao.currentData()
                    else None
                ),
                id_categoria=(
                    str(dlg.cb_cat.currentData())
                    if (new_kind == KIND_RECEITA or len(dlg.custom_splits) <= 1) and dlg.cb_cat.currentData()
                    else None
                ),
                id_subcategoria=(
                    str(dlg.cb_sub.currentData())
                    if (new_kind == KIND_RECEITA or len(dlg.custom_splits) <= 1) and dlg.cb_sub.currentData()
                    else None
                ),
                splits=dlg.custom_splits if (new_kind == KIND_DESPESA and len(dlg.custom_splits) > 1) else None,
                obs=dlg.ed_obs.text().strip(),
                efetivada=dlg.chk_pago.isChecked(),
                tag_ids=dlg.selected_tag_ids(),
            )
        elif occ.kind == KIND_RECEITA:
            dlg_r = IncomeDialog(
                self.db,
                profile_id=profile_id,
                default_date=occ.data_vencimento,
                occurrence=occ,
                parent=self,
            )
            if dlg_r.exec() != QDialog.DialogCode.Accepted:
                return
            scope = str(dlg_r.cb_scope.currentData() or "this") if hasattr(dlg_r, "cb_scope") else "this"
            new_kind = dlg_r.selected_kind()
            rec_code = str(dlg_r.cb_rec.currentData() or REC_UNICA) if hasattr(dlg_r, "cb_rec") else None
            self.tx_service.update_occurrence(
                occ,
                scope=scope,
                new_kind=new_kind,
                recorrencia=rec_code,
                descricao=dlg_r.ed_desc.text().strip(),
                valor=float(dlg_r.sp_valor.value()),
                data_vencimento=_qdate_to_py(dlg_r.dt_venc.date()),
                id_conta=str(dlg_r.cb_conta.currentData()) if dlg_r.cb_conta.currentData() else None,
                id_categoria=str(dlg_r.cb_cat.currentData()) if dlg_r.cb_cat.currentData() else None,
                id_subcategoria=str(dlg_r.cb_sub.currentData()) if dlg_r.cb_sub.currentData() else None,
                obs=dlg_r.ed_obs.text().strip(),
                efetivada=dlg_r.chk_recebido.isChecked(),
                tag_ids=dlg_r.selected_tag_ids(),
            )
        else:
            dlg_t = TransferDialog(
                self.db,
                profile_id=profile_id,
                default_date=occ.data_vencimento,
                occurrence=occ,
                parent=self,
            )
            if dlg_t.exec() != QDialog.DialogCode.Accepted:
                return
            scope = str(dlg_t.cb_scope.currentData() or "this")
            self.tx_service.update_occurrence(
                occ,
                scope=scope,
                descricao=dlg_t.ed_desc.text().strip(),
                valor=float(dlg_t.sp_valor.value()),
                data_vencimento=_qdate_to_py(dlg_t.dt_venc.date()),
                id_conta=str(dlg_t.cb_origem.currentData()),
                id_conta_destino=str(dlg_t.cb_destino.currentData()),
                obs=dlg_t.ed_obs.text().strip(),
                efetivada=dlg_t.chk_efetivada.isChecked(),
            )

        self.on_data_mutated()
        self.refresh_data()

    def delete_selected_occurrence(self) -> None:
        occ = self._selected_occurrence()
        if occ is None:
            return

        scope = "this"
        if occ.is_recurring:
            dlg = QDialog(self)
            dlg.setWindowTitle("Excluir Lançamento Recorrente / Parcelado")
            dlg.setMinimumWidth(440)
            v = QVBoxLayout(dlg)
            v.setContentsMargins(20, 20, 20, 20)
            v.setSpacing(12)

            lbl_info = QLabel(
                f"Como deseja excluir <b>{occ.descricao}</b> ({occ.parcela_label})?"
            )
            lbl_info.setWordWrap(True)
            v.addWidget(lbl_info)

            rb_this = QRadioButton("Somente esta ocorrência deste mês")
            rb_future = QRadioButton("Esta e todas as próximas ocorrências")
            rb_all = QRadioButton("Toda a série (inclusive anteriores)")
            rb_this.setChecked(True)
            v.addWidget(rb_this)
            v.addWidget(rb_future)
            v.addWidget(rb_all)

            bb = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok
                | QDialogButtonBox.StandardButton.Cancel
            )
            btn_ok = bb.button(QDialogButtonBox.StandardButton.Ok)
            btn_ok.setText("Confirmar Exclusão")
            btn_ok.setObjectName("PrimaryButton")
            btn_cancel = bb.button(QDialogButtonBox.StandardButton.Cancel)
            btn_cancel.setText("Cancelar")
            btn_cancel.setObjectName("SecondaryButton")
            bb.accepted.connect(dlg.accept)
            bb.rejected.connect(dlg.reject)
            v.addWidget(bb)

            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            if rb_all.isChecked():
                scope = "all"
            elif rb_future.isChecked():
                scope = "future"
        else:
            ans = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                f"Deseja excluir '{occ.descricao}' ({format_currency(occ.total)})?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self.tx_service.delete_occurrence(occ, scope=scope)
        self.on_data_mutated()
        self.refresh_data()

    def quick_import_spreadsheet(self, file_path: Optional[str] = None) -> None:
        from PySide6.QtWidgets import QFileDialog
        from app.io_module.io_orchestrator import DataIOOrchestrator

        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Importar Planilha CSV ou Excel",
                "",
                "Planilhas (*.csv *.xlsx);;CSV (*.csv);;Excel (*.xlsx)",
            )
        if not file_path:
            return
        profile_id, _, _, _ = self.get_context()
        orchestrator = DataIOOrchestrator(self.db, self.tx_service)
        report = orchestrator.import_file(file_path, profile_id=profile_id)
        self.on_data_mutated()
        self.refresh_data()
        QMessageBox.information(
            self,
            "Importação Concluída",
            f"Arquivo: {report.source_path}\n"
            f"Importados: {report.imported_count}\n"
            f"Duplicados ignorados: {report.skipped_duplicates}\n"
            f"Erros: {report.error_count}",
        )

    def quick_export_spreadsheet(self, file_path: Optional[str] = None) -> None:
        from PySide6.QtWidgets import QFileDialog
        from app.io_module.io_orchestrator import DataIOOrchestrator

        profile_id, month, year, _ = self.get_context()
        kind_filter = str(self.cb_filter_kind.currentData() or "ALL")
        exp_mode = "extrato"
        if kind_filter == KIND_DESPESA:
            exp_mode = "despesas"
        elif kind_filter == KIND_RECEITA:
            exp_mode = "receitas"
        elif kind_filter == KIND_TRANSFERENCIA:
            exp_mode = "transferencias"

        if not file_path:
            default_name = f"plutos_{exp_mode}_{year}_{month:02d}.xlsx"
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Exportar Planilha",
                default_name,
                "Planilha Excel (*.xlsx);;Arquivo CSV (*.csv)",
            )
        if not file_path:
            return
        orchestrator = DataIOOrchestrator(self.db, self.tx_service)
        report = orchestrator.export_month_data(
            file_path,
            year=year,
            month=month,
            profile_id=profile_id,
            date_mode=self.db.settings.date_reference_mode,
            export_mode=exp_mode,
        )
        QMessageBox.information(
            self,
            "Exportação Concluída",
            f"Arquivo salvo em:\n{report.target_path}\n"
            f"Registros exportados: {report.exported_rows}",
        )
