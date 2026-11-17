"""Tela Nativa de Transações / Extrato Mensal (`TransacoesView`)."""

from __future__ import annotations

from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
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
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.app_settings import DateReferenceMode
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
from app.ui.components import (
    Badge,
    DonutProgressRing,
    EmptyStateWidget,
    InstallmentMiniBar,
    KpiCard,
    SegmentedBar,
    SideDrawer,
)
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import PT_BR_MONTHS, format_currency, format_date_br


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
        self.setMinimumWidth(620)

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
        self.card_mode = card_mode
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Seletor segmentado no topo sincronizado com cb_kind (retrocompatível com testes)
        self.cb_kind = QComboBox()
        self.cb_kind.addItem(get_line_icon("arrow-down", color=EXPENSE_RED, size=16), "Despesa", KIND_DESPESA)
        self.cb_kind.addItem(get_line_icon("arrow-up", color=INCOME_GREEN, size=16), "Receita", KIND_RECEITA)
        self.cb_kind.setVisible(False)
        self.cb_kind.currentIndexChanged.connect(self._on_kind_changed)

        self.seg_kind = SegmentedBar(
            [(KIND_DESPESA, "Despesa"), (KIND_RECEITA, "Receita")],
            active_key=KIND_DESPESA,
        )
        self.seg_kind.changed.connect(self._on_segment_kind_changed)
        layout.addWidget(self.seg_kind)
        layout.addWidget(self.cb_kind)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        # Meio de Pagamento: Conta vs Cartão de Crédito
        lbl_pay = QLabel("Forma de Pagamento")
        lbl_pay.setObjectName("FormLabel")
        dest_row = QHBoxLayout()
        dest_row.setSpacing(14)
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
        grid.addWidget(lbl_pay, 0, 0, 1, 2)
        grid.addLayout(dest_row, 1, 0, 1, 2)

        # Valor + Descrição (grid 2 colunas)
        lbl_val = QLabel("Valor (R$) *")
        lbl_val.setObjectName("FormLabel")
        lbl_desc = QLabel("Descrição *")
        lbl_desc.setObjectName("FormLabel")
        grid.addWidget(lbl_val, 2, 0)
        grid.addWidget(lbl_desc, 2, 1)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(50.00)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("Ex.: Supermercado, Aluguel, Combustível...")
        grid.addWidget(self.sp_valor, 3, 0)
        grid.addWidget(self.ed_desc, 3, 1)

        # Conta Bancária / Cartão de Crédito (exibição dinâmica no mesmo slot)
        self.lbl_source = QLabel("Conta Bancária *")
        self.lbl_source.setObjectName("FormLabel")
        grid.addWidget(self.lbl_source, 4, 0, 1, 2)

        self.cb_conta = QComboBox()
        for acc in self._accounts:
            self.cb_conta.addItem(acc.name, acc.id)

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
        grid.addWidget(self.cb_conta, 5, 0, 1, 2)
        grid.addWidget(self.cb_cartao, 5, 0, 1, 2)

        # Datas (Lançamento + Vencimento)
        lbl_evt = QLabel("Data da Compra / Lançamento")
        lbl_evt.setObjectName("FormLabel")
        lbl_venc = QLabel("Data de Vencimento *")
        lbl_venc.setObjectName("FormLabel")
        grid.addWidget(lbl_evt, 6, 0)
        grid.addWidget(lbl_venc, 6, 1)

        self.dt_evento = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_evento.setCalendarPopup(True)
        self.dt_evento.setDisplayFormat("dd/MM/yyyy")

        self.dt_venc = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_venc.setCalendarPopup(True)
        self.dt_venc.setDisplayFormat("dd/MM/yyyy")
        grid.addWidget(self.dt_evento, 7, 0)
        grid.addWidget(self.dt_venc, 7, 1)

        # Categoria + Subcategoria + Rateio
        lbl_cat = QLabel("Categoria")
        lbl_cat.setObjectName("FormLabel")
        lbl_sub = QLabel("Subcategoria")
        lbl_sub.setObjectName("FormLabel")
        grid.addWidget(lbl_cat, 8, 0)
        grid.addWidget(lbl_sub, 8, 1)

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
        grid.addWidget(self.cb_cat, 9, 0)
        grid.addWidget(self.cb_sub, 9, 1)

        split_row = QHBoxLayout()
        self.btn_split = QPushButton("Rateio Multi-Categoria")
        self.btn_split.setObjectName("SecondaryButton")
        self.btn_split.setIcon(get_line_icon("pie-chart", size=16))
        self.btn_split.setAutoDefault(False)
        self.btn_split.setDefault(False)
        self.btn_split.clicked.connect(self._open_split_dialog)
        self.lbl_split_status = QLabel("")
        self.lbl_split_status.setStyleSheet(f"color: {PRIMARY_BLUE}; font-weight: 600;")
        split_row.addWidget(self.btn_split)
        split_row.addWidget(self.lbl_split_status, 1)
        grid.addLayout(split_row, 10, 0, 1, 2)

        # Recorrência + Situação
        lbl_rec = QLabel("Tipo de Lançamento / Recorrência")
        lbl_rec.setObjectName("FormLabel")
        lbl_st = QLabel("Status")
        lbl_st.setObjectName("FormLabel")
        grid.addWidget(lbl_rec, 11, 0)
        grid.addWidget(lbl_st, 11, 1)

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

        rec_row.addWidget(self.cb_rec, 1)
        rec_row.addWidget(self.sp_parcelas)
        grid.addLayout(rec_row, 12, 0)

        self.chk_pago = QCheckBox("Já está paga / efetivada")
        grid.addWidget(self.chk_pago, 12, 1)

        self.chk_val_parcela = QCheckBox("Valor informado já é de cada parcela")
        grid.addWidget(self.chk_val_parcela, 13, 0, 1, 2)

        row_idx = 14
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
            lbl_scope = QLabel("Escopo da Edição")
            lbl_scope.setObjectName("FormLabel")
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
            grid.addWidget(lbl_scope, row_idx, 0)
            grid.addWidget(self.cb_scope, row_idx, 1)
            row_idx += 1
        else:
            self._on_rec_changed()

        # Compra em nome de terceiro / Empréstimo de cartão
        self.chk_terceiro = QCheckBox("Compra em nome de terceiro")
        self.chk_terceiro.setToolTip("Compra em nome de terceiro / Empréstimo de cartão")
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
        grid.addWidget(self.chk_terceiro, row_idx, 0)
        grid.addWidget(self.ed_terceiro_pessoa, row_idx, 1)
        row_idx += 1

        # Tags + Observações
        lbl_tags = QLabel("Tags")
        lbl_tags.setObjectName("FormLabel")
        lbl_obs = QLabel("Observações")
        lbl_obs.setObjectName("FormLabel")
        grid.addWidget(lbl_tags, row_idx, 0)
        grid.addWidget(lbl_obs, row_idx, 1)
        row_idx += 1

        self.list_tags = QListWidget()
        self.list_tags.setMaximumHeight(68)
        for t in self._tags:
            it = QListWidgetItem(
                create_color_badge_icon(t.color_hex, "#", size=16),
                t.name,
            )
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.list_tags.addItem(it)

        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Observações adicionais (opcional)")
        if self._tags:
            grid.addWidget(self.list_tags, row_idx, 0)
        else:
            self.list_tags.setVisible(False)
            lbl_no_tags = QLabel("Nenhuma tag cadastrada (Cadastros → Tags)")
            lbl_no_tags.setObjectName("MutedText")
            lbl_no_tags.setStyleSheet("font-size: 12px; padding: 6px 0;")
            grid.addWidget(lbl_no_tags, row_idx, 0)
        grid.addWidget(self.ed_obs, row_idx, 1, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(grid)

        sep = QFrame()
        sep.setObjectName("ModalSeparator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

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

    def _on_segment_kind_changed(self, kind_key: str) -> None:
        idx = self.cb_kind.findData(kind_key)
        if idx >= 0 and self.cb_kind.currentIndex() != idx:
            self.cb_kind.setCurrentIndex(idx)

    def selected_kind(self) -> str:
        if hasattr(self, "cb_kind"):
            return str(self.cb_kind.currentData() or KIND_DESPESA)
        return KIND_DESPESA

    def _on_kind_changed(self) -> None:
        is_income = self.selected_kind() == KIND_RECEITA
        if hasattr(self, "seg_kind"):
            self.seg_kind.set_active(KIND_RECEITA if is_income else KIND_DESPESA, emit=False)
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
        self.cb_cartao.setVisible(is_card)
        self.cb_conta.setEnabled(not is_card)
        self.cb_conta.setVisible(not is_card)
        if hasattr(self, "lbl_source"):
            self.lbl_source.setText("Cartão de Crédito *" if is_card else "Conta Bancária *")
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
        self.setMinimumWidth(620)

        self._accounts = self.account_repo.list_accounts(profile_id)
        self._categories = self.cat_repo.list_categories("RECEITA", profile_id)
        self._tags = self.tag_repo.list_tags(profile_id)
        self._build_ui()
        if occurrence is not None:
            self._populate(occurrence)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Tipo de Lançamento (Receita vs Despesa) via SegmentedBar + cb_kind oculto p/ testes
        self.cb_kind = QComboBox()
        self.cb_kind.addItem(get_line_icon("arrow-up", color=INCOME_GREEN, size=16), "Receita", KIND_RECEITA)
        self.cb_kind.addItem(get_line_icon("arrow-down", color=EXPENSE_RED, size=16), "Despesa", KIND_DESPESA)
        self.cb_kind.setVisible(False)
        self.cb_kind.currentIndexChanged.connect(self._on_kind_changed)

        self.seg_kind = SegmentedBar(
            [(KIND_RECEITA, "Receita"), (KIND_DESPESA, "Despesa")],
            active_key=KIND_RECEITA,
        )
        self.seg_kind.changed.connect(self._on_segment_kind_changed)
        layout.addWidget(self.seg_kind)
        layout.addWidget(self.cb_kind)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        lbl_val = QLabel("Valor (R$) *")
        lbl_val.setObjectName("FormLabel")
        lbl_desc = QLabel("Descrição *")
        lbl_desc.setObjectName("FormLabel")
        grid.addWidget(lbl_val, 0, 0)
        grid.addWidget(lbl_desc, 0, 1)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(1000.00)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("Ex.: Salário, Dividendos, Reembolso...")
        grid.addWidget(self.sp_valor, 1, 0)
        grid.addWidget(self.ed_desc, 1, 1)

        lbl_acc = QLabel("Conta de Destino")
        lbl_acc.setObjectName("FormLabel")
        lbl_dt = QLabel("Data Prevista / Recebimento *")
        lbl_dt.setObjectName("FormLabel")
        grid.addWidget(lbl_acc, 2, 0)
        grid.addWidget(lbl_dt, 2, 1)

        self.cb_conta = QComboBox()
        for acc in self._accounts:
            self.cb_conta.addItem(acc.name, acc.id)

        self.dt_venc = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_venc.setCalendarPopup(True)
        self.dt_venc.setDisplayFormat("dd/MM/yyyy")
        grid.addWidget(self.cb_conta, 3, 0)
        grid.addWidget(self.dt_venc, 3, 1)

        lbl_cat = QLabel("Categoria")
        lbl_cat.setObjectName("FormLabel")
        lbl_sub = QLabel("Subcategoria")
        lbl_sub.setObjectName("FormLabel")
        grid.addWidget(lbl_cat, 4, 0)
        grid.addWidget(lbl_sub, 4, 1)

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
        grid.addWidget(self.cb_cat, 5, 0)
        grid.addWidget(self.cb_sub, 5, 1)

        lbl_rec = QLabel("Tipo de Lançamento / Recorrência")
        lbl_rec.setObjectName("FormLabel")
        lbl_st = QLabel("Status")
        lbl_st.setObjectName("FormLabel")
        grid.addWidget(lbl_rec, 6, 0)
        grid.addWidget(lbl_st, 6, 1)

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

        rec_row.addWidget(self.cb_rec, 1)
        rec_row.addWidget(self.sp_parcelas)
        grid.addLayout(rec_row, 7, 0)

        self.chk_recebido = QCheckBox("Já foi recebida / efetivada")
        grid.addWidget(self.chk_recebido, 7, 1)

        self.chk_val_parcela = QCheckBox("Valor já é de cada parcela")
        grid.addWidget(self.chk_val_parcela, 8, 0, 1, 2)

        row_idx = 9
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

            lbl_scope = QLabel("Escopo da Edição")
            lbl_scope.setObjectName("FormLabel")
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
            grid.addWidget(lbl_scope, row_idx, 0)
            grid.addWidget(self.cb_scope, row_idx, 1)
            row_idx += 1
        else:
            self._on_rec_changed()

        lbl_tags = QLabel("Tags")
        lbl_tags.setObjectName("FormLabel")
        lbl_obs = QLabel("Observações")
        lbl_obs.setObjectName("FormLabel")
        grid.addWidget(lbl_tags, row_idx, 0)
        grid.addWidget(lbl_obs, row_idx, 1)
        row_idx += 1

        self.list_tags = QListWidget()
        self.list_tags.setMaximumHeight(68)
        for t in self._tags:
            it = QListWidgetItem(
                create_color_badge_icon(t.color_hex, "#", size=16),
                t.name,
            )
            it.setData(Qt.ItemDataRole.UserRole, t.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self.list_tags.addItem(it)

        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Observações adicionais (opcional)")
        if self._tags:
            grid.addWidget(self.list_tags, row_idx, 0)
        else:
            self.list_tags.setVisible(False)
            lbl_no_tags = QLabel("Nenhuma tag cadastrada (Cadastros → Tags)")
            lbl_no_tags.setObjectName("MutedText")
            lbl_no_tags.setStyleSheet("font-size: 12px; padding: 6px 0;")
            grid.addWidget(lbl_no_tags, row_idx, 0)
        grid.addWidget(self.ed_obs, row_idx, 1, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(grid)

        sep = QFrame()
        sep.setObjectName("ModalSeparator")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

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

    def _on_segment_kind_changed(self, kind_key: str) -> None:
        idx = self.cb_kind.findData(kind_key)
        if idx >= 0 and self.cb_kind.currentIndex() != idx:
            self.cb_kind.setCurrentIndex(idx)

    def selected_kind(self) -> str:
        if hasattr(self, "cb_kind"):
            return str(self.cb_kind.currentData() or KIND_RECEITA)
        return KIND_RECEITA

    def _on_kind_changed(self) -> None:
        is_despesa = self.selected_kind() == KIND_DESPESA
        if hasattr(self, "seg_kind"):
            self.seg_kind.set_active(KIND_DESPESA if is_despesa else KIND_RECEITA, emit=False)
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
        self.setMinimumWidth(580)
        self._accounts = self.account_repo.list_accounts(profile_id)
        self._build_ui()
        if occurrence is not None:
            self._populate(occurrence)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        lbl_val = QLabel("Valor (R$) *")
        lbl_val.setObjectName("FormLabel")
        lbl_desc = QLabel("Descrição *")
        lbl_desc.setObjectName("FormLabel")
        grid.addWidget(lbl_val, 0, 0)
        grid.addWidget(lbl_desc, 0, 1)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(250.00)

        self.ed_desc = QLineEdit("Transferência entre contas")
        grid.addWidget(self.sp_valor, 1, 0)
        grid.addWidget(self.ed_desc, 1, 1)

        lbl_orig = QLabel("Conta de Origem (Saída) *")
        lbl_orig.setObjectName("FormLabel")
        lbl_dest = QLabel("Conta de Destino (Entrada) *")
        lbl_dest.setObjectName("FormLabel")
        grid.addWidget(lbl_orig, 2, 0)
        grid.addWidget(lbl_dest, 2, 1)

        self.cb_origem = QComboBox()
        self.cb_destino = QComboBox()
        for acc in self._accounts:
            self.cb_origem.addItem(acc.name, acc.id)
            self.cb_destino.addItem(acc.name, acc.id)
        if self.cb_destino.count() > 1:
            self.cb_destino.setCurrentIndex(1)
        grid.addWidget(self.cb_origem, 3, 0)
        grid.addWidget(self.cb_destino, 3, 1)

        lbl_dt = QLabel("Data da Transferência *")
        lbl_dt.setObjectName("FormLabel")
        lbl_rec = QLabel("Recorrência" if self.occurrence is None else "Escopo da Edição")
        lbl_rec.setObjectName("FormLabel")
        grid.addWidget(lbl_dt, 4, 0)
        grid.addWidget(lbl_rec, 4, 1)

        self.dt_venc = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_venc.setCalendarPopup(True)
        self.dt_venc.setDisplayFormat("dd/MM/yyyy")
        grid.addWidget(self.dt_venc, 5, 0)

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
            rec_row.addWidget(self.cb_rec, 1)
            rec_row.addWidget(self.sp_parcelas)
            grid.addLayout(rec_row, 5, 1)
        else:
            self.cb_scope = QComboBox()
            self.cb_scope.addItem("Somente esta ocorrência", "this")
            if self.occurrence.is_recurring:
                self.cb_scope.addItem("Toda a série", "all")
            grid.addWidget(self.cb_scope, 5, 1)

        lbl_st = QLabel("Situação")
        lbl_st.setObjectName("FormLabel")
        lbl_obs = QLabel("Observações")
        lbl_obs.setObjectName("FormLabel")
        grid.addWidget(lbl_st, 6, 0)
        grid.addWidget(lbl_obs, 6, 1)

        self.chk_efetivada = QCheckBox("Transferência já efetivada")
        self.chk_efetivada.setChecked(True)

        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Observações adicionais (opcional)")
        grid.addWidget(self.chk_efetivada, 7, 0)
        grid.addWidget(self.ed_obs, 7, 1)

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
        self.cat_repo = CategoryRepository(db)

        self._occurrences: List[Occurrence] = []
        self._category_filter: str = "ALL"
        self._view_mode: str = "feed"
        self._feed_cards: Dict[int, QFrame] = {}
        self.count_pills: Dict[str, QPushButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

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
        self.btn_new_card_exp = QPushButton("Cartão")
        self.btn_new_card_exp.setObjectName("SecondaryButton")
        self.btn_new_card_exp.setToolTip("Nova despesa no cartão de crédito")
        self.btn_new_card_exp.setIcon(get_line_icon("card", size=15))
        self.btn_new_card_exp.clicked.connect(lambda: self.open_new_expense_dialog(True))

        self.btn_new_income = QPushButton("Receita")
        self.btn_new_income.setObjectName("SecondaryButton")
        self.btn_new_income.setToolTip("Nova receita")
        self.btn_new_income.setIcon(get_line_icon("plus", size=15))
        self.btn_new_income.clicked.connect(self.open_new_income_dialog)

        self.btn_new_transfer = QPushButton("Transferência")
        self.btn_new_transfer.setObjectName("SecondaryButton")
        self.btn_new_transfer.setToolTip("Nova transferência entre contas")
        self.btn_new_transfer.setIcon(get_line_icon("swap", size=15))
        self.btn_new_transfer.clicked.connect(self.open_new_transfer_dialog)

        header_row.addWidget(self.btn_new_expense)
        header_row.addWidget(self.btn_new_card_exp)
        header_row.addWidget(self.btn_new_income)
        header_row.addWidget(self.btn_new_transfer)
        root.addLayout(header_row)

        # 2. Cards KPI Superiores com micro-ícone à direita e tint semântico
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.card_prev, self.lbl_prev_val, self.lbl_prev_sub = self._make_kpi_card(
            "Saldo Anterior", PRIMARY_BLUE, icon_name="wallet", tint=None
        )
        self.card_inc, self.lbl_inc_val, self.lbl_inc_sub = self._make_kpi_card(
            "Receitas", INCOME_GREEN, icon_name="arrow-up", tint="positive"
        )
        self.card_exp, self.lbl_exp_val, self.lbl_exp_sub = self._make_kpi_card(
            "Despesas", EXPENSE_RED, icon_name="arrow-down", tint="negative"
        )
        self.card_res, self.lbl_res_val, self.lbl_res_sub = self._make_kpi_card(
            "Resultado", PRIMARY_BLUE, icon_name="chart", tint="info"
        )
        kpi_row.addWidget(self.card_prev, 1)
        kpi_row.addWidget(self.card_inc, 1)
        kpi_row.addWidget(self.card_exp, 1)
        kpi_row.addWidget(self.card_res, 1)
        root.addLayout(kpi_row)

        # 3. Barra Única Compacta: Pílulas + Fonte + Modo (Feed/Tabela) + Filtros Avançados
        filter_bar = QFrame()
        filter_bar.setObjectName("CardSurface")
        f_lay = QHBoxLayout(filter_bar)
        f_lay.setContentsMargins(12, 8, 12, 8)
        f_lay.setSpacing(8)

        for p_key, p_label in (
            ("ALL", "Tudo"),
            (KIND_RECEITA, "Receitas"),
            (KIND_DESPESA, "Despesas"),
            (KIND_TRANSFERENCIA, "Transferências"),
        ):
            chip = QPushButton(f"{p_label} 0")
            chip.setObjectName("CountPillChip")
            chip.setProperty("active", p_key == "ALL")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, k=p_key: self._on_count_pill_clicked(k))
            f_lay.addWidget(chip)
            self.count_pills[p_key] = chip

        f_lay.addStretch()

        # Filtros internos mantidos para sincronização com pílulas e Filtros Avançados
        self.cb_filter_kind = QComboBox()
        self.cb_filter_kind.addItem("Todos os Tipos", "ALL")
        self.cb_filter_kind.addItem("Despesas", KIND_DESPESA)
        self.cb_filter_kind.addItem("Receitas", KIND_RECEITA)
        self.cb_filter_kind.addItem("Transferências", KIND_TRANSFERENCIA)
        self.cb_filter_kind.currentIndexChanged.connect(lambda _: self.refresh_data())
        self.cb_filter_kind.setVisible(False)

        self.cb_filter_source = QComboBox()
        self.cb_filter_source.setMinimumWidth(210)
        self.cb_filter_source.currentIndexChanged.connect(lambda _: self.refresh_data())
        f_lay.addWidget(self.cb_filter_source)

        self.cb_filter_status = QComboBox()
        self.cb_filter_status.addItem("Qualquer Situação", "ALL")
        self.cb_filter_status.addItem("Confirmadas / Efetivadas", "EFFECTIVE")
        self.cb_filter_status.addItem("Pendentes / Em Aberto", "PENDING")
        self.cb_filter_status.currentIndexChanged.connect(lambda _: self.refresh_data())
        self.cb_filter_status.setVisible(False)

        self.lbl_count_badge = QLabel("0 lançamentos")
        self.lbl_count_badge.setObjectName("MutedText")
        self.lbl_count_badge.setStyleSheet("font-size: 12px; font-weight: 500; padding: 0 4px;")
        f_lay.addWidget(self.lbl_count_badge)

        self.seg_view_mode = SegmentedBar(
            [("feed", "Feed por Data"), ("table", "Tabela")],
            active_key="feed",
        )
        self.seg_view_mode.changed.connect(self.set_view_mode)
        f_lay.addWidget(self.seg_view_mode)

        self.btn_adv_filters = QPushButton("Filtros")
        self.btn_adv_filters.setObjectName("SecondaryButton")
        self.btn_adv_filters.setToolTip("Filtros Avançados")
        self.btn_adv_filters.setIcon(get_line_icon("filter", size=15))
        self.btn_adv_filters.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_adv_filters.clicked.connect(self.open_advanced_filters_drawer)
        f_lay.addWidget(self.btn_adv_filters)
        root.addWidget(filter_bar)

        # 4. Área Principal (Tabela / Feed Agrupado à esquerda + Drawers Laterais à direita)
        body_h = QHBoxLayout()
        body_h.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)

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
        self.table.verticalHeader().setDefaultSectionSize(44)
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
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 136)
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

        # Feed Agrupado por Data (Estilo Artha)
        self.feed_scroll = QScrollArea()
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.feed_host = QWidget()
        self.feed_layout = QVBoxLayout(self.feed_host)
        self.feed_layout.setContentsMargins(0, 2, 4, 8)
        self.feed_layout.setSpacing(8)
        self.feed_layout.addStretch()
        self.feed_scroll.setWidget(self.feed_host)
        self.stack.addWidget(self.feed_scroll)

        self.empty_widget = EmptyStateWidget(
            title="Nenhum lançamento no período",
            subtitle="Não há receitas, despesas ou transferências registradas para os filtros selecionados.",
            icon_name="list",
            action_text="+ Nova Despesa",
            action_callback=lambda: self.open_new_expense_dialog(False),
        )
        self.stack.addWidget(self.empty_widget)

        left_col.addWidget(self.stack, stretch=1)

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
        left_col.addLayout(act_bar)

        body_h.addLayout(left_col, stretch=1)

        # Drawers Laterais Direitos
        self.filter_drawer = SideDrawer(
            title="Filtros Avançados",
            subtitle="Configure regime, situação, conta e categoria",
            width=336,
            parent=self,
        )
        self._build_filter_drawer_content()
        body_h.addWidget(self.filter_drawer)

        self.installment_drawer = SideDrawer(
            title="Detalhe da Série Parcelada",
            subtitle="",
            width=404,
            parent=self,
        )
        body_h.addWidget(self.installment_drawer)

        root.addLayout(body_h, stretch=1)

    def _make_kpi_card(
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
        has_sel = self.table.currentRow() >= 0 and len(self._occurrences) > 0
        self.btn_toggle_eff.setEnabled(has_sel)
        self.btn_edit.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _on_count_pill_clicked(self, kind_key: str) -> None:
        idx = self.cb_filter_kind.findData(kind_key)
        if idx >= 0:
            self.cb_filter_kind.setCurrentIndex(idx)

    def _update_count_pills(self, all_occs: List[Occurrence], active_kind: str) -> None:
        counts = {
            "ALL": len(all_occs),
            KIND_RECEITA: sum(1 for o in all_occs if o.kind == KIND_RECEITA),
            KIND_DESPESA: sum(1 for o in all_occs if o.kind == KIND_DESPESA),
            KIND_TRANSFERENCIA: sum(1 for o in all_occs if o.kind == KIND_TRANSFERENCIA),
        }
        labels = {
            "ALL": "Tudo",
            KIND_RECEITA: "Receitas",
            KIND_DESPESA: "Despesas",
            KIND_TRANSFERENCIA: "Transferências",
        }
        for key, btn in self.count_pills.items():
            btn.setText(f"{labels[key]} {counts[key]}")
            btn.setProperty("active", key == active_kind)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_view_mode(self, mode: str) -> None:
        self._view_mode = "feed" if mode == "feed" else "table"
        if hasattr(self, "seg_view_mode"):
            self.seg_view_mode.set_active(self._view_mode, emit=False)
        self._sync_active_list_widget()

    def _sync_active_list_widget(self) -> None:
        if not self._occurrences:
            self.stack.setCurrentWidget(self.empty_widget)
        elif self._view_mode == "feed":
            self.stack.setCurrentWidget(self.feed_scroll)
        else:
            self.stack.setCurrentWidget(self.table)

    # ------------------------------------------------------------------ #
    # Drawers Laterais: Filtros Avançados & Detalhe de Parcelas
    # ------------------------------------------------------------------ #
    def _build_filter_drawer_content(self) -> None:
        lay = self.filter_drawer.body_layout

        # 1. Regime de Visualização
        lbl_reg = QLabel("Regime de Visualização")
        lbl_reg.setObjectName("FormLabel")
        lay.insertWidget(lay.count() - 1, lbl_reg)

        self._drawer_regime_group = QButtonGroup(self.filter_drawer)
        self._rb_reg_comp = QRadioButton("Competência (Data da Transação)")
        self._rb_reg_caixa = QRadioButton("Caixa (Vencimento / Fatura)")
        self._rb_reg_eff = QRadioButton("Efetivação (Pago / Recebido)")
        for rb in (self._rb_reg_comp, self._rb_reg_caixa, self._rb_reg_eff):
            self._drawer_regime_group.addButton(rb)
            lay.insertWidget(lay.count() - 1, rb)

        lbl_reg_hint = QLabel("Competência usa a data da compra; Caixa usa a data de vencimento.")
        lbl_reg_hint.setObjectName("MutedText")
        lbl_reg_hint.setWordWrap(True)
        lay.insertWidget(lay.count() - 1, lbl_reg_hint)

        # 2. Situação
        lbl_st = QLabel("Status")
        lbl_st.setObjectName("FormLabel")
        lay.insertWidget(lay.count() - 1, lbl_st)

        st_row = QHBoxLayout()
        self._chk_adv_paid = QCheckBox("Pagos / Efetivados")
        self._chk_adv_pend = QCheckBox("Pendentes")
        self._chk_adv_paid.setChecked(True)
        self._chk_adv_pend.setChecked(True)
        st_row.addWidget(self._chk_adv_paid)
        st_row.addWidget(self._chk_adv_pend)
        lay.insertLayout(lay.count() - 1, st_row)

        # 3. Conta / Cartão
        lbl_src = QLabel("Conta Bancária / Cartão")
        lbl_src.setObjectName("FormLabel")
        self._cb_adv_source = QComboBox()
        lay.insertWidget(lay.count() - 1, lbl_src)
        lay.insertWidget(lay.count() - 1, self._cb_adv_source)

        # 4. Categoria
        lbl_cat = QLabel("Categoria")
        lbl_cat.setObjectName("FormLabel")
        self._cb_adv_cat = QComboBox()
        lay.insertWidget(lay.count() - 1, lbl_cat)
        lay.insertWidget(lay.count() - 1, self._cb_adv_cat)

        # Rodapé: Limpar + Aplicar
        btn_clear = QPushButton("Limpar")
        btn_clear.setObjectName("SecondaryButton")
        btn_clear.setIcon(get_line_icon("x", size=14))
        btn_clear.clicked.connect(self._clear_advanced_filters)

        btn_apply = QPushButton("Aplicar Filtros")
        btn_apply.setObjectName("PrimaryButton")
        btn_apply.clicked.connect(self._apply_advanced_filters)

        self.filter_drawer.footer_layout.addWidget(btn_clear)
        self.filter_drawer.footer_layout.addWidget(btn_apply, 1)

    def open_advanced_filters_drawer(self) -> None:
        self.installment_drawer.setVisible(False)
        profile_id, _, _, _ = self.get_context()

        cur_mode = self.db.settings.date_reference_mode
        if cur_mode in (DateReferenceMode.LANCAMENTO.value, DateReferenceMode.LANCAMENTO_DISTRIBUIR.value):
            self._rb_reg_comp.setChecked(True)
        elif cur_mode == DateReferenceMode.EFETIVACAO.value:
            self._rb_reg_eff.setChecked(True)
        else:
            self._rb_reg_caixa.setChecked(True)

        st = str(self.cb_filter_status.currentData() or "ALL")
        self._chk_adv_paid.setChecked(st in ("ALL", "EFFECTIVE"))
        self._chk_adv_pend.setChecked(st in ("ALL", "PENDING"))

        self._cb_adv_source.clear()
        for i in range(self.cb_filter_source.count()):
            self._cb_adv_source.addItem(
                self.cb_filter_source.itemText(i), self.cb_filter_source.itemData(i)
            )
        idx_s = self._cb_adv_source.findData(self.cb_filter_source.currentData())
        if idx_s >= 0:
            self._cb_adv_source.setCurrentIndex(idx_s)

        self._cb_adv_cat.clear()
        self._cb_adv_cat.addItem("Todas as Categorias", "ALL")
        seen_cats = set()
        for cat_kind in (KIND_DESPESA, KIND_RECEITA):
            for c in self.cat_repo.list_categories(cat_kind, profile_id):
                if c.id not in seen_cats:
                    seen_cats.add(c.id)
                    self._cb_adv_cat.addItem(
                        create_color_badge_icon(c.color_hex, c.name[:1], size=16),
                        c.name,
                        c.id,
                    )
        idx_c = self._cb_adv_cat.findData(self._category_filter)
        self._cb_adv_cat.setCurrentIndex(idx_c if idx_c >= 0 else 0)

        self.filter_drawer.open_drawer()

    def _clear_advanced_filters(self) -> None:
        self._category_filter = "ALL"
        self.cb_filter_kind.blockSignals(True)
        self.cb_filter_kind.setCurrentIndex(0)
        self.cb_filter_kind.blockSignals(False)
        self.cb_filter_status.blockSignals(True)
        self.cb_filter_status.setCurrentIndex(0)
        self.cb_filter_status.blockSignals(False)
        idx_all = self.cb_filter_source.findData("ALL")
        if idx_all >= 0:
            self.cb_filter_source.blockSignals(True)
            self.cb_filter_source.setCurrentIndex(idx_all)
            self.cb_filter_source.blockSignals(False)
        self.filter_drawer.close_drawer()
        self.refresh_data()

    def _apply_advanced_filters(self) -> None:
        new_mode = DateReferenceMode.VENCIMENTO.value
        if self._rb_reg_comp.isChecked():
            new_mode = DateReferenceMode.LANCAMENTO.value
        elif self._rb_reg_eff.isChecked():
            new_mode = DateReferenceMode.EFETIVACAO.value

        mode_changed = new_mode != self.db.settings.date_reference_mode
        if mode_changed:
            self.db.settings.date_reference_mode = new_mode
            self.db.settings.save()

        paid = self._chk_adv_paid.isChecked()
        pend = self._chk_adv_pend.isChecked()
        target_st = "EFFECTIVE" if (paid and not pend) else ("PENDING" if (pend and not paid) else "ALL")
        idx_st = self.cb_filter_status.findData(target_st)
        if idx_st >= 0:
            self.cb_filter_status.blockSignals(True)
            self.cb_filter_status.setCurrentIndex(idx_st)
            self.cb_filter_status.blockSignals(False)

        src_data = self._cb_adv_source.currentData()
        idx_src = self.cb_filter_source.findData(src_data)
        if idx_src >= 0:
            self.cb_filter_source.blockSignals(True)
            self.cb_filter_source.setCurrentIndex(idx_src)
            self.cb_filter_source.blockSignals(False)

        self._category_filter = str(self._cb_adv_cat.currentData() or "ALL")
        self.filter_drawer.close_drawer()
        if mode_changed:
            self.on_data_mutated()
        self.refresh_data()

    def _navigate_to_cards(self) -> None:
        w = self.parent()
        while w is not None:
            if hasattr(w, "navigate_to"):
                w.navigate_to("cartoes")
                return
            w = w.parent()

    def open_installment_drawer(self, occ: Occurrence) -> None:
        """Abre o drawer lateral com anel de progresso e timeline vertical das parcelas."""
        self.filter_drawer.setVisible(False)
        series = self.tx_service.list_installment_series(occ)
        if not series:
            return

        total_n = max(occ.num_parcelas, len(series))
        eyebrow = f"{'COMPRA' if occ.kind == KIND_DESPESA else 'RECEITA'} PARCELADA · {total_n}×"
        source_txt = occ.cartao_nome or occ.conta_nome or ""
        self.installment_drawer.set_header(occ.descricao, source_txt, eyebrow=eyebrow)
        self.installment_drawer.clear_body()

        # Limpa botões antigos do rodapé do drawer
        while self.installment_drawer.footer_layout.count():
            it = self.installment_drawer.footer_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        lay = self.installment_drawer.body_layout

        # Bloco superior: DonutProgressRing + Resumo numérico
        top_card = QFrame()
        top_card.setObjectName("CardSurface")
        top_h = QHBoxLayout(top_card)
        top_h.setContentsMargins(14, 14, 14, 14)
        top_h.setSpacing(14)

        accent_hex = PRIMARY_BLUE if occ.kind == KIND_DESPESA else INCOME_GREEN
        ring = DonutProgressRing(size=92)
        ring.set_progress(occ.num_parcela, total_n, subtitle="parcela atual", accent_hex=accent_hex)
        top_h.addWidget(ring)

        paid_items = [s for s in series if s["efetivada"] or s["num_parcela"] < occ.num_parcela]
        rem_items = [s for s in series if s not in paid_items]
        total_sum = sum(s["valor"] for s in series)
        paid_sum = sum(s["valor"] for s in paid_items)
        rem_sum = sum(s["valor"] for s in rem_items)
        last_dt = series[-1]["data_vencimento"]
        last_str = (
            f"até {PT_BR_MONTHS.get(last_dt.month, '')[:3].lower()}/{str(last_dt.year)[-2:]}"
            if last_dt
            else ""
        )

        stats_grid = QGridLayout()
        stats_grid.setVerticalSpacing(6)
        stats_grid.setHorizontalSpacing(10)

        def _add_stat(r_idx: int, label_txt: str, val_txt: str, sub_txt: str = "", val_color: str = "") -> None:
            l_col = QVBoxLayout()
            l_col.setSpacing(0)
            l1 = QLabel(label_txt)
            l1.setObjectName("MutedText")
            l1.setStyleSheet("font-size: 11px;")
            l_col.addWidget(l1)
            if sub_txt:
                l2 = QLabel(sub_txt)
                l2.setObjectName("MutedText")
                l2.setStyleSheet("font-size: 10px;")
                l_col.addWidget(l2)
            v_lbl = QLabel(val_txt)
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            v_lbl.setStyleSheet(
                f"font-size: 13px; font-weight: 700; {f'color: {val_color};' if val_color else ''}"
            )
            stats_grid.addLayout(l_col, r_idx, 0)
            stats_grid.addWidget(v_lbl, r_idx, 1)

        _add_stat(0, "Total", format_currency(total_sum), f"{total_n}× {format_currency(occ.valor)}")
        _add_stat(
            1,
            "Já cobrado",
            format_currency(paid_sum),
            f"{len(paid_items)} parcela(s)",
            accent_hex,
        )
        _add_stat(2, "Falta", format_currency(rem_sum), last_str)
        top_h.addLayout(stats_grid, 1)
        lay.insertWidget(lay.count() - 1, top_card)

        # Timeline Vertical das Parcelas
        lbl_tl = QLabel("CRONOGRAMA DAS PARCELAS")
        lbl_tl.setObjectName("MutedText")
        lbl_tl.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 0.06em;")
        lay.insertWidget(lay.count() - 1, lbl_tl)

        for item in series:
            n_cur = int(item["num_parcela"])
            is_cur = item["id"] == occ.id or n_cur == occ.num_parcela
            dt: Optional[date] = item["data_vencimento"]
            mon_lbl = PT_BR_MONTHS.get(dt.month, "")[:3] if dt else "—"
            yr_lbl = str(dt.year) if dt else ""

            row_card = QFrame()
            row_card.setObjectName("TimelineItemCard")
            row_card.setProperty("current", is_cur)
            rh = QHBoxLayout(row_card)
            rh.setContentsMargins(10, 8, 10, 8)
            rh.setSpacing(10)

            dt_col = QVBoxLayout()
            dt_col.setSpacing(1)
            lbl_m = QLabel(f"{mon_lbl}/{yr_lbl[-2:]}" if yr_lbl else mon_lbl)
            lbl_m.setStyleSheet("font-size: 11px; font-weight: 700;")
            lbl_d = QLabel(dt.strftime("%d/%m") if dt else "—")
            lbl_d.setObjectName("MutedText")
            lbl_d.setStyleSheet("font-size: 10px;")
            dt_col.addWidget(lbl_m)
            dt_col.addWidget(lbl_d)
            rh.addLayout(dt_col)

            mid_col = QVBoxLayout()
            mid_col.setSpacing(1)
            lbl_p = QLabel(f"Parcela {n_cur}/{total_n}")
            lbl_p.setStyleSheet("font-size: 12px; font-weight: 600;")
            lbl_s = QLabel(f"Vencimento {format_date_br(dt.isoformat())}" if dt else "")
            lbl_s.setObjectName("MutedText")
            lbl_s.setStyleSheet("font-size: 10px;")
            mid_col.addWidget(lbl_p)
            mid_col.addWidget(lbl_s)
            rh.addLayout(mid_col, 1)

            right_col = QVBoxLayout()
            right_col.setSpacing(3)
            right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_v = QLabel(format_currency(item["valor"]))
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignRight)
            lbl_v.setStyleSheet("font-size: 12px; font-weight: 700;")
            right_col.addWidget(lbl_v)

            if is_cur:
                tag = QLabel("FATURA ATUAL" if occ.is_card else "PARCELA ATUAL")
                tag.setObjectName("TimelineTagCurrent")
            elif item["efetivada"] or n_cur < occ.num_parcela:
                tag = QLabel("COBRADA" if occ.is_card else "PAGA")
                tag.setObjectName("TimelineTagPaid")
            else:
                tag = QLabel("PREVISTA")
                tag.setObjectName("TimelineTagFuture")
            tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tag.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            right_col.addWidget(tag, 0, Qt.AlignmentFlag.AlignRight)
            rh.addLayout(right_col)

            lay.insertWidget(lay.count() - 1, row_card)

        if occ.is_card:
            btn_open_bill = QPushButton("Abrir fatura no módulo Cartões")
            btn_open_bill.setObjectName("PrimaryButton")
            btn_open_bill.clicked.connect(self._navigate_to_cards)
            self.installment_drawer.footer_layout.addWidget(btn_open_bill, 1)

        self.installment_drawer.open_drawer()

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

        if occ.is_installment:
            act_parc = menu.addAction(
                get_line_icon("card", size=16), "Ver Detalhes das Parcelas"
            )
            act_parc.triggered.connect(lambda: self.open_installment_drawer(occ))

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

        accounts = self.account_repo.list_accounts(profile_id)
        cards = self.card_service.list_cards(profile_id)

        # Encontra a Conta Corrente prioritária (ou primeira conta bancária ativa)
        primary_acc = None
        other_accounts = []
        for acc in accounts:
            if primary_acc is None and "corrente" in acc.name.lower():
                primary_acc = acc
            else:
                other_accounts.append(acc)
        if primary_acc is None and other_accounts:
            primary_acc = other_accounts.pop(0)

        # 1. Primeira Opção e Padrão: Conta Corrente
        if primary_acc:
            self.cb_filter_source.addItem(f"Conta: {primary_acc.name}", f"ACC:{primary_acc.id}")

        # 2. Visões Agrupadas
        self.cb_filter_source.addItem("Todas as Contas e Cartões", "ALL")
        self.cb_filter_source.addItem("Apenas Contas Bancárias (Caixa)", "ACCOUNTS_ONLY")

        # 3. Demais Contas Bancárias
        for acc in other_accounts:
            self.cb_filter_source.addItem(f"Conta: {acc.name}", f"ACC:{acc.id}")

        # 4. Cartões de Crédito
        for card in cards:
            self.cb_filter_source.addItem(f"Cartão: {card.nome}", f"CARD:{card.id}")

        idx = -1
        if current_data is not None:
            idx = self.cb_filter_source.findData(current_data)

        if idx >= 0:
            self.cb_filter_source.setCurrentIndex(idx)
        else:
            self.cb_filter_source.setCurrentIndex(0)

        self.cb_filter_source.blockSignals(False)

    def refresh_data(self) -> None:
        profile_id, month, year, search_text = self.get_context()
        self._reload_source_combo(profile_id)

        mode = self.db.settings.date_reference_mode
        kind_filter = str(self.cb_filter_kind.currentData() or "ALL")

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

        all_for_pills = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            kinds=list(ALL_KINDS),
            id_conta=id_conta,
            id_cartao=id_cartao,
            source=source,
            search=search_text,
            only_effective=only_effective,
            profile_id=profile_id,
        )
        if self._category_filter != "ALL":
            all_for_pills = [
                o for o in all_for_pills if str(o.id_categoria or "") == self._category_filter
            ]

        self._update_count_pills(all_for_pills, kind_filter)
        if kind_filter == "ALL":
            self._occurrences = all_for_pills
        else:
            self._occurrences = [o for o in all_for_pills if o.kind == kind_filter]

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
            f"color: {INCOME_GREEN if res_val >= 0 else EXPENSE_RED}; font-size: 22px; font-weight: 700;"
        )
        self.lbl_res_sub.setText(
            f"Saldo Previsto: {format_currency(saldo_prev)}"
        )

        self.lbl_count_badge.setText(f"{len(self._occurrences)} lançamentos")
        self._populate_table()
        self._populate_feed()
        self._sync_active_list_widget()

    def _populate_table(self) -> None:
        if not self._occurrences:
            self.table.setRowCount(0)
            self._sync_active_list_widget()
            self._on_selection_changed()
            return

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

            # 2: Parcela (com InstallmentMiniBar clicável quando parcelado; texto vazio evita sobreposição)
            parc_label = occ.parcela_label if occ.parcela_label else "—"
            it_rec = QTableWidgetItem("" if occ.is_installment else parc_label)
            it_rec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if occ.is_installment:
                it_rec.setToolTip(f"Parcela {parc_label}")
            elif parc_label == "—" or parc_label == "Única":
                it_rec.setForeground(QColor("#7B8190"))
            self.table.setItem(row_idx, 2, it_rec)

            if occ.is_installment:
                mini = InstallmentMiniBar(
                    occ.num_parcela,
                    occ.num_parcelas,
                    accent_hex=PRIMARY_BLUE if occ.kind == KIND_DESPESA else INCOME_GREEN,
                )
                mini.clicked.connect(lambda o=occ: self.open_installment_drawer(o))
                wrap = QWidget()
                wl = QHBoxLayout(wrap)
                wl.setContentsMargins(2, 0, 2, 0)
                wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                wl.addWidget(mini)
                self.table.setCellWidget(row_idx, 2, wrap)

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

    def _select_feed_row(self, row_idx: int) -> None:
        self.table.selectRow(row_idx)
        for idx, card in self._feed_cards.items():
            is_sel = idx == row_idx
            card.setProperty("selected", is_sel)
            card.style().unpolish(card)
            card.style().polish(card)
        self._on_selection_changed()

    def _populate_feed(self) -> None:
        while self.feed_layout.count() > 1:
            it = self.feed_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._feed_cards.clear()

        if not self._occurrences:
            return

        weekdays = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
        today = date.today()
        groups: List[Tuple[date, List[Tuple[int, Occurrence]]]] = []
        by_date: Dict[date, List[Tuple[int, Occurrence]]] = {}
        for idx, occ in enumerate(self._occurrences):
            if occ.ref_date not in by_date:
                by_date[occ.ref_date] = []
                groups.append((occ.ref_date, by_date[occ.ref_date]))
            by_date[occ.ref_date].append((idx, occ))

        for grp_dt, entries in groups:
            prefix = "Hoje · " if grp_dt == today else ""
            wk = weekdays[grp_dt.weekday()]
            day_net = sum(o.signed_total for _, o in entries)

            hdr_frame = QFrame()
            hdr_frame.setObjectName("FeedDateHeader")
            hh = QHBoxLayout(hdr_frame)
            hh.setContentsMargins(12, 6, 12, 6)
            lbl_dt = QLabel(f"{prefix}{grp_dt.strftime('%d/%m')} · {wk}")
            lbl_dt.setStyleSheet("font-size: 12px; font-weight: 700;")
            lbl_net = QLabel(format_currency(day_net))
            lbl_net.setStyleSheet(
                f"font-size: 12px; font-weight: 700; color: {INCOME_GREEN if day_net >= 0 else EXPENSE_RED};"
            )
            hh.addWidget(lbl_dt)
            hh.addStretch()
            hh.addWidget(lbl_net)
            self.feed_layout.insertWidget(self.feed_layout.count() - 1, hdr_frame)

            for row_idx, occ in entries:
                card = QFrame()
                card.setObjectName("FeedRowCard")
                card.setProperty("selected", row_idx == self.table.currentRow())
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.mousePressEvent = lambda ev, r=row_idx: self._select_feed_row(r)  # type: ignore[method-assign]
                card.mouseDoubleClickEvent = lambda ev, r=row_idx: (  # type: ignore[method-assign]
                    self._select_feed_row(r),
                    self.edit_selected_occurrence(),
                )

                ch = QHBoxLayout(card)
                ch.setContentsMargins(14, 10, 14, 10)
                ch.setSpacing(12)

                # Ícone circular à esquerda
                ico_lbl = QLabel()
                ico_lbl.setFixedSize(34, 34)
                ico_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if occ.kind == KIND_TRANSFERENCIA:
                    ico_lbl.setPixmap(get_line_pixmap("swap", color=TRANSFER_AMBER, size=18))
                else:
                    cat_col = occ.categoria_cor or "#5C6BC0"
                    initial = (occ.categoria_nome[:1] if occ.categoria_nome else "•").upper()
                    ico_lbl.setPixmap(create_color_badge_icon(cat_col, initial, size=28).pixmap(28, 28))
                ch.addWidget(ico_lbl)

                # Bloco central: Descrição + Categoria + Parcela + Subtítulo conta/cartão
                mid = QVBoxLayout()
                mid.setSpacing(3)

                top_line = QHBoxLayout()
                top_line.setSpacing(8)
                lbl_d = QLabel(occ.descricao)
                lbl_d.setStyleSheet("font-size: 13px; font-weight: 600;")
                top_line.addWidget(lbl_d)

                if occ.kind == KIND_TRANSFERENCIA:
                    top_line.addWidget(Badge("Transferência", variant="info"))
                elif occ.categoria_nome:
                    cat_str = (
                        f"{occ.categoria_nome} ▸ {occ.subcategoria_nome}"
                        if occ.subcategoria_nome
                        else occ.categoria_nome
                    )
                    top_line.addWidget(Badge(cat_str, variant="default"))
                else:
                    top_line.addWidget(Badge("Sem categoria", variant="warning"))

                if occ.is_installment:
                    mini = InstallmentMiniBar(
                        occ.num_parcela,
                        occ.num_parcelas,
                        accent_hex=PRIMARY_BLUE if occ.kind == KIND_DESPESA else INCOME_GREEN,
                    )
                    mini.clicked.connect(lambda o=occ: self.open_installment_drawer(o))
                    top_line.addWidget(mini)
                elif occ.is_fixed:
                    top_line.addWidget(Badge("Fixa", variant="default"))

                top_line.addStretch()
                mid.addLayout(top_line)

                src_txt = (
                    f"{occ.conta_nome} → {occ.conta_destino_nome}"
                    if occ.kind == KIND_TRANSFERENCIA
                    else (occ.cartao_nome or occ.conta_nome or "—")
                )
                tags_suffix = (
                    " · " + ", ".join(f"#{n}" for _, n, _ in occ.tags) if occ.tags else ""
                )
                lbl_sub = QLabel(f"{src_txt}{tags_suffix}")
                lbl_sub.setObjectName("MutedText")
                lbl_sub.setStyleSheet("font-size: 11px;")
                mid.addWidget(lbl_sub)
                ch.addLayout(mid, 1)

                # Direita: Valor tabulado + Status pill
                right_col = QVBoxLayout()
                right_col.setSpacing(3)
                right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                sign = "+ " if occ.kind == KIND_RECEITA else ("− " if occ.kind == KIND_DESPESA else "")
                v_col = INCOME_GREEN if occ.kind == KIND_RECEITA else (EXPENSE_RED if occ.kind == KIND_DESPESA else TRANSFER_AMBER)
                lbl_val = QLabel(f"{sign}{format_currency(occ.total)}")
                lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight)
                lbl_val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {v_col};")
                right_col.addWidget(lbl_val)

                st_txt = "Efetivado" if occ.efetivada else "Pendente"
                right_col.addWidget(
                    Badge(st_txt, variant="success" if occ.efetivada else "warning"),
                    0,
                    Qt.AlignmentFlag.AlignRight,
                )
                ch.addLayout(right_col)

                self._feed_cards[row_idx] = card
                self.feed_layout.insertWidget(self.feed_layout.count() - 1, card)

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
