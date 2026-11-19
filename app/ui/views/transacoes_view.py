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
    QToolButton,
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
    FilterCountPill,
    InstallmentMiniBar,
    KpiCard,
    SegmentedBar,
    SideDrawer,
    TimelineStepMarker,
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


class UnifiedTransactionDialog(QDialog):
    """Modal único compacto estilo Artha para Receita, Despesa (Conta/Cartão) e Transferência."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        default_date: date,
        initial_kind: str = KIND_DESPESA,
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
        self.card_mode = card_mode
        self.preselect_card_id = preselect_card_id
        self.custom_splits: List[SplitDTO] = []

        self.account_repo = AccountRepository(db)
        self.card_service = CreditCardService(db, TransactionService(db))
        self.cat_repo = CategoryRepository(db)
        self.tag_repo = TagRepository(db)

        self._accounts = self.account_repo.list_accounts(profile_id)
        self._cards = self.card_service.list_cards(profile_id)
        self._tags = self.tag_repo.list_tags(profile_id)

        start_kind = occurrence.kind if occurrence is not None else initial_kind
        self._kind: str = start_kind if start_kind in (KIND_RECEITA, KIND_DESPESA, KIND_TRANSFERENCIA) else KIND_DESPESA

        self.setWindowTitle("Editar Lançamento" if occurrence is not None else "Novo Lançamento")
        self.setMinimumWidth(470)
        self.setMaximumWidth(520)

        self._build_ui()
        if occurrence is not None:
            self._populate(occurrence)
        else:
            self._set_kind(self._kind)

    def _build_ui(self) -> None:
        from app.config.theme_palette import ThemePalette

        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # Barra segmentada superior: Receita | Despesa | Transferência
        seg_box = QFrame()
        seg_box.setStyleSheet(
            f"QFrame {{ background-color: {pal.app_background}; border: 1px solid {pal.border_subtle}; border-radius: 10px; }}"
        )
        seg_lay = QHBoxLayout(seg_box)
        seg_lay.setContentsMargins(4, 4, 4, 4)
        seg_lay.setSpacing(4)

        self._kind_btns: Dict[str, QPushButton] = {}
        self._kind_group = QButtonGroup(self)
        self._kind_group.setExclusive(True)
        for k_key, k_label, k_ico in (
            (KIND_RECEITA, "Receita", "arrow-up"),
            (KIND_DESPESA, "Despesa", "arrow-down"),
            (KIND_TRANSFERENCIA, "Transferência", "swap"),
        ):
            b = QPushButton(k_label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIcon(get_line_icon(k_ico, size=14))
            b.setFixedHeight(32)
            b.clicked.connect(lambda _=False, kk=k_key: self._set_kind(kk))
            self._kind_group.addButton(b)
            self._kind_btns[k_key] = b
            seg_lay.addWidget(b, 1)
        root.addWidget(seg_box)

        # Forma de pagamento (Despesa: Conta Bancária vs Cartão de Crédito)
        self.pay_mode_widget = QWidget()
        pm_lay = QVBoxLayout(self.pay_mode_widget)
        pm_lay.setContentsMargins(0, 2, 0, 0)
        pm_lay.setSpacing(6)
        lbl_pm = QLabel("Forma de Pagamento")
        lbl_pm.setObjectName("FormLabel")
        pm_row = QHBoxLayout()
        pm_row.setSpacing(16)
        self.rb_conta = QRadioButton("Conta Bancária")
        self.rb_conta.setIcon(get_line_icon("bank", size=14))
        self.rb_cartao = QRadioButton("Cartão de Crédito")
        self.rb_cartao.setIcon(get_line_icon("card", size=14))
        if self.card_mode and self._cards:
            self.rb_cartao.setChecked(True)
        else:
            self.rb_conta.setChecked(True)
        self.rb_conta.toggled.connect(self._on_pay_mode_changed)
        pm_row.addWidget(self.rb_conta)
        pm_row.addWidget(self.rb_cartao)
        pm_row.addStretch()
        pm_lay.addWidget(lbl_pm)
        pm_lay.addLayout(pm_row)
        root.addWidget(self.pay_mode_widget)

        # Valor em destaque (largura total)
        lbl_val = QLabel("Valor *")
        lbl_val.setObjectName("FormLabel")
        root.addWidget(lbl_val)
        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(0.01 if self.occurrence else 50.00)
        self.sp_valor.setMinimumHeight(42)
        self.sp_valor.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(self.sp_valor)

        # Grid 2 colunas para Datas, Descrição/Categoria, Origem/Destino, Conta/Status
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.lbl_dt_evt = QLabel("Data Lançamento *")
        self.lbl_dt_evt.setObjectName("FormLabel")
        self.lbl_dt_venc = QLabel("Data Vencimento *")
        self.lbl_dt_venc.setObjectName("FormLabel")
        grid.addWidget(self.lbl_dt_evt, 0, 0)
        grid.addWidget(self.lbl_dt_venc, 0, 1)

        self.dt_evento = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_evento.setCalendarPopup(True)
        self.dt_evento.setDisplayFormat("dd/MM/yyyy")

        self.dt_venc = QDateEdit(_py_to_qdate(self.default_date))
        self.dt_venc.setCalendarPopup(True)
        self.dt_venc.setDisplayFormat("dd/MM/yyyy")
        grid.addWidget(self.dt_evento, 1, 0)
        grid.addWidget(self.dt_venc, 1, 1)

        self.lbl_desc = QLabel("Descrição *")
        self.lbl_desc.setObjectName("FormLabel")
        self.lbl_cat = QLabel("Categoria")
        self.lbl_cat.setObjectName("FormLabel")
        grid.addWidget(self.lbl_desc, 2, 0)
        grid.addWidget(self.lbl_cat, 2, 1)

        self.ed_desc = QLineEdit()
        self.ed_desc.setPlaceholderText("Ex: Almoço, Uber, Freelance...")
        self.cb_cat = QComboBox()
        self.cb_cat.currentIndexChanged.connect(self._on_cat_changed)
        grid.addWidget(self.ed_desc, 3, 0)
        grid.addWidget(self.cb_cat, 3, 1)

        # Linha Origem / Destino (apenas Transferência)
        self.lbl_orig = QLabel("Conta de Origem *")
        self.lbl_orig.setObjectName("FormLabel")
        self.lbl_dest = QLabel("Conta de Destino *")
        self.lbl_dest.setObjectName("FormLabel")
        self.cb_origem = QComboBox()
        self.cb_destino = QComboBox()
        for acc in self._accounts:
            self.cb_origem.addItem(acc.name, acc.id)
            self.cb_destino.addItem(acc.name, acc.id)
        if self.cb_destino.count() > 1:
            self.cb_destino.setCurrentIndex(1)
        grid.addWidget(self.lbl_orig, 4, 0)
        grid.addWidget(self.lbl_dest, 4, 1)
        grid.addWidget(self.cb_origem, 5, 0)
        grid.addWidget(self.cb_destino, 5, 1)

        root.addLayout(grid)

        # Tags compactas (largura total)
        lbl_tags = QLabel("Tags")
        lbl_tags.setObjectName("FormLabel")
        root.addWidget(lbl_tags)

        self.btn_tags_picker = QPushButton("Tags (opcional)")
        self.btn_tags_picker.setObjectName("SecondaryButton")
        self.btn_tags_picker.setIcon(get_line_icon("tag", size=14))
        self.btn_tags_picker.setStyleSheet("text-align: left; padding: 7px 12px;")
        self._tag_menu = QMenu(self.btn_tags_picker)
        self._tag_actions: List[Tuple[str, object]] = []
        for t in self._tags:
            act = self._tag_menu.addAction(create_color_badge_icon(t.color_hex, "#", size=14), t.name)
            act.setCheckable(True)
            act.toggled.connect(self._update_tags_button_label)
            self._tag_actions.append((t.id, act))
        if not self._tags:
            empty_act = self._tag_menu.addAction("Nenhuma tag cadastrada")
            empty_act.setEnabled(False)
        self.btn_tags_picker.setMenu(self._tag_menu)
        root.addWidget(self.btn_tags_picker)

        # Card Tipo de Lançamento (igual Imagem 2)
        rec_box = QFrame()
        rec_box.setStyleSheet(
            f"QFrame {{ background-color: {pal.app_background}; border: 1px solid {pal.border_subtle}; border-radius: 10px; }}"
        )
        rb_lay = QVBoxLayout(rec_box)
        rb_lay.setContentsMargins(12, 10, 12, 10)
        rb_lay.setSpacing(8)
        lbl_rec = QLabel("Tipo de lançamento")
        lbl_rec.setObjectName("FormLabel")
        lbl_rec.setStyleSheet("border: none; background: transparent;")
        rb_lay.addWidget(lbl_rec)

        self.cb_rec = QComboBox()
        self.cb_rec.addItem("Simples (único lançamento)", REC_UNICA)
        self.cb_rec.addItem("Parcelada (Ex.: 2x a 120x)", REC_PARCELADA)
        self.cb_rec.addItem("Fixa Mensal (Recorrente)", "FIXED")
        self.cb_rec.currentIndexChanged.connect(self._on_rec_changed)
        rb_lay.addWidget(self.cb_rec)

        self.parc_opts_row = QWidget()
        self.parc_opts_row.setStyleSheet("background: transparent; border: none;")
        po_lay = QHBoxLayout(self.parc_opts_row)
        po_lay.setContentsMargins(0, 0, 0, 0)
        po_lay.setSpacing(10)
        self.sp_parcelas = QSpinBox()
        self.sp_parcelas.setRange(2, 240)
        self.sp_parcelas.setValue(2)
        self.sp_parcelas.setSuffix(" parcelas")
        self.chk_val_parcela = QCheckBox("Valor já é de cada parcela")
        po_lay.addWidget(self.sp_parcelas)
        po_lay.addWidget(self.chk_val_parcela, 1)
        rb_lay.addWidget(self.parc_opts_row)

        if self.occurrence is not None:
            self.cb_scope = QComboBox()
            if self.occurrence.is_installment:
                self.cb_scope.addItem("Toda a série (todas as parcelas)", "all")
                self.cb_scope.addItem("Somente esta parcela", "this")
            elif self.occurrence.is_recurring:
                self.cb_scope.addItem("Toda a série (todas as fixas)", "all")
                self.cb_scope.addItem("Somente esta ocorrência", "this")
            else:
                self.cb_scope.addItem("Somente esta ocorrência", "this")
            rb_lay.addWidget(self.cb_scope)

        root.addWidget(rec_box)

        # Conta / Cartão + Status (2 colunas no rodapé do formulário, igual Imagem 2)
        bot_grid = QGridLayout()
        bot_grid.setHorizontalSpacing(12)
        bot_grid.setVerticalSpacing(6)

        self.lbl_source = QLabel("Conta")
        self.lbl_source.setObjectName("FormLabel")
        self.lbl_status = QLabel("Status")
        self.lbl_status.setObjectName("FormLabel")
        bot_grid.addWidget(self.lbl_source, 0, 0)
        bot_grid.addWidget(self.lbl_status, 0, 1)

        self.cb_conta = QComboBox()
        for acc in self._accounts:
            self.cb_conta.addItem(acc.name, acc.id)

        self.cb_cartao = QComboBox()
        for idx, c in enumerate(self._cards):
            card_icon = get_card_brand_icon(brand_icon_filename(c.brand_key), size=16)
            self.cb_cartao.addItem(card_icon, f"{c.nome} (Vence {c.dia_venc})", c.id)
            if self.preselect_card_id and c.id == self.preselect_card_id:
                self.cb_cartao.setCurrentIndex(idx)

        self.cb_status = QComboBox()
        self.cb_status.addItem("Pago", True)
        self.cb_status.addItem("Pendente", False)

        bot_grid.addWidget(self.cb_conta, 1, 0)
        bot_grid.addWidget(self.cb_cartao, 1, 0)
        bot_grid.addWidget(self.cb_status, 1, 1)
        root.addLayout(bot_grid)

        # Toggle discreto de opções extras (Subcategoria, Observações, Terceiro, Rateio)
        self.btn_more_opts = QPushButton("+ Subcategoria, observações e rateio")
        self.btn_more_opts.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {pal.primary}; font-size: 12px; font-weight: 600; text-align: left; padding: 2px 0; }}"
        )
        self.btn_more_opts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_more_opts.clicked.connect(self._toggle_more_opts)
        root.addWidget(self.btn_more_opts)

        self.more_widget = QWidget()
        mw_lay = QVBoxLayout(self.more_widget)
        mw_lay.setContentsMargins(0, 0, 0, 0)
        mw_lay.setSpacing(8)
        m_grid = QGridLayout()
        m_grid.setHorizontalSpacing(12)
        m_grid.setVerticalSpacing(6)
        lbl_sub = QLabel("Subcategoria")
        lbl_sub.setObjectName("FormLabel")
        lbl_obs = QLabel("Observações")
        lbl_obs.setObjectName("FormLabel")
        m_grid.addWidget(lbl_sub, 0, 0)
        m_grid.addWidget(lbl_obs, 0, 1)
        self.cb_sub = QComboBox()
        self.ed_obs = QLineEdit()
        self.ed_obs.setPlaceholderText("Observações (opcional)")
        m_grid.addWidget(self.cb_sub, 1, 0)
        m_grid.addWidget(self.ed_obs, 1, 1)
        mw_lay.addLayout(m_grid)

        self.split_extra_row = QWidget()
        se_lay = QHBoxLayout(self.split_extra_row)
        se_lay.setContentsMargins(0, 0, 0, 0)
        se_lay.setSpacing(8)
        self.btn_split = QPushButton("Rateio Multi-Categoria")
        self.btn_split.setObjectName("SecondaryButton")
        self.btn_split.clicked.connect(self._open_split_dialog)
        self.chk_terceiro = QCheckBox("Terceiro")
        self.ed_terceiro_pessoa = QLineEdit()
        self.ed_terceiro_pessoa.setPlaceholderText("Pessoa...")
        self.ed_terceiro_pessoa.setEnabled(False)
        self.chk_terceiro.toggled.connect(self.ed_terceiro_pessoa.setEnabled)
        se_lay.addWidget(self.btn_split)
        se_lay.addWidget(self.chk_terceiro)
        se_lay.addWidget(self.ed_terceiro_pessoa, 1)
        mw_lay.addWidget(self.split_extra_row)
        self.more_widget.setVisible(False)
        root.addWidget(self.more_widget)

        # Botões inferiores: Cancelar + Criar/Salvar
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Salvar" if self.occurrence else "Criar")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setMinimumWidth(96)
        self.btn_save.setFixedHeight(36)
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._validate_and_accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    def _toggle_more_opts(self) -> None:
        vis = not self.more_widget.isVisible()
        self.more_widget.setVisible(vis)
        self.btn_more_opts.setText(
            "− Ocultar opções extras" if vis else "+ Subcategoria, observações e rateio"
        )

    def _update_tags_button_label(self) -> None:
        names = [act.text() for _, act in self._tag_actions if act.isChecked()]
        if names:
            self.btn_tags_picker.setText(", ".join(f"#{n}" for n in names))
        else:
            self.btn_tags_picker.setText("Tags (opcional)")

    def selected_tag_ids(self) -> List[str]:
        return [tid for tid, act in self._tag_actions if act.isChecked()]

    def selected_kind(self) -> str:
        return self._kind

    def _set_kind(self, kind_key: str) -> None:
        self._kind = kind_key
        from app.config.theme_palette import ThemePalette

        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        kind_styles = {
            KIND_RECEITA: (INCOME_GREEN, pal.income_badge_bg),
            KIND_DESPESA: (EXPENSE_RED, pal.expense_badge_bg),
            KIND_TRANSFERENCIA: (pal.primary, pal.primary_active_pill),
        }
        for k, btn in self._kind_btns.items():
            fg, bg = kind_styles[k]
            if k == kind_key:
                btn.setChecked(True)
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {bg}; color: {fg}; border: none; border-radius: 7px; font-weight: 700; }}"
                )
            else:
                btn.setChecked(False)
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {pal.text_secondary}; border: none; border-radius: 7px; font-weight: 500; }}"
                )

        fg_active, _ = kind_styles[kind_key]
        self.btn_save.setStyleSheet(
            f"QPushButton {{ background-color: {fg_active}; color: #FFFFFF; border: none; border-radius: 8px; font-weight: 600; padding: 8px 18px; }}"
        )

        is_exp = kind_key == KIND_DESPESA
        is_inc = kind_key == KIND_RECEITA
        is_tr = kind_key == KIND_TRANSFERENCIA

        self.pay_mode_widget.setVisible(is_exp)
        self.lbl_dt_evt.setVisible(is_exp)
        self.dt_evento.setVisible(is_exp)
        self.lbl_dt_venc.setText(
            "Data Vencimento *" if is_exp else ("Data Prevista *" if is_inc else "Data da Transferência *")
        )

        self.lbl_cat.setVisible(not is_tr)
        self.cb_cat.setVisible(not is_tr)
        self.lbl_orig.setVisible(is_tr)
        self.cb_origem.setVisible(is_tr)
        self.lbl_dest.setVisible(is_tr)
        self.cb_destino.setVisible(is_tr)

        self.lbl_source.setVisible(not is_tr)
        if is_tr:
            self.cb_conta.setVisible(False)
            self.cb_cartao.setVisible(False)
        else:
            self._on_pay_mode_changed()

        self.btn_tags_picker.setVisible(not is_tr)
        self.split_extra_row.setVisible(is_exp)
        self.btn_more_opts.setVisible(not is_tr)
        if is_tr and not self.ed_desc.text().strip():
            self.ed_desc.setText("Transferência entre contas")

        self.cb_status.blockSignals(True)
        cur_st = bool(self.cb_status.currentData())
        self.cb_status.clear()
        if is_inc:
            self.cb_status.addItem("Recebido", True)
            self.cb_status.addItem("Pendente", False)
        elif is_tr:
            self.cb_status.addItem("Efetivada", True)
            self.cb_status.addItem("Pendente", False)
        else:
            self.cb_status.addItem("Pago", True)
            self.cb_status.addItem("Pendente", False)
        idx_st = self.cb_status.findData(cur_st)
        self.cb_status.setCurrentIndex(idx_st if idx_st >= 0 else 0)
        self.cb_status.blockSignals(False)

        if not is_tr:
            cats = self.cat_repo.list_categories("DESPESA" if is_exp else "RECEITA", self.profile_id)
            self.cb_cat.blockSignals(True)
            self.cb_cat.clear()
            for c in cats:
                self.cb_cat.addItem(create_color_badge_icon(c.color_hex, c.name[:1], size=16), c.name, c.id)
            self.cb_cat.blockSignals(False)
            self._categories = cats
            self._on_cat_changed()

        self._on_rec_changed()

    def _on_pay_mode_changed(self) -> None:
        is_card = self._kind == KIND_DESPESA and self.rb_cartao.isChecked()
        self.cb_cartao.setVisible(is_card)
        self.cb_cartao.setEnabled(is_card)
        self.cb_conta.setVisible(not is_card and self._kind != KIND_TRANSFERENCIA)
        self.cb_conta.setEnabled(not is_card)
        self.lbl_source.setText("Cartão" if is_card else "Conta")
        if is_card:
            idx_p = self.cb_status.findData(False)
            if idx_p >= 0 and self.occurrence is None:
                self.cb_status.setCurrentIndex(idx_p)
            self.cb_status.setEnabled(False)
        else:
            self.cb_status.setEnabled(True)

    def _on_cat_changed(self) -> None:
        self.cb_sub.clear()
        cat_id = self.cb_cat.currentData()
        if not cat_id:
            return
        for c in getattr(self, "_categories", []):
            if c.id == cat_id:
                self.cb_sub.addItem("(Geral / Sem subcategoria)", None)
                for s in c.subcategories:
                    self.cb_sub.addItem(s.name, s.id)
                break

    def _on_rec_changed(self) -> None:
        is_parc = self.cb_rec.currentData() == REC_PARCELADA and self.occurrence is None
        self.parc_opts_row.setVisible(is_parc)

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
            self.cb_cat.setEnabled(len(self.custom_splits) <= 1)

    def _populate(self, occ: Occurrence) -> None:
        self._set_kind(occ.kind)
        self.sp_valor.setValue(occ.valor)
        self.ed_desc.setText(occ.descricao)
        self.dt_venc.setDate(_py_to_qdate(occ.data_vencimento))
        self.dt_evento.setDate(_py_to_qdate(occ.data_evento or occ.data_vencimento))
        if occ.kind == KIND_DESPESA:
            if occ.is_card:
                self.rb_cartao.setChecked(True)
                idx_c = self.cb_cartao.findData(occ.id_cartao)
                if idx_c >= 0:
                    self.cb_cartao.setCurrentIndex(idx_c)
            else:
                self.rb_conta.setChecked(True)
                idx_a = self.cb_conta.findData(occ.id_conta)
                if idx_a >= 0:
                    self.cb_conta.setCurrentIndex(idx_a)
            self._on_pay_mode_changed()
        elif occ.kind == KIND_RECEITA:
            idx_a = self.cb_conta.findData(occ.id_conta)
            if idx_a >= 0:
                self.cb_conta.setCurrentIndex(idx_a)
        else:
            idx_o = self.cb_origem.findData(occ.id_conta)
            if idx_o >= 0:
                self.cb_origem.setCurrentIndex(idx_o)
            idx_d = self.cb_destino.findData(occ.id_conta_destino)
            if idx_d >= 0:
                self.cb_destino.setCurrentIndex(idx_d)

        if occ.id_categoria:
            idx_cat = self.cb_cat.findData(occ.id_categoria)
            if idx_cat >= 0:
                self.cb_cat.setCurrentIndex(idx_cat)
        if occ.id_subcategoria:
            idx_sub = self.cb_sub.findData(occ.id_subcategoria)
            if idx_sub >= 0:
                self.cb_sub.setCurrentIndex(idx_sub)

        if occ.is_installment:
            self.cb_rec.setCurrentIndex(1)
            self.cb_rec.setEnabled(False)
        elif occ.is_fixed:
            self.cb_rec.setCurrentIndex(2)
        else:
            self.cb_rec.setCurrentIndex(0)

        idx_st = self.cb_status.findData(bool(occ.efetivada))
        if idx_st >= 0:
            self.cb_status.setCurrentIndex(idx_st)

        occ_tag_ids = {tid for tid, _, _ in occ.tags}
        for tid, act in self._tag_actions:
            act.setChecked(tid in occ_tag_ids)
        self._update_tags_button_label()
        self.ed_obs.setText(occ.obs)
        if occ.splits:
            self.custom_splits = list(occ.splits)

    def _validate_and_accept(self) -> None:
        if not self.ed_desc.text().strip():
            QMessageBox.warning(self, "Campo obrigatório", "Informe a descrição do lançamento.")
            self.ed_desc.setFocus()
            return
        if self._kind == KIND_DESPESA and self.rb_cartao.isChecked() and self.cb_cartao.count() == 0:
            QMessageBox.warning(self, "Sem cartão cadastrado", "Cadastre um cartão de crédito primeiro.")
            return
        if self._kind == KIND_TRANSFERENCIA:
            orig = self.cb_origem.currentData()
            dest = self.cb_destino.currentData()
            if not orig or not dest or str(orig) == str(dest):
                QMessageBox.warning(self, "Contas inválidas", "Selecione duas contas distintas para origem e destino.")
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
        root.setContentsMargins(20, 12, 20, 12)
        root.setSpacing(10)

        # 1. Cabeçalho estilo Artha (Título + Exportar | Importar | + Novo lançamento)
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_title = QLabel("Lançamentos")
        self.lbl_title.setObjectName("SectionTitle")
        self.lbl_subtitle = QLabel("Gerencie suas receitas e despesas")
        self.lbl_subtitle.setObjectName("MutedText")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_subtitle)
        header_row.addLayout(title_col)
        header_row.addStretch()

        self.btn_export_sheet = QPushButton("Exportar")
        self.btn_export_sheet.setObjectName("SecondaryButton")
        self.btn_export_sheet.setIcon(get_line_icon("download", size=15))
        self.btn_export_sheet.clicked.connect(self.quick_export_spreadsheet)

        self.btn_import_sheet = QPushButton("Importar")
        self.btn_import_sheet.setObjectName("SecondaryButton")
        self.btn_import_sheet.setIcon(get_line_icon("upload", size=15))
        self.btn_import_sheet.clicked.connect(self.quick_import_spreadsheet)

        self.btn_new_expense = QPushButton("Novo lançamento")
        self.btn_new_expense.setObjectName("PrimaryButton")
        self.btn_new_expense.setIcon(get_line_icon("plus", color="#FFFFFF", size=16))
        self.btn_new_expense.clicked.connect(lambda: self.open_new_transaction_dialog(KIND_DESPESA))

        # Botões legados mantidos ocultos para compatibilidade de atalhos/testes
        self.btn_new_card_exp = QPushButton("Cartão")
        self.btn_new_card_exp.setObjectName("SecondaryButton")
        self.btn_new_card_exp.clicked.connect(lambda: self.open_new_transaction_dialog(KIND_DESPESA, card_mode=True))
        self.btn_new_card_exp.setVisible(False)
        self.btn_new_income = QPushButton("Receita")
        self.btn_new_income.setObjectName("SecondaryButton")
        self.btn_new_income.clicked.connect(lambda: self.open_new_transaction_dialog(KIND_RECEITA))
        self.btn_new_income.setVisible(False)
        self.btn_new_transfer = QPushButton("Transferência")
        self.btn_new_transfer.setObjectName("SecondaryButton")
        self.btn_new_transfer.clicked.connect(lambda: self.open_new_transaction_dialog(KIND_TRANSFERENCIA))
        self.btn_new_transfer.setVisible(False)

        header_row.addWidget(self.btn_export_sheet)
        header_row.addWidget(self.btn_import_sheet)
        header_row.addWidget(self.btn_new_expense)
        root.addLayout(header_row)

        # 2. Barra Única Limpa: Fonte + Busca Rápida + Feed/Tabela + Filtros Avançados (Imagem 3)
        filter_bar = QFrame()
        filter_bar.setObjectName("CardSurface")
        f_lay = QHBoxLayout(filter_bar)
        f_lay.setContentsMargins(10, 6, 10, 6)
        f_lay.setSpacing(8)

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

        f_lay.addStretch()

        self.ed_quick_search = QLineEdit()
        self.ed_quick_search.setPlaceholderText("Buscar descrição, categoria, valor...")
        self.ed_quick_search.setMinimumWidth(230)
        self.ed_quick_search.setClearButtonEnabled(True)
        self.ed_quick_search.textChanged.connect(lambda _: self.refresh_data())
        f_lay.addWidget(self.ed_quick_search)

        self.seg_view_mode = SegmentedBar(
            [("feed", "Feed"), ("table", "Tabela")],
            active_key="feed",
        )
        self.seg_view_mode.changed.connect(self.set_view_mode)
        f_lay.addWidget(self.seg_view_mode)

        self.btn_adv_filters = QPushButton("")
        self.btn_adv_filters.setObjectName("SecondaryButton")
        self.btn_adv_filters.setToolTip("Filtros Avançados")
        self.btn_adv_filters.setIcon(get_line_icon("filter", size=15))
        self.btn_adv_filters.setFixedSize(34, 34)
        self.btn_adv_filters.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_adv_filters.clicked.connect(self.open_advanced_filters_drawer)
        f_lay.addWidget(self.btn_adv_filters)
        root.addWidget(filter_bar)

        # 3. Cards KPI Superiores (Receitas | Despesas | Resultado | Saldo Anterior)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.card_inc, self.lbl_inc_val, self.lbl_inc_sub = self._make_kpi_card(
            "Receitas", INCOME_GREEN, icon_name="arrow-up", tint="positive"
        )
        self.card_exp, self.lbl_exp_val, self.lbl_exp_sub = self._make_kpi_card(
            "Despesas", EXPENSE_RED, icon_name="arrow-down", tint="negative"
        )
        self.card_res, self.lbl_res_val, self.lbl_res_sub = self._make_kpi_card(
            "Resultado", PRIMARY_BLUE, icon_name="chart", tint="info"
        )
        self.card_prev, self.lbl_prev_val, self.lbl_prev_sub = self._make_kpi_card(
            "Saldo Anterior", PRIMARY_BLUE, icon_name="wallet", tint=None
        )
        kpi_row.addWidget(self.card_inc, 1)
        kpi_row.addWidget(self.card_exp, 1)
        kpi_row.addWidget(self.card_res, 1)
        kpi_row.addWidget(self.card_prev, 1)
        root.addLayout(kpi_row)

        # 3.1 Pílulas Contadoras Cápsula estilo Arthas (Tudo | • Receitas | • Despesas | • Transferências)
        pills_row = QHBoxLayout()
        pills_row.setSpacing(8)
        for p_key, p_label, p_dot in (
            ("ALL", "Tudo", None),
            (KIND_RECEITA, "Receitas", "#10B981"),
            (KIND_DESPESA, "Despesas", "#DC2626"),
            (KIND_TRANSFERENCIA, "Transferências", "#3B82F6"),
        ):
            chip = FilterCountPill(f"{p_label} 0", dot_color=p_dot)
            chip.setProperty("active", p_key == "ALL")
            chip.clicked.connect(lambda _=False, k=p_key: self._on_count_pill_clicked(k))
            pills_row.addWidget(chip)
            self.count_pills[p_key] = chip
        self.lbl_count_badge = QLabel("0 lançamentos")
        self.lbl_count_badge.setObjectName("MutedText")
        self.lbl_count_badge.setStyleSheet("font-size: 12px; font-weight: 500; padding-left: 6px;")
        pills_row.addWidget(self.lbl_count_badge)
        pills_row.addStretch()
        root.addLayout(pills_row)

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

        # Feed Agrupado por Data em container contínuo plano (Estilo Artha - sem zoom)
        from app.config.theme_palette import ThemePalette

        pal_init = ThemePalette.for_mode(self.db.settings.theme_mode)
        self.feed_scroll = QScrollArea()
        self.feed_scroll.setWidgetResizable(True)
        self.feed_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.feed_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {pal_init.surface_card}; border: 1px solid {pal_init.border_subtle}; border-radius: 10px; }}"
        )
        self.feed_host = QWidget()
        self.feed_host.setStyleSheet("background: transparent;")
        self.feed_layout = QVBoxLayout(self.feed_host)
        self.feed_layout.setContentsMargins(0, 0, 0, 0)
        self.feed_layout.setSpacing(0)
        self.feed_layout.addStretch()
        self.feed_scroll.setWidget(self.feed_host)
        self.stack.addWidget(self.feed_scroll)

        self.empty_widget = EmptyStateWidget(
            title="Nenhum lançamento no período",
            subtitle="Não há receitas, despesas ou transferências registradas para os filtros selecionados.",
            icon_name="list",
            action_text="+ Novo lançamento",
            action_callback=lambda: self.open_new_transaction_dialog(KIND_DESPESA),
        )
        self.stack.addWidget(self.empty_widget)

        left_col.addWidget(self.stack, stretch=1)

        # Botões de ação mantidos como atributos ocultos (ações ficam no menu ⋮ de cada linha e context menu)
        self.btn_toggle_eff = QPushButton("Confirmar / Desfazer")
        self.btn_toggle_eff.clicked.connect(self.toggle_selected_effective)
        self.btn_toggle_eff.setVisible(False)
        self.btn_edit = QPushButton("Editar")
        self.btn_edit.clicked.connect(self.edit_selected_occurrence)
        self.btn_edit.setVisible(False)
        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.setObjectName("SecondaryButton")
        self.btn_delete.clicked.connect(self.delete_selected_occurrence)
        self.btn_delete.setVisible(False)

        body_h.addLayout(left_col, stretch=1)

        # Drawers Laterais Direitos (Overlay em altura total com scrim escuro estilo Arthas)
        self.filter_drawer = SideDrawer(
            title="Filtros Avançados",
            subtitle="Configure regime, situação, conta e categoria",
            width=380,
            overlay=True,
            parent=self,
        )
        self._build_filter_drawer_content()

        self.installment_drawer = SideDrawer(
            title="Detalhe da Série Parcelada",
            subtitle="",
            width=440,
            overlay=True,
            parent=self,
        )

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
        card.lbl_value.setStyleSheet(
            f"color: {accent_hex}; font-size: 19px; font-weight: 700; background: transparent; border: none;"
        )
        card.lbl_subtitle.setStyleSheet("font-size: 11px; background: transparent; border: none;")
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
            btn.setProperty("active", key == active_kind)
            btn.setText(f"{labels[key]} {counts[key]}")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

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
        """Abre o drawer lateral em overlay com anel de progresso e timeline espaçada das parcelas."""
        self.filter_drawer.setVisible(False)
        series = self.tx_service.list_installment_series(occ)
        if not series:
            return
        self.installment_drawer.populate_installment_series(
            occ=occ,
            series=series,
            theme_mode=self.db.settings.theme_mode,
            on_open_bill=self._navigate_to_cards if occ.is_card else None,
        )
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

        # 1. Primeira Opção e Padrão (estilo Artha): Todas as Contas e Cartões
        self.cb_filter_source.addItem("Todas as Contas e Cartões", "ALL")
        self.cb_filter_source.addItem("Apenas Contas Bancárias (Caixa)", "ACCOUNTS_ONLY")

        # 2. Conta Corrente prioritária seguida das demais contas
        if primary_acc:
            self.cb_filter_source.addItem(f"Conta: {primary_acc.name}", f"ACC:{primary_acc.id}")
        for acc in other_accounts:
            self.cb_filter_source.addItem(f"Conta: {acc.name}", f"ACC:{acc.id}")

        # 3. Cartões de Crédito
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

        local_search = self.ed_quick_search.text().strip() if hasattr(self, "ed_quick_search") else ""
        merged_search = " ".join(part for part in (search_text, local_search) if part).strip()

        all_for_pills = self.tx_service.list_occurrences(
            year,
            month,
            mode=mode,
            kinds=list(ALL_KINDS),
            id_conta=id_conta,
            id_cartao=id_cartao,
            source=source,
            search=merged_search,
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
            f"color: {INCOME_GREEN if res_val >= 0 else EXPENSE_RED}; font-size: 19px; font-weight: 700; background: transparent; border: none;"
        )
        self.lbl_res_sub.setText(
            f"Saldo Previsto: {format_currency(saldo_prev)}"
        )

        self.lbl_count_badge.setText(f"{len(self._occurrences)} lançamentos")
        uncat_cnt = sum(
            1 for o in self._occurrences
            if o.kind != KIND_TRANSFERENCIA and (not o.id_categoria or str(o.id_categoria).strip() in ("", "-1"))
        )
        if uncat_cnt > 0:
            self.lbl_subtitle.setText(f"Gerencie suas receitas e despesas · {uncat_cnt} sem categoria")
        else:
            self.lbl_subtitle.setText("Gerencie suas receitas e despesas")
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

    def _open_feed_row_menu(self, row_idx: int, btn: QWidget) -> None:
        self._select_feed_row(row_idx)
        occ = self._selected_occurrence()
        if occ is None:
            return
        menu = QMenu(self)
        act_toggle = menu.addAction(
            get_line_icon("check", size=15),
            "Desfazer Baixa" if occ.efetivada else "Confirmar Baixa",
        )
        act_toggle.triggered.connect(self.toggle_selected_effective)
        act_edit = menu.addAction(get_line_icon("edit", size=15), "Editar Lançamento")
        act_edit.triggered.connect(self.edit_selected_occurrence)
        if occ.is_installment:
            act_parc = menu.addAction(get_line_icon("card", size=15), f"Ver as {occ.num_parcelas} parcelas")
            act_parc.triggered.connect(lambda: self.open_installment_drawer(occ))
        menu.addSeparator()
        act_del = menu.addAction(get_line_icon("trash", size=15), "Excluir Lançamento")
        act_del.triggered.connect(self.delete_selected_occurrence)
        menu.exec(btn.mapToGlobal(btn.rect().bottomRight()))

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

        from app.config.theme_palette import ThemePalette

        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        self.feed_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {pal.surface_card}; border: 1px solid {pal.border_subtle}; border-radius: 10px; }}"
        )

        # Cabeçalho de colunas discreto estilo Artha: DATA | DESCRIÇÃO | VALOR
        cols_hdr = QFrame()
        cols_hdr.setObjectName("FeedColsHeader")
        cols_hdr.setFixedHeight(32)
        cols_hdr.setStyleSheet(
            f"QFrame#FeedColsHeader {{ background-color: {pal.surface_card}; border: none; border-bottom: 1px solid {pal.border_subtle}; }}"
        )
        ch_lay = QHBoxLayout(cols_hdr)
        ch_lay.setContentsMargins(16, 0, 50, 0)
        ch_lay.setSpacing(10)
        lbl_h_dt = QLabel("DATA")
        lbl_h_dt.setObjectName("MutedText")
        lbl_h_dt.setFixedWidth(84)
        lbl_h_dt.setStyleSheet("border: none; background: transparent; font-size: 10px; font-weight: 700; letter-spacing: 0.05em;")
        lbl_h_desc = QLabel("DESCRIÇÃO")
        lbl_h_desc.setObjectName("MutedText")
        lbl_h_desc.setStyleSheet("border: none; background: transparent; font-size: 10px; font-weight: 700; letter-spacing: 0.05em;")
        lbl_h_val = QLabel("VALOR")
        lbl_h_val.setObjectName("MutedText")
        lbl_h_val.setMinimumWidth(115)
        lbl_h_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl_h_val.setStyleSheet("border: none; background: transparent; font-size: 10px; font-weight: 700; letter-spacing: 0.05em;")
        ch_lay.addWidget(lbl_h_dt)
        ch_lay.addWidget(lbl_h_desc, 1)
        ch_lay.addWidget(lbl_h_val)
        self.feed_layout.insertWidget(self.feed_layout.count() - 1, cols_hdr)

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
            is_today = grp_dt == today
            prefix = "Hoje · " if is_today else ""
            wk = weekdays[grp_dt.weekday()]
            day_net = sum(o.signed_total for _, o in entries)
            day_net_str = (
                f"-{format_currency(abs(day_net))}"
                if day_net < 0
                else (f"+{format_currency(day_net)}" if day_net > 0 else format_currency(0.0))
            )

            hdr_frame = QFrame()
            hdr_frame.setObjectName("FeedDateHeader")
            hdr_frame.setProperty("today", is_today)
            hdr_frame.setFixedHeight(32)
            hh = QHBoxLayout(hdr_frame)
            hh.setContentsMargins(16, 0, 50, 0)
            dt_hdr_col = pal.primary if is_today else pal.text_secondary
            lbl_dt = QLabel(f"{prefix}{grp_dt.strftime('%d/%m')} · {wk}")
            lbl_dt.setStyleSheet(
                f"font-size: 11px; font-weight: 700; color: {dt_hdr_col}; background: transparent; border: none;"
            )
            sub_bg = (
                "rgba(148, 163, 184, 0.14)"
                if pal.mode == "dark"
                else "rgba(15, 23, 42, 0.06)"
            )
            lbl_net = QLabel(f"Subtotal  {day_net_str}")
            lbl_net.setObjectName("FeedSubtotalBadge")
            lbl_net.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_net.setStyleSheet(
                f"font-size: 11px; font-weight: 600; color: {pal.text_secondary}; "
                f"background-color: {sub_bg}; border: none; border-radius: 9px; padding: 2px 9px;"
            )
            hh.addWidget(lbl_dt)
            hh.addStretch()
            hh.addWidget(lbl_net, 0, Qt.AlignmentFlag.AlignVCenter)
            self.feed_layout.insertWidget(self.feed_layout.count() - 1, hdr_frame)

            for row_idx, occ in entries:
                card = QFrame()
                card.setObjectName("FeedRowCard")
                card.setMinimumHeight(60)
                card.setProperty("selected", row_idx == self.table.currentRow())
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.mousePressEvent = lambda ev, r=row_idx: self._select_feed_row(r)  # type: ignore[method-assign]
                card.mouseDoubleClickEvent = lambda ev, r=row_idx: (  # type: ignore[method-assign]
                    self._select_feed_row(r),
                    self.edit_selected_occurrence(),
                )

                ch = QHBoxLayout(card)
                ch.setContentsMargins(16, 9, 16, 9)
                ch.setSpacing(10)

                # Checkbox discreto (22x22 íntegro) + Data (52px sem colisão)
                chk_row = QCheckBox()
                chk_row.setFixedSize(22, 22)
                chk_row.setStyleSheet(
                    "QCheckBox { spacing: 0px; margin: 0px; padding: 0px; background: transparent; }"
                )
                chk_row.toggled.connect(lambda checked, r=row_idx: checked and self._select_feed_row(r))
                ch.addWidget(chk_row)

                dt_col = QVBoxLayout()
                dt_col.setContentsMargins(0, 0, 0, 0)
                dt_col.setSpacing(0)
                lbl_d_num = QLabel(occ.ref_date.strftime("%d/%m"))
                lbl_d_num.setStyleSheet("font-size: 12px; font-weight: 600;")
                lbl_d_wk = QLabel(weekdays[occ.ref_date.weekday()].upper())
                lbl_d_wk.setObjectName("MutedText")
                lbl_d_wk.setStyleSheet("font-size: 10px;")
                dt_col.addWidget(lbl_d_num)
                dt_col.addWidget(lbl_d_wk)
                dt_wrap = QWidget()
                dt_wrap.setFixedWidth(52)
                dt_wrap.setLayout(dt_col)
                ch.addWidget(dt_wrap)

                # Ícone redondo suave estilo Arthas (34x34 circular)
                ico_lbl = QLabel()
                ico_lbl.setFixedSize(34, 34)
                ico_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if occ.kind == KIND_TRANSFERENCIA:
                    ico_lbl.setStyleSheet(
                        f"background-color: {pal.primary_active_pill}; border-radius: 17px;"
                    )
                    ico_lbl.setPixmap(get_line_pixmap("swap", color=pal.primary, size=15))
                else:
                    cat_col = occ.categoria_cor or "#5B5BD6"
                    tint_c = QColor(cat_col)
                    tint_bg = f"rgba({tint_c.red()}, {tint_c.green()}, {tint_c.blue()}, 0.14)"
                    ico_lbl.setStyleSheet(
                        f"background-color: {tint_bg}; border-radius: 17px; color: {cat_col}; font-weight: 700; font-size: 12px;"
                    )
                    if occ.kind == KIND_RECEITA:
                        ico_lbl.setPixmap(get_line_pixmap("arrow-up", color=INCOME_GREEN, size=15))
                    elif occ.is_card:
                        ico_lbl.setPixmap(get_line_pixmap("card", color=cat_col, size=15))
                    else:
                        ico_lbl.setText((occ.categoria_nome[:1] if occ.categoria_nome else "•").upper())
                ch.addWidget(ico_lbl)

                # Bloco central: Linha 1 (Descrição + Pílula Redonda Categoria) | Linha 2 (Banco/Cartão + Timeline de Pontos)
                mid = QVBoxLayout()
                mid.setContentsMargins(0, 0, 0, 0)
                mid.setSpacing(2)

                top_line = QHBoxLayout()
                top_line.setSpacing(6)
                lbl_d = QLabel(occ.descricao)
                lbl_d.setStyleSheet("font-size: 13px; font-weight: 600;")
                top_line.addWidget(lbl_d)

                if occ.kind == KIND_TRANSFERENCIA:
                    top_line.addWidget(Badge("• Transferência", variant="info"))
                elif occ.categoria_nome:
                    cat_str = (
                        f"{occ.categoria_nome} ▸ {occ.subcategoria_nome}"
                        if occ.subcategoria_nome
                        else occ.categoria_nome
                    )
                    cat_col = occ.categoria_cor or pal.primary
                    cc = QColor(cat_col)
                    cat_pill = QLabel(f"• {cat_str}")
                    cat_pill.setObjectName("CategoryCapsulePill")
                    cat_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cat_pill.setStyleSheet(
                        f"QLabel#CategoryCapsulePill {{ background-color: rgba({cc.red()}, {cc.green()}, {cc.blue()}, 0.14); "
                        f"color: {cat_col}; border: none; border-radius: 10px; padding: 2px 9px; font-size: 11px; font-weight: 600; }}"
                    )
                    top_line.addWidget(cat_pill)
                else:
                    top_line.addWidget(Badge("Sem categoria", variant="warning"))

                if not occ.efetivada:
                    top_line.addWidget(Badge("Pendente", variant="warning"))

                top_line.addStretch()
                mid.addLayout(top_line)

                sub_line = QHBoxLayout()
                sub_line.setSpacing(8)
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
                lbl_sub.setStyleSheet("font-size: 12px;")
                sub_line.addWidget(lbl_sub, 0, Qt.AlignmentFlag.AlignVCenter)

                if occ.is_installment:
                    mini = InstallmentMiniBar(
                        occ.num_parcela,
                        occ.num_parcelas,
                    )
                    mini.clicked.connect(lambda o=occ: self.open_installment_drawer(o))
                    sub_line.addWidget(mini, 0, Qt.AlignmentFlag.AlignVCenter)
                elif occ.is_fixed:
                    sub_line.addWidget(Badge("Fixa", variant="default"), 0, Qt.AlignmentFlag.AlignVCenter)

                sub_line.addStretch()
                mid.addLayout(sub_line)
                ch.addLayout(mid, 1)

                # Direita: Valor real da transação em destaque (14px bold em cor viva) + Menu ⋮
                sign = "+" if occ.kind == KIND_RECEITA else ("-" if occ.kind == KIND_DESPESA else "")
                v_col = INCOME_GREEN if occ.kind == KIND_RECEITA else (EXPENSE_RED if occ.kind == KIND_DESPESA else TRANSFER_AMBER)
                lbl_val = QLabel(f"{sign}{format_currency(abs(occ.total))}")
                lbl_val.setMinimumWidth(115)
                lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                lbl_val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {v_col};")
                ch.addWidget(lbl_val)

                btn_more = QToolButton()
                btn_more.setText("⋮")
                btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_more.setFixedSize(24, 24)
                btn_more.setStyleSheet(
                    f"QToolButton {{ background: transparent; border: none; border-radius: 6px; font-size: 15px; color: {pal.text_secondary}; }}"
                    f"QToolButton:hover {{ background-color: {pal.app_background}; color: {pal.text_primary}; }}"
                )
                btn_more.clicked.connect(lambda _=False, r=row_idx, b=btn_more: self._open_feed_row_menu(r, b))
                ch.addWidget(btn_more)

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
    def open_new_transaction_dialog(
        self,
        initial_kind: str = KIND_DESPESA,
        card_mode: bool = False,
        preselect_card_id: Optional[str] = None,
    ) -> None:
        profile_id, month, year, _ = self.get_context()
        default_dt = date(year, month, min(date.today().day, 28))
        dlg = UnifiedTransactionDialog(
            self.db,
            profile_id=profile_id,
            default_date=default_dt,
            initial_kind=initial_kind,
            card_mode=card_mode,
            preselect_card_id=preselect_card_id,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_unified_dialog_result(dlg, profile_id=profile_id, occurrence=None)

    def _save_unified_dialog_result(
        self,
        dlg: UnifiedTransactionDialog,
        profile_id: str,
        occurrence: Optional[Occurrence],
    ) -> None:
        kind = dlg.selected_kind()
        raw_rec = str(dlg.cb_rec.currentData() or REC_UNICA)
        if raw_rec == "FIXED":
            rec_code = fixed_code_for(kind)
        else:
            rec_code = raw_rec
        num_parc = int(dlg.sp_parcelas.value()) if rec_code == REC_PARCELADA else 1
        is_eff = bool(dlg.cb_status.currentData())

        if occurrence is None:
            if kind == KIND_RECEITA:
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
                    recebido=is_eff,
                    obs=dlg.ed_obs.text().strip(),
                    tag_ids=dlg.selected_tag_ids(),
                )
            elif kind == KIND_TRANSFERENCIA:
                self.tx_service.create_transfer(
                    descricao=dlg.ed_desc.text().strip(),
                    valor=float(dlg.sp_valor.value()),
                    data=_qdate_to_py(dlg.dt_venc.date()),
                    id_conta_origem=str(dlg.cb_origem.currentData()),
                    id_conta_destino=str(dlg.cb_destino.currentData()),
                    profile_id=profile_id,
                    recorrencia=rec_code,
                    num_parcelas=num_parc,
                    efetivada=is_eff,
                    obs=dlg.ed_obs.text().strip(),
                )
            else:
                is_card = dlg.rb_cartao.isChecked()
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
                    pago=is_eff,
                    obs=dlg.ed_obs.text().strip(),
                    tag_ids=dlg.selected_tag_ids(),
                    terceiro_em_nome_de=(
                        dlg.ed_terceiro_pessoa.text().strip()
                        if dlg.chk_terceiro.isChecked()
                        else None
                    ),
                    gerar_emprestimo_terceiro=dlg.chk_terceiro.isChecked(),
                )
        else:
            scope = str(dlg.cb_scope.currentData() or "this") if hasattr(dlg, "cb_scope") else "this"
            if kind == KIND_TRANSFERENCIA:
                self.tx_service.update_occurrence(
                    occurrence,
                    scope=scope,
                    descricao=dlg.ed_desc.text().strip(),
                    valor=float(dlg.sp_valor.value()),
                    data_vencimento=_qdate_to_py(dlg.dt_venc.date()),
                    id_conta=str(dlg.cb_origem.currentData()),
                    id_conta_destino=str(dlg.cb_destino.currentData()),
                    obs=dlg.ed_obs.text().strip(),
                    efetivada=is_eff,
                )
            else:
                is_card = (kind == KIND_DESPESA and dlg.rb_cartao.isChecked())
                self.tx_service.update_occurrence(
                    occurrence,
                    scope=scope,
                    new_kind=kind,
                    recorrencia=rec_code,
                    descricao=dlg.ed_desc.text().strip(),
                    valor=float(dlg.sp_valor.value()),
                    data_vencimento=_qdate_to_py(dlg.dt_venc.date()),
                    data_evento=_qdate_to_py(dlg.dt_evento.date()) if kind == KIND_DESPESA else None,
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
                        if (kind == KIND_RECEITA or len(dlg.custom_splits) <= 1) and dlg.cb_cat.currentData()
                        else None
                    ),
                    id_subcategoria=(
                        str(dlg.cb_sub.currentData())
                        if (kind == KIND_RECEITA or len(dlg.custom_splits) <= 1) and dlg.cb_sub.currentData()
                        else None
                    ),
                    splits=dlg.custom_splits if (kind == KIND_DESPESA and len(dlg.custom_splits) > 1) else None,
                    obs=dlg.ed_obs.text().strip(),
                    efetivada=is_eff,
                    tag_ids=dlg.selected_tag_ids(),
                )

        self.on_data_mutated()
        self.refresh_data()

    def open_new_expense_dialog(
        self, card_mode: bool = False, preselect_card_id: Optional[str] = None
    ) -> None:
        self.open_new_transaction_dialog(
            initial_kind=KIND_DESPESA,
            card_mode=card_mode,
            preselect_card_id=preselect_card_id,
        )

    def open_new_income_dialog(self) -> None:
        self.open_new_transaction_dialog(initial_kind=KIND_RECEITA)

    def open_new_transfer_dialog(self) -> None:
        self.open_new_transaction_dialog(initial_kind=KIND_TRANSFERENCIA)

    def toggle_selected_effective(self) -> None:
        occ = self._selected_occurrence()
        if occ is None:
            QMessageBox.information(
                self, "Selecione um lançamento", "Clique em um lançamento."
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
        dlg = UnifiedTransactionDialog(
            self.db,
            profile_id=profile_id,
            default_date=occ.data_vencimento,
            initial_kind=occ.kind,
            card_mode=occ.is_card,
            occurrence=occ,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_unified_dialog_result(dlg, profile_id=profile_id, occurrence=occ)

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
