"""Tela Nativa de Cartões de Crédito e Faturas Mensais (`CartoesView`)."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QDate, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QMouseEvent, QShortcut
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
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
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
    PRIMARY_ACCENT,
    PRIMARY_BLUE,
    WARNING_ORANGE,
)
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.domain.date_utils import add_months, clamp_day
from app.domain.models import (
    CardDTO,
    InvoiceDTO,
    KIND_DESPESA,
    KIND_RECEITA,
    Occurrence,
    REC_UNICA,
)
from app.domain.services.credit_card_service import (
    CARD_BRANDS,
    CreditCardService,
    brand_icon_filename,
)
from app.domain.services.transaction_service import TransactionService
from app.ui.bank_icons import (
    create_color_badge_icon,
    get_card_brand_icon,
    get_card_institution_pixmap,
)
from app.ui.components import Badge, EmptyStateWidget, FilterCountPill, InstallmentMiniBar, KpiCard, SideDrawer
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import format_currency, format_date_br
from app.ui.views.transacoes_view import ExpenseDialog, _qdate_to_py

_PT_MONTHS_LOWER = [
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def _extract_card_last4(card: CardDTO) -> str:
    """Extrai os 4 últimos dígitos informados no nome do cartão ou deriva sufixo determinístico."""
    m = re.search(r"(\d{4})\b", card.nome or "")
    if m:
        return m.group(1)
    digest = hashlib.md5(f"{card.id}:{card.nome}".encode("utf-8")).hexdigest()
    num = (int(digest[:6], 16) % 9000) + 1000
    return f"{num:04d}"


class CreditCardTile(QFrame):
    """
    Card interativo de Cartão de Crédito conforme o redesign:
    - Cabeçalho claro: [logo pequeno 26px] + Nome do banco/cartão + final •••• 1234
    - Fatura atual em destaque (22px bold tabular) + vencimento + Badge de status
    - Barra de limite usado com percentual
    - Hover com elevação sutil de borda e clique para selecionar e atualizar a fatura abaixo.
    """

    clicked = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(
        self,
        invoice: InvoiceDTO,
        selected: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.invoice = invoice
        self.card = invoice.card
        self._selected = selected
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(265)
        self.setMaximumWidth(340)
        self.setMinimumHeight(158)
        self._build_ui()
        self._apply_card_style()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        # 1. Cabeçalho: [logo 26px] Nome do banco + final do cartão
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        self.lbl_logo = QLabel()
        self.lbl_logo.setFixedSize(26, 26)
        pix = get_card_institution_pixmap(
            card_name=self.card.nome,
            brand_filename=brand_icon_filename(self.card.brand_key),
            color_hex=self.card.color_hex,
            account_name=self.card.conta_nome,
            size=26,
        )
        self.lbl_logo.setPixmap(pix)
        hdr.addWidget(self.lbl_logo)

        self.lbl_name = QLabel(self.card.nome)
        self.lbl_name.setStyleSheet("font-size: 14px; font-weight: 600;")
        hdr.addWidget(self.lbl_name, stretch=1)

        last4 = _extract_card_last4(self.card)
        self.lbl_last4 = QLabel(f"•••• {last4}")
        self.lbl_last4.setObjectName("MutedText")
        self.lbl_last4.setStyleSheet("font-size: 12px;")
        hdr.addWidget(self.lbl_last4)

        lay.addLayout(hdr)

        # 2. Subtítulo da fatura + Vencimento + Badge de status
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        mes_nome = _PT_MONTHS_LOWER[self.invoice.mes] if 1 <= self.invoice.mes <= 12 else f"{self.invoice.mes:02d}"
        venc_str = self.invoice.data_vencimento.strftime("%d/%m")
        self.lbl_fatura_caption = QLabel(f"Fatura de {mes_nome} · vence {venc_str}")
        self.lbl_fatura_caption.setObjectName("MutedText")
        self.lbl_fatura_caption.setStyleSheet("font-size: 12px;")
        meta_row.addWidget(self.lbl_fatura_caption)
        meta_row.addStretch()

        st = self.invoice.status
        variant = (
            "success"
            if self.invoice.paga
            else ("danger" if st == "Vencida" else ("warning" if st == "Fechada" else "info"))
        )
        self.badge_status = Badge("Paga" if self.invoice.paga else st, variant=variant)
        meta_row.addWidget(self.badge_status)
        lay.addLayout(meta_row)

        # 3. Valor da Fatura Atual em Destaque
        self.lbl_total = QLabel(format_currency(self.invoice.total))
        self.lbl_total.setStyleSheet(
            "font-size: 21px; font-weight: 700; margin-top: 2px; margin-bottom: 2px;"
        )
        lay.addWidget(self.lbl_total)

        # 4. Barra de limite usado com percentual
        limite = max(0.0, float(self.invoice.limite))
        usado = max(0.0, float(self.invoice.usado))
        pct = int(round((usado / limite) * 100)) if limite > 0 else 0
        pct_clamped = max(0, min(100, pct))

        self.lbl_limit_info = QLabel(
            f"Limite usado: {pct}% de {format_currency(limite)}"
        )
        self.lbl_limit_info.setObjectName("MutedText")
        self.lbl_limit_info.setStyleSheet("font-size: 11px;")
        lay.addWidget(self.lbl_limit_info)

        self.bar_limit = QProgressBar()
        self.bar_limit.setRange(0, 100)
        self.bar_limit.setValue(pct_clamped)
        self.bar_limit.setTextVisible(False)
        self.bar_limit.setFixedHeight(8)
        bar_color = EXPENSE_RED if pct >= 85 else (WARNING_ORANGE if pct >= 65 else PRIMARY_ACCENT)
        self.bar_limit.setStyleSheet(
            f"QProgressBar {{ border: none; border-radius: 99px; background-color: rgba(123, 129, 144, 0.15); }}"
            f"QProgressBar::chunk {{ border-radius: 99px; background-color: {bar_color}; }}"
        )
        lay.addWidget(self.bar_limit)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_card_style()

    def _apply_card_style(self) -> None:
        if self._selected:
            self.setObjectName("CardTileSelected")
            self.setStyleSheet(
                "QFrame#CardTileSelected {"
                f"  border: 2px solid {PRIMARY_BLUE};"
                "  border-radius: 12px;"
                "}"
            )
        elif self._hovered:
            self.setObjectName("CardSurface")
            self.setStyleSheet(
                "QFrame#CardSurface {"
                f"  border: 1px solid {PRIMARY_BLUE};"
                "  border-radius: 12px;"
                "}"
            )
        else:
            self.setObjectName("CardSurface")
            self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._apply_card_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_card_style()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.card.id)
        elif event.button() == Qt.MouseButton.RightButton:
            self.clicked.emit(self.card.id)
            menu = QMenu(self)
            act_edit = menu.addAction(get_line_icon("edit", size=16), "Editar cartão")
            act_del = menu.addAction(get_line_icon("trash", size=16), "Excluir cartão")
            chosen = menu.exec(event.globalPosition().toPoint())
            if chosen == act_edit:
                self.edit_requested.emit(self.card.id)
            elif chosen == act_del:
                self.delete_requested.emit(self.card.id)
        super().mousePressEvent(event)


class CardFormDialog(QDialog):
    """Modal estilo Arthas em 2 colunas para criar ou editar um Cartão de Crédito."""

    ARTHAS_CARD_COLORS = [
        "#8B5CF6", "#6366F1", "#3B82F6", "#0EA5E9", "#14B8A6",
        "#10B981", "#22C55E", "#EAB308", "#F97316", "#EF4444",
        "#EC4899", "#A855F7", "#1E293B", "#475569", "#78716C",
    ]

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        card: Optional[CardDTO] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.card = card
        self.account_repo = AccountRepository(db)
        self._selected_color: str = self.ARTHAS_CARD_COLORS[0]
        self.swatch_buttons: List[QPushButton] = []

        self.setWindowTitle(
            "Editar Cartão" if card else "Novo Cartão de Crédito"
        )
        self.setMinimumWidth(500)
        self._accounts = self.account_repo.list_accounts(profile_id)
        self._build_ui()
        if card is not None:
            self._populate(card)
        else:
            self._select_swatch(self.ARTHAS_CARD_COLORS[0])

    @staticmethod
    def _field_block(label_text: str, widget: QWidget) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setObjectName("FormLabel")
        lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        col.addWidget(lbl)
        col.addWidget(widget)
        return col

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        # Cabeçalho estilo Arthas: [ícone cartão] Novo Cartão de Crédito | botão X
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        lbl_ico = QLabel()
        lbl_ico.setFixedSize(22, 22)
        lbl_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ico.setPixmap(get_line_pixmap("card", color="#0F172A", size=18))
        lbl_t = QLabel("Editar Cartão" if self.card else "Novo Cartão de Crédito")
        lbl_t.setObjectName("SectionTitle")
        lbl_t.setStyleSheet("font-size: 18px; font-weight: 700;")
        btn_x = QPushButton()
        btn_x.setObjectName("IconButton")
        btn_x.setFixedSize(28, 28)
        btn_x.setIcon(get_line_icon("x", size=15))
        btn_x.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_x.clicked.connect(self.reject)
        hdr.addWidget(lbl_ico)
        hdr.addWidget(lbl_t, 1)
        hdr.addWidget(btn_x)
        layout.addLayout(hdr)

        # Linha 1 (2 colunas): Nome do Cartão * | Conta / Grupo
        r1 = QHBoxLayout()
        r1.setSpacing(14)
        self.ed_nome = QLineEdit()
        self.ed_nome.setPlaceholderText("Ex: Nubank, Itaú Platinum")
        self.ed_nome.setFixedHeight(38)

        self.cb_conta = QComboBox()
        self.cb_conta.setFixedHeight(38)
        self.cb_conta.addItem("Sem conta vinculada", None)
        for acc in self._accounts:
            self.cb_conta.addItem(acc.name, acc.id)

        r1.addLayout(self._field_block("Nome do Cartão *", self.ed_nome), 1)
        r1.addLayout(self._field_block("Conta vinculada", self.cb_conta), 1)
        layout.addLayout(r1)

        # Linha 2 (2 colunas): Bandeira | Últimos 4 dígitos
        r2 = QHBoxLayout()
        r2.setSpacing(14)
        self.cb_brand = QComboBox()
        self.cb_brand.setFixedHeight(38)
        for b_key, b_label, fname in CARD_BRANDS:
            self.cb_brand.addItem(get_card_brand_icon(fname, size=20), b_label, b_key)

        self.ed_last4 = QLineEdit()
        self.ed_last4.setPlaceholderText("1234")
        self.ed_last4.setMaxLength(4)
        self.ed_last4.setFixedHeight(38)

        r2.addLayout(self._field_block("Bandeira", self.cb_brand), 1)
        r2.addLayout(self._field_block("Últimos 4 dígitos", self.ed_last4), 1)
        layout.addLayout(r2)

        # Linha 3 (Largura total): Limite
        self.sp_limite = QDoubleSpinBox()
        self.sp_limite.setRange(0.0, 999_999_999.99)
        self.sp_limite.setDecimals(2)
        self.sp_limite.setPrefix("R$  ")
        self.sp_limite.setValue(5000.00)
        self.sp_limite.setFixedHeight(38)
        layout.addLayout(self._field_block("Limite", self.sp_limite))

        # Linha 4 (2 colunas): Dia de Fechamento * | Dia de Vencimento *
        r4 = QHBoxLayout()
        r4.setSpacing(14)
        self.sp_fecha = QSpinBox()
        self.sp_fecha.setRange(1, 31)
        self.sp_fecha.setValue(15)
        self.sp_fecha.setFixedHeight(38)

        self.sp_venc = QSpinBox()
        self.sp_venc.setRange(1, 31)
        self.sp_venc.setValue(25)
        self.sp_venc.setFixedHeight(38)

        r4.addLayout(self._field_block("Dia de Fechamento *", self.sp_fecha), 1)
        r4.addLayout(self._field_block("Dia de Vencimento *", self.sp_venc), 1)
        layout.addLayout(r4)

        # Linha 5: Seletor circular de Cor estilo Arthas (sincronizado com cb_cor oculto)
        self.cb_cor = QComboBox()
        self.cb_cor.setVisible(False)
        all_swatches = list(dict.fromkeys(self.ARTHAS_CARD_COLORS + list(CATEGORY_SWATCHES)))
        for hex_code in all_swatches:
            self.cb_cor.addItem(hex_code, hex_code)

        cor_col = QVBoxLayout()
        cor_col.setContentsMargins(0, 0, 0, 0)
        cor_col.setSpacing(8)
        lbl_cor = QLabel("Cor")
        lbl_cor.setObjectName("FormLabel")
        lbl_cor.setStyleSheet("font-size: 12px; font-weight: 600;")
        cor_col.addWidget(lbl_cor)

        sw_grid = QGridLayout()
        sw_grid.setHorizontalSpacing(8)
        sw_grid.setVerticalSpacing(8)
        for idx, hex_c in enumerate(self.ARTHAS_CARD_COLORS):
            btn_sw = QPushButton()
            btn_sw.setObjectName("ColorSwatchCircle")
            btn_sw.setFixedSize(28, 28)
            btn_sw.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_sw.setProperty("swatch_hex", hex_c)
            btn_sw.clicked.connect(lambda _=False, hc=hex_c: self._select_swatch(hc))
            sw_grid.addWidget(btn_sw, idx // 11, idx % 11)
            self.swatch_buttons.append(btn_sw)
        sw_wrap = QHBoxLayout()
        sw_wrap.addLayout(sw_grid)
        sw_wrap.addStretch()
        cor_col.addLayout(sw_wrap)
        layout.addLayout(cor_col)

        self.chk_padrao = QCheckBox("Definir como cartão padrão")
        layout.addWidget(self.chk_padrao)

        # Rodapé estilo Arthas: Cancelar | Criar Cartão
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        btn_cancel.setFixedHeight(38)
        btn_cancel.setMinimumWidth(96)
        btn_cancel.clicked.connect(self.reject)

        self.btn_save_card = QPushButton("Salvar" if self.card else "Criar Cartão")
        self.btn_save_card.setObjectName("PrimaryButton")
        self.btn_save_card.setFixedHeight(38)
        self.btn_save_card.setMinimumWidth(124)
        self.btn_save_card.setDefault(True)
        self.btn_save_card.clicked.connect(self._validate_and_accept)

        footer.addWidget(btn_cancel)
        footer.addWidget(self.btn_save_card)
        layout.addLayout(footer)

    def _select_swatch(self, hex_code: str) -> None:
        self._selected_color = hex_code
        idx_c = self.cb_cor.findData(hex_code)
        if idx_c < 0:
            self.cb_cor.addItem(hex_code, hex_code)
            idx_c = self.cb_cor.count() - 1
        self.cb_cor.setCurrentIndex(idx_c)
        for btn in self.swatch_buttons:
            hc = str(btn.property("swatch_hex") or "")
            is_sel = hc.lower() == hex_code.lower()
            border_rule = "2px solid #0F172A" if is_sel else "2px solid transparent"
            btn.setStyleSheet(
                f"QPushButton#ColorSwatchCircle {{ background-color: {hc}; border: {border_rule}; border-radius: 14px; padding: 0px; }}"
            )

    def resolved_card_name(self) -> str:
        base = self.ed_nome.text().strip()
        last4 = re.sub(r"\D", "", self.ed_last4.text().strip())
        if len(last4) == 4 and last4 not in base:
            return f"{base} {last4}"
        return base

    def _populate(self, card: CardDTO) -> None:
        raw_name = (card.nome or "").strip()
        m = re.search(r"\s+(\d{4})$", raw_name)
        if m:
            self.ed_nome.setText(raw_name[: m.start()].strip())
            self.ed_last4.setText(m.group(1))
        else:
            self.ed_nome.setText(raw_name)
        idx_b = self.cb_brand.findData(card.brand_key)
        if idx_b >= 0:
            self.cb_brand.setCurrentIndex(idx_b)
        self.sp_limite.setValue(card.limite)
        self.sp_fecha.setValue(card.dia_fecha)
        self.sp_venc.setValue(card.dia_venc)
        if card.id_conta:
            idx_c = self.cb_conta.findData(card.id_conta)
            if idx_c >= 0:
                self.cb_conta.setCurrentIndex(idx_c)
        self._select_swatch(card.color_hex or self.ARTHAS_CARD_COLORS[0])
        self.chk_padrao.setChecked(card.padrao == "S")

    def _validate_and_accept(self) -> None:
        if not self.ed_nome.text().strip():
            QMessageBox.warning(self, "Campo obrigatório", "Informe o nome do cartão.")
            return
        self.accept()


class InvoiceAdvanceDialog(QDialog):
    """Modal para registrar Adiantamento de Fatura de Cartão."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        invoice: InvoiceDTO,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.account_repo = AccountRepository(db)
        self.invoice = invoice
        self.setWindowTitle(f"Adiantamento de Fatura — {invoice.card.nome}")
        self.setMinimumWidth(440)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.ed_desc = QLineEdit("Adiantamento de fatura")
        form.addRow("Descrição:", self.ed_desc)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, 999_999_999.99)
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(max(50.0, invoice.total if invoice.total > 0 else 100.0))
        form.addRow("Valor do Adiantamento*:", self.sp_valor)

        self.cb_conta = QComboBox()
        for acc in self.account_repo.list_accounts(profile_id):
            self.cb_conta.addItem(acc.name, acc.id)
        if invoice.id_conta_pagamento:
            idx = self.cb_conta.findData(invoice.id_conta_pagamento)
            if idx >= 0:
                self.cb_conta.setCurrentIndex(idx)
        form.addRow("Debitar da Conta*:", self.cb_conta)

        today = date.today()
        self.dt_pag = QDateEdit(QDate(today.year, today.month, today.day))
        self.dt_pag.setCalendarPopup(True)
        self.dt_pag.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Data do Pagamento:", self.dt_pag)

        lay.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("Confirmar Adiantamento")
        btn_ok.setObjectName("PrimaryButton")
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class InvoiceMonthDialog(QDialog):
    """
    Modal para ajustar pontualmente a fatura de um mês específico.

    Permite (1) alterar os dias do ciclo, (2) definir datas EXATAS manuais de
    fechamento e vencimento e (3) forçar o status (Aberta / Fechada / Paga).
    """

    _STATUS_OPTIONS = [
        ("Automático (calculado pelas datas)", ""),
        ("Aberta", "Aberta"),
        ("Fechada", "Fechada"),
        ("Paga", "Paga"),
    ]

    def __init__(
        self,
        db: ConnectionManager,
        invoice: InvoiceDTO,
        manual_fecha: Optional[date] = None,
        manual_venc: Optional[date] = None,
        manual_status: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.invoice = invoice
        self.card = invoice.card
        self._restored_default = False
        self._init_manual_fecha = manual_fecha
        self._init_manual_venc = manual_venc
        self._init_manual_status = manual_status

        self.setWindowTitle(
            f"Ajustar Fatura de {invoice.mes:02d}/{invoice.ano} — {self.card.nome}"
        )
        self.setMinimumWidth(520)
        self._build_ui()
        self._update_preview()

    @staticmethod
    def _to_qdate(d: date) -> QDate:
        return QDate(d.year, d.month, d.day)

    def _make_date_edit(self, value: date) -> QDateEdit:
        ed = QDateEdit(self._to_qdate(value))
        ed.setCalendarPopup(True)
        ed.setDisplayFormat("dd/MM/yyyy")
        ed.dateChanged.connect(self._update_preview)
        return ed

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        info = QLabel(
            f"Ajuste pontual para a fatura de <b>{self.invoice.mes:02d}/{self.invoice.ano}</b> "
            f"do cartão <b>{self.card.nome}</b>.<br>"
            f"<span style='color: #7B8190;'>Padrão geral do cartão: "
            f"Fecha dia {self.card.dia_fecha} · Vence dia {self.card.dia_venc}</span>"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        self.sp_fecha = QSpinBox()
        self.sp_fecha.setRange(1, 31)
        self.sp_fecha.setValue(self.invoice.card.dia_fecha)
        self.sp_fecha.valueChanged.connect(self._update_preview)
        form.addRow("Dia de Fechamento desta fatura:", self.sp_fecha)

        self.sp_venc = QSpinBox()
        self.sp_venc.setRange(1, 31)
        self.sp_venc.setValue(self.invoice.card.dia_venc)
        self.sp_venc.valueChanged.connect(self._update_preview)
        form.addRow("Dia de Vencimento desta fatura:", self.sp_venc)

        has_manual = bool(self._init_manual_fecha or self._init_manual_venc)
        self.chk_manual = QCheckBox("Definir datas exatas manualmente")
        self.chk_manual.setChecked(has_manual)
        self.chk_manual.toggled.connect(self._on_manual_toggled)
        form.addRow(self.chk_manual)

        self.dt_fecha = self._make_date_edit(
            self._init_manual_fecha or self.invoice.data_fechamento
        )
        self.dt_venc = self._make_date_edit(
            self._init_manual_venc or self.invoice.data_vencimento
        )
        form.addRow("Data exata de Fechamento:", self.dt_fecha)
        form.addRow("Data exata de Vencimento:", self.dt_venc)

        self.cb_status = QComboBox()
        for label, value in self._STATUS_OPTIONS:
            self.cb_status.addItem(label, value)
        idx_s = self.cb_status.findData(self._init_manual_status)
        self.cb_status.setCurrentIndex(max(0, idx_s))
        self.cb_status.currentIndexChanged.connect(self._update_preview)
        form.addRow("Status da fatura:", self.cb_status)

        self.preview_box = QFrame()
        self.preview_box.setObjectName("CardSurface")
        p_lay = QVBoxLayout(self.preview_box)
        p_lay.setContentsMargins(12, 10, 12, 10)
        p_lay.setSpacing(4)
        self.lbl_preview_dates = QLabel("")
        self.lbl_preview_status = QLabel("")
        f_bold = QFont()
        f_bold.setBold(True)
        self.lbl_preview_status.setFont(f_bold)
        p_lay.addWidget(self.lbl_preview_dates)
        p_lay.addWidget(self.lbl_preview_status)
        form.addRow("Previsão do Ciclo:", self.preview_box)

        self.chk_limite = QCheckBox("Sobrescrever limite apenas para este mês")
        self.sp_limite = QDoubleSpinBox()
        self.sp_limite.setRange(0.0, 999_999_999.99)
        self.sp_limite.setDecimals(2)
        self.sp_limite.setPrefix("R$ ")
        self.sp_limite.setValue(self.invoice.limite)
        self.sp_limite.setEnabled(False)
        self.chk_limite.toggled.connect(self.sp_limite.setEnabled)
        form.addRow(self.chk_limite, self.sp_limite)

        lay.addLayout(form)

        bottom_row = QHBoxLayout()
        self.btn_restore = QPushButton("Restaurar Padrão do Cartão")
        self.btn_restore.setObjectName("SecondaryButton")
        self.btn_restore.setIcon(get_line_icon("refresh", size=16))
        self.btn_restore.clicked.connect(self._on_restore_default)
        bottom_row.addWidget(self.btn_restore)
        bottom_row.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_save = buttons.button(QDialogButtonBox.StandardButton.Save)
        btn_save.setText("Salvar Ajuste")
        btn_save.setObjectName("PrimaryButton")
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        bottom_row.addWidget(buttons)
        lay.addLayout(bottom_row)

        self._on_manual_toggled(self.chk_manual.isChecked())

    def _on_manual_toggled(self, manual: bool) -> None:
        self.dt_fecha.setEnabled(manual)
        self.dt_venc.setEnabled(manual)
        self.sp_fecha.setEnabled(not manual)
        self.sp_venc.setEnabled(not manual)
        self._update_preview()

    def _effective_dates(self) -> Tuple[date, date]:
        """Datas de fechamento e vencimento resultantes da configuração atual do formulário."""
        if self.chk_manual.isChecked():
            return _qdate_to_py(self.dt_fecha.date()), _qdate_to_py(self.dt_venc.date())

        dia_f = self.sp_fecha.value()
        dia_v = self.sp_venc.value()
        year, month = self.invoice.ano, self.invoice.mes
        if dia_f >= dia_v:
            prev = add_months(date(year, month, 1), -1)
            dt_fecha = date(
                prev.year, prev.month, clamp_day(prev.year, prev.month, dia_f)
            )
        else:
            dt_fecha = date(year, month, clamp_day(year, month, dia_f))
        return dt_fecha, date(year, month, clamp_day(year, month, dia_v))

    def _update_preview(self, *_args) -> None:
        if not hasattr(self, "lbl_preview_status"):
            return
        dt_fecha, dt_venc = self._effective_dates()
        forced = str(self.cb_status.currentData() or "")
        today = date.today()
        if forced == "Paga" or (not forced and self.invoice.paga):
            st_text, st_color = "Paga", INCOME_GREEN
        elif forced == "Fechada":
            st_text, st_color = "Fechada (definido manualmente)", WARNING_ORANGE
        elif forced == "Aberta":
            st_text, st_color = "Aberta (definido manualmente)", INCOME_GREEN
        elif today > dt_venc and self.invoice.total > 0:
            st_text, st_color = "Vencida (a data de vencimento já passou)", EXPENSE_RED
        elif today >= dt_fecha:
            st_text, st_color = (
                "Fechada (aguardando pagamento até o vencimento)",
                WARNING_ORANGE,
            )
        else:
            st_text, st_color = (
                "Aberta (acumulando compras até o fechamento)",
                INCOME_GREEN,
            )

        self.lbl_preview_dates.setText(
            f"Fecha em: <b>{dt_fecha.strftime('%d/%m/%Y')}</b> · "
            f"Vence em: <b>{dt_venc.strftime('%d/%m/%Y')}</b>"
        )
        self.lbl_preview_status.setText(
            f"Status em {today.strftime('%d/%m/%Y')}: {st_text}"
        )
        self.lbl_preview_status.setStyleSheet(f"color: {st_color};")

    def _validate_and_accept(self) -> None:
        if self.chk_manual.isChecked():
            dt_fecha, dt_venc = self._effective_dates()
            if dt_venc < dt_fecha:
                QMessageBox.warning(
                    self,
                    "Datas inválidas",
                    "A data de vencimento não pode ser anterior à data de fechamento.",
                )
                return
        self.accept()

    def _on_restore_default(self) -> None:
        self._restored_default = True
        self.accept()

    def is_restore(self) -> bool:
        return self._restored_default

    def get_data(self) -> dict:
        """Valores a gravar (`None` em datas = cálculo automático pelos dias do ciclo)."""
        manual = self.chk_manual.isChecked()
        dt_fecha, dt_venc = self._effective_dates() if manual else (None, None)
        return {
            "dia_fecha": self.sp_fecha.value(),
            "dia_venc": self.sp_venc.value(),
            "limite": self.sp_limite.value() if self.chk_limite.isChecked() else None,
            "data_fechamento": dt_fecha,
            "data_vencimento": dt_venc,
            "status_manual": str(self.cb_status.currentData() or "") or None,
        }


class RealignExpensesDialog(QDialog):
    """
    Modal de confirmação para realinhar compras à vista com vencimento divergente
    do ciclo atual configurado no cartão de crédito.
    """

    def __init__(
        self,
        card: CardDTO,
        changes: List[Dict[str, object]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.card = card
        self.changes = changes
        self.setWindowTitle(f"Realinhar Compras — {card.nome}")
        self.setMinimumWidth(660)
        self.setMinimumHeight(400)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        info = QLabel(
            f"Foram encontradas <b>{len(self.changes)}</b> compra(s) com data de vencimento "
            f"divergente do ciclo configurado no cartão <b>{self.card.nome}</b>.<br>"
            f"<span style='color: #7B8190;'>Ciclo do cartão: "
            f"Fecha dia <b>{self.card.dia_fecha:02d}</b> · Vence dia <b>{self.card.dia_venc:02d}</b></span><br>"
            f"Deseja mover estes lançamentos para a fatura correta?"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        tbl = QTableWidget(len(self.changes), 5)
        tbl.setHorizontalHeaderLabels(
            ["Data Compra", "Descrição", "Vencimento Gravado", "Novo Vencimento", "Valor"]
        )
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(38)

        f_bold = QFont()
        f_bold.setBold(True)
        for idx, ch in enumerate(self.changes):
            dt_c: date = ch["data_compra"]  # type: ignore[assignment]
            dt_old: date = ch["vencimento_atual"]  # type: ignore[assignment]
            dt_new: date = ch["vencimento_novo"]  # type: ignore[assignment]

            it_c = QTableWidgetItem(dt_c.strftime("%d/%m/%Y"))
            it_c.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(idx, 0, it_c)

            tbl.setItem(idx, 1, QTableWidgetItem(str(ch["descricao"])))

            it_old = QTableWidgetItem(dt_old.strftime("%d/%m/%Y"))
            it_old.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_old.setForeground(QColor(WARNING_ORANGE))
            tbl.setItem(idx, 2, it_old)

            it_new = QTableWidgetItem(dt_new.strftime("%d/%m/%Y"))
            it_new.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_new.setForeground(QColor(INCOME_GREEN))
            it_new.setFont(f_bold)
            tbl.setItem(idx, 3, it_new)

            it_v = QTableWidgetItem(format_currency(float(ch["valor"])))  # type: ignore[arg-type]
            it_v.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_v.setFont(f_bold)
            tbl.setItem(idx, 4, it_v)

        lay.addWidget(tbl, stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        btn_cancel.clicked.connect(self.reject)
        btn_apply = QPushButton(f"Confirmar e Realinhar ({len(self.changes)})")
        btn_apply.setObjectName("PrimaryButton")
        btn_apply.setIcon(get_line_icon("check", color="#FFFFFF", size=16))
        btn_apply.clicked.connect(self.accept)
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_apply)
        lay.addLayout(bottom)


class CartoesView(QWidget):
    """
    Tela interativa de Cartões de Crédito e Faturas Mensais:
    - Galeria de Cards de Cartão no topo com logo pequeno do banco (26px) ao lado do nome,
      final ••••, valor da fatura em destaque, vencimento e barra de limite com percentual.
    - Clique em qualquer card atualiza a fatura detalhada abaixo.
    - Seletor de mês de fatura (< Anterior / Combo / Próxima >), filtro por categoria dentro da fatura,
      linhas expansíveis mostrando parcelas restantes e valor futuro a pagar.
    - Botões 'Pagar fatura' (primário) e 'Novo lançamento no cartão' (secundário).
    - Estado vazio amigável ('Adicione seu primeiro cartão').
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

        self._invoices: List[InvoiceDTO] = []
        self._selected_invoice: Optional[InvoiceDTO] = None
        self._last_context_period: Optional[Tuple[int, int]] = None
        self.card_tiles: List[CreditCardTile] = []
        self._expanded_occ_id: Optional[str] = None
        self._inv_type_filter: str = "ALL"
        self._filtered_items: List[Occurrence] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # 1. Cabeçalho estilo Arthas: Título à esquerda | [Limites e cadastro] [Novo cartão] à direita
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_t = QLabel("Cartões e faturas")
        lbl_t.setObjectName("SectionTitle")
        self.lbl_cards_subtitle = QLabel("Faturas fechadas e projeções abertas para os próximos meses em um só lugar")
        self.lbl_cards_subtitle.setObjectName("MutedText")
        title_col.addWidget(lbl_t)
        title_col.addWidget(self.lbl_cards_subtitle)
        header_row.addLayout(title_col)
        header_row.addStretch()

        self.btn_limits_toggle = QPushButton("Limites e cadastro")
        self.btn_limits_toggle.setObjectName("SecondaryButton")
        self.btn_limits_toggle.setIcon(get_line_icon("card", size=15))
        self.btn_limits_toggle.setFixedHeight(36)
        self.btn_limits_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_limits_toggle.clicked.connect(
            lambda: self.limits_summary_card.setVisible(not self.limits_summary_card.isVisible())
        )
        header_row.addWidget(self.btn_limits_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_new_card = QPushButton("Novo cartão")
        self.btn_new_card.setObjectName("PrimaryButton")
        self.btn_new_card.setIcon(get_line_icon("plus", color="#FFFFFF", size=15))
        self.btn_new_card.setFixedHeight(36)
        self.btn_new_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new_card.clicked.connect(self.open_new_card_dialog)
        header_row.addWidget(self.btn_new_card, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header_row)

        # 2. KPI Cards Consolidados (com micro-ícones e tint semântico)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_total, self.lbl_kpi_total, self.lbl_kpi_total_sub = self._make_kpi_card(
            "Total das Faturas", EXPENSE_RED, icon_name="card", tint="negative"
        )
        self.kpi_open, self.lbl_kpi_open, self.lbl_kpi_open_sub = self._make_kpi_card(
            "Em Aberto / Fechadas", WARNING_ORANGE, icon_name="clock", tint="warning"
        )
        self.kpi_limit, self.lbl_kpi_limit, self.lbl_kpi_limit_sub = self._make_kpi_card(
            "Limite Consolidado", PRIMARY_BLUE, icon_name="target", tint="info"
        )
        self.kpi_avail, self.lbl_kpi_avail, self.lbl_kpi_avail_sub = self._make_kpi_card(
            "Limite Disponível", INCOME_GREEN, icon_name="check", tint="positive"
        )
        kpi_row.addWidget(self.kpi_total, 1)
        kpi_row.addWidget(self.kpi_open, 1)
        kpi_row.addWidget(self.kpi_limit, 1)
        kpi_row.addWidget(self.kpi_avail, 1)
        root.addLayout(kpi_row)

        # Tabela oculta mantida por compatibilidade retroativa
        self.tbl_cards = QTableWidget(0, 5)
        self.tbl_cards.setVisible(False)
        self.tbl_cards.itemSelectionChanged.connect(self._on_card_selection_changed)

        # 3. QStackedWidget Principal: [Página 0: Galeria de Cartões + Fatura] vs [Página 1: Empty State]
        self.main_stack = QStackedWidget()

        content_page = QWidget()
        c_lay = QVBoxLayout(content_page)
        c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.setSpacing(14)

        # 3A. Galeria Horizontal de Cards Interativos de Cartão
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.cards_scroll.setFixedHeight(172)
        self.cards_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.cards_container = QWidget()
        self.cards_container.setObjectName("CardsGalleryHost")
        self.cards_container.setStyleSheet("QWidget#CardsGalleryHost { background: transparent; }")
        self.cards_row_layout = QHBoxLayout(self.cards_container)
        self.cards_row_layout.setContentsMargins(0, 2, 0, 6)
        self.cards_row_layout.setSpacing(14)
        self.cards_row_layout.addStretch()
        self.cards_scroll.setWidget(self.cards_container)
        c_lay.addWidget(self.cards_scroll)

        # 3A-ter. Banner sutil "Melhor dia de compra" estilo Arthas
        self.best_day_banner = QFrame()
        self.best_day_banner.setObjectName("BestDayBanner")
        bd_lay = QHBoxLayout(self.best_day_banner)
        bd_lay.setContentsMargins(16, 10, 16, 10)
        bd_lay.setSpacing(10)
        lbl_bd_ico = QLabel()
        lbl_bd_ico.setFixedSize(18, 18)
        lbl_bd_ico.setPixmap(get_line_pixmap("zap", color=INCOME_GREEN, size=15))
        self.lbl_best_day_text = QLabel("Melhor dia de compra: selecione um cartão")
        self.lbl_best_day_text.setStyleSheet(
            f"font-size: 12px; font-weight: 500; color: {INCOME_GREEN}; background: transparent; border: none;"
        )
        bd_lay.addWidget(lbl_bd_ico)
        bd_lay.addWidget(self.lbl_best_day_text, 1)
        c_lay.addWidget(self.best_day_banner)

        # 3A-bis. Barra Resumo de Limites Consolidados (estilo Artha Limites e cadastro)
        self.limits_summary_card = QFrame()
        self.limits_summary_card.setObjectName("CardSurface")
        ls_lay = QHBoxLayout(self.limits_summary_card)
        ls_lay.setContentsMargins(18, 12, 18, 12)
        ls_lay.setSpacing(16)

        ls_left = QVBoxLayout()
        ls_left.setSpacing(4)
        lbl_ls_title = QLabel("USO CONSOLIDADO DE LIMITE")
        lbl_ls_title.setObjectName("MutedText")
        lbl_ls_title.setStyleSheet("font-size: 10px; font-weight: 700; letter-spacing: 0.06em;")
        ls_badges = QHBoxLayout()
        ls_badges.setSpacing(8)
        self.badge_limit_used = Badge("R$ 0,00 utilizado", variant="info")
        self.badge_limit_avail = Badge("R$ 0,00 disponível", variant="success")
        ls_badges.addWidget(self.badge_limit_used)
        ls_badges.addWidget(self.badge_limit_avail)
        ls_badges.addStretch()
        ls_left.addWidget(lbl_ls_title)
        ls_left.addLayout(ls_badges)

        self.bar_total_limit = QProgressBar()
        self.bar_total_limit.setRange(0, 100)
        self.bar_total_limit.setValue(0)
        self.bar_total_limit.setTextVisible(False)
        self.bar_total_limit.setFixedHeight(10)
        self.bar_total_limit.setStyleSheet(
            f"QProgressBar {{ background-color: rgba(148, 163, 184, 0.22); border: none; border-radius: 5px; }}"
            f"QProgressBar::chunk {{ background-color: {PRIMARY_BLUE}; border-radius: 5px; }}"
        )
        self.lbl_limit_pct = QLabel("0% utilizado")
        self.lbl_limit_pct.setObjectName("MutedText")
        self.lbl_limit_pct.setStyleSheet("font-size: 11px; font-weight: 600;")

        ls_lay.addLayout(ls_left)
        ls_lay.addWidget(self.bar_total_limit, 1)
        ls_lay.addWidget(self.lbl_limit_pct)
        c_lay.addWidget(self.limits_summary_card)

        # 3B. Card de Detalhe da Fatura Selecionada (alinhado em linha única, sem botões empilhados)
        self.invoice_card = QFrame()
        self.invoice_card.setObjectName("CardSurface")
        r_lay = QVBoxLayout(self.invoice_card)
        r_lay.setContentsMargins(22, 18, 22, 18)
        r_lay.setSpacing(14)

        # Linha 1 da Fatura (100% em uma única linha alinhada):
        # Esquerda: [Logo] Nome | < Seletor Mês > | Fatura aberta | Status
        # Direita:  [Novo lançamento no cartão] | [Pagar fatura] | [Gerenciar ▾]
        inv_top = QHBoxLayout()
        inv_top.setSpacing(8)

        self.lbl_invoice_logo = QLabel()
        self.lbl_invoice_logo.setFixedSize(28, 28)
        inv_top.addWidget(self.lbl_invoice_logo, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lbl_invoice_title = QLabel("Selecione um cartão")
        self.lbl_invoice_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        inv_top.addWidget(self.lbl_invoice_title, 0, Qt.AlignmentFlag.AlignVCenter)

        inv_top.addSpacing(6)

        self.btn_prev_inv = QPushButton()
        self.btn_prev_inv.setObjectName("SecondaryButton")
        self.btn_prev_inv.setIcon(get_line_icon("chevron-left", size=15))
        self.btn_prev_inv.setFixedSize(34, 34)
        self.btn_prev_inv.setToolTip("Fatura anterior")
        self.btn_prev_inv.clicked.connect(self._on_prev_invoice)
        inv_top.addWidget(self.btn_prev_inv, 0, Qt.AlignmentFlag.AlignVCenter)

        self.cb_invoice_month = QComboBox()
        self.cb_invoice_month.setFixedHeight(34)
        self.cb_invoice_month.setMinimumWidth(230)
        self.cb_invoice_month.currentIndexChanged.connect(self._on_invoice_month_selected)
        inv_top.addWidget(self.cb_invoice_month, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_next_inv = QPushButton()
        self.btn_next_inv.setObjectName("SecondaryButton")
        self.btn_next_inv.setIcon(get_line_icon("chevron-right", size=15))
        self.btn_next_inv.setFixedSize(34, 34)
        self.btn_next_inv.setToolTip("Próxima fatura")
        self.btn_next_inv.clicked.connect(self._on_next_invoice)
        inv_top.addWidget(self.btn_next_inv, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_open_inv = QPushButton("Fatura aberta")
        self.btn_open_inv.setObjectName("SecondaryButton")
        self.btn_open_inv.setFixedHeight(34)
        self.btn_open_inv.setToolTip("Ir direto para a fatura aberta atual do cartão")
        self.btn_open_inv.clicked.connect(self._on_jump_open_invoice)
        inv_top.addWidget(self.btn_open_inv, 0, Qt.AlignmentFlag.AlignVCenter)

        self.badge_invoice_status = Badge("Aberta", variant="info")
        inv_top.addWidget(self.badge_invoice_status, 0, Qt.AlignmentFlag.AlignVCenter)

        inv_top.addStretch()

        self.btn_add_purchase = QPushButton("Novo lançamento no cartão")
        self.btn_add_purchase.setObjectName("SecondaryButton")
        self.btn_add_purchase.setIcon(get_line_icon("plus", size=15))
        self.btn_add_purchase.setFixedHeight(34)
        self.btn_add_purchase.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_purchase.clicked.connect(self.open_new_purchase_for_selected_card)
        inv_top.addWidget(self.btn_add_purchase, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_pay_reopen = QPushButton("Pagar fatura")
        self.btn_pay_reopen.setObjectName("PrimaryButton")
        self.btn_pay_reopen.setIcon(get_line_icon("check", color="#FFFFFF", size=15))
        self.btn_pay_reopen.setFixedHeight(34)
        self.btn_pay_reopen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pay_reopen.clicked.connect(self.pay_or_reopen_selected_invoice)
        inv_top.addWidget(self.btn_pay_reopen, 0, Qt.AlignmentFlag.AlignVCenter)

        # Atributo preservado por compatibilidade; ação incorporada de forma limpa em Gerenciar ▾
        self.btn_advance = QPushButton("Adiantar", self.invoice_card)
        self.btn_advance.setObjectName("SecondaryButton")
        self.btn_advance.setVisible(False)
        self.btn_advance.clicked.connect(self.advance_selected_invoice)

        self.btn_card_actions = QPushButton("Gerenciar ▾")
        self.btn_card_actions.setObjectName("SecondaryButton")
        self.btn_card_actions.setFixedHeight(34)
        self.btn_card_actions.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_card_actions.setToolTip("Adiantar fatura, ajustar ciclo, editar ou excluir cartão")
        card_menu = QMenu(self.btn_card_actions)
        act_adv = card_menu.addAction(get_line_icon("zap", size=15), "Adiantar fatura")
        act_adv.triggered.connect(self.advance_selected_invoice)
        act_adj = card_menu.addAction(get_line_icon("calendar", size=15), "Ajustar fatura")
        act_adj.triggered.connect(self.edit_selected_invoice_month)
        act_realign = card_menu.addAction(get_line_icon("refresh", size=15), "Realinhar ciclo")
        act_realign.triggered.connect(self.realign_selected_card_purchases)
        card_menu.addSeparator()
        act_edit_c = card_menu.addAction(get_line_icon("edit", size=15), "Editar cartão")
        act_edit_c.triggered.connect(self.edit_selected_card)
        act_del_c = card_menu.addAction(get_line_icon("trash", size=15), "Excluir cartão")
        act_del_c.triggered.connect(self.delete_selected_card)
        self.btn_card_actions.setMenu(card_menu)
        inv_top.addWidget(self.btn_card_actions, 0, Qt.AlignmentFlag.AlignVCenter)

        r_lay.addLayout(inv_top)

        # Linha 2 da Fatura: Resumo em destaque limpo (sem segunda fileira de botões)
        summary_row = QHBoxLayout()
        summary_col = QVBoxLayout()
        summary_col.setSpacing(2)

        lbl_tot_cap = QLabel("Total da fatura")
        lbl_tot_cap.setObjectName("MutedText")
        lbl_tot_cap.setStyleSheet("font-size: 12px;")
        summary_col.addWidget(lbl_tot_cap)

        self.lbl_invoice_big_total = QLabel("R$ 0,00")
        self.lbl_invoice_big_total.setStyleSheet("font-size: 26px; font-weight: 700;")
        summary_col.addWidget(self.lbl_invoice_big_total)

        self.lbl_invoice_meta = QLabel("")
        self.lbl_invoice_meta.setObjectName("MutedText")
        self.lbl_invoice_meta.setStyleSheet("font-size: 12px;")
        summary_col.addWidget(self.lbl_invoice_meta)

        summary_row.addLayout(summary_col)
        summary_row.addStretch()
        r_lay.addLayout(summary_row)

        sep_inv = QFrame()
        sep_inv.setObjectName("ModalSeparator")
        sep_inv.setFixedHeight(1)
        r_lay.addWidget(sep_inv)

        # Barra da seção "Lançamentos" estilo Arthas: Título à esquerda | [Todos] [Parcelados] [Todas as categorias] à direita
        items_bar = QHBoxLayout()
        items_bar.setSpacing(8)
        lbl_it_sec = QLabel("Lançamentos")
        lbl_it_sec.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.lbl_inv_items_count = QLabel("0")
        self.lbl_inv_items_count.setObjectName("MutedText")
        self.lbl_inv_items_count.setStyleSheet("font-size: 12px; font-weight: 600;")
        items_bar.addWidget(lbl_it_sec, 0, Qt.AlignmentFlag.AlignVCenter)
        items_bar.addWidget(self.lbl_inv_items_count, 0, Qt.AlignmentFlag.AlignVCenter)
        items_bar.addStretch()

        self.pill_inv_all = FilterCountPill("Todos 0")
        self.pill_inv_all.setProperty("active", True)
        self.pill_inv_all.clicked.connect(lambda: self._set_inv_type_filter("ALL"))
        items_bar.addWidget(self.pill_inv_all, 0, Qt.AlignmentFlag.AlignVCenter)

        self.pill_inv_parc = FilterCountPill("Parcelados 0", dot_color="#7F77DD")
        self.pill_inv_parc.setProperty("active", False)
        self.pill_inv_parc.clicked.connect(lambda: self._set_inv_type_filter("PARC"))
        items_bar.addWidget(self.pill_inv_parc, 0, Qt.AlignmentFlag.AlignVCenter)

        self.cb_filter_category = QComboBox()
        self.cb_filter_category.setFixedHeight(32)
        self.cb_filter_category.setMinimumWidth(175)
        self.cb_filter_category.addItem("Todas as categorias", "ALL")
        self.cb_filter_category.currentIndexChanged.connect(self._on_category_filter_changed)
        items_bar.addWidget(self.cb_filter_category, 0, Qt.AlignmentFlag.AlignVCenter)

        r_lay.addLayout(items_bar)

        # Tabela de Lançamentos da Fatura (sem grades verticais, com expansão de parcelas ao clicar)
        self.tbl_items = QTableWidget(0, 6)
        self.tbl_items.setHorizontalHeaderLabels(
            [
                "Data",
                "Descrição",
                "Parcela",
                "Categoria",
                "Situação",
                "Valor",
            ]
        )
        self.tbl_items.setShowGrid(False)
        self.tbl_items.verticalHeader().setVisible(False)
        self.tbl_items.verticalHeader().setDefaultSectionSize(42)
        self.tbl_items.setMinimumHeight(220)
        ihdr = self.tbl_items.horizontalHeader()
        ihdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        ihdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        ihdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.tbl_items.setColumnWidth(2, 136)
        ihdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        ihdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.tbl_items.setColumnWidth(4, 120)
        ihdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        ihdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.tbl_items.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_items.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tbl_items.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_items.cellClicked.connect(self._on_item_cell_clicked)
        self.tbl_items.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tbl_items.itemSelectionChanged.connect(self._on_item_selection_changed)
        self.tbl_items.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl_items.customContextMenuRequested.connect(self._show_items_context_menu)

        shortcut_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.tbl_items)
        shortcut_del.activated.connect(self.delete_selected_item)
        shortcut_edit_ret = QShortcut(QKeySequence(Qt.Key.Key_Return), self.tbl_items)
        shortcut_edit_ret.activated.connect(self.edit_selected_item)
        shortcut_edit_f2 = QShortcut(QKeySequence(Qt.Key.Key_F2), self.tbl_items)
        shortcut_edit_f2.activated.connect(self.edit_selected_item)
        r_lay.addWidget(self.tbl_items, stretch=1)

        # Barra inferior discreta para o lançamento selecionado na fatura
        item_act_bar = QHBoxLayout()
        item_act_bar.setSpacing(8)

        self.btn_edit_purchase = QPushButton("Editar compra")
        self.btn_edit_purchase.setObjectName("SecondaryButton")
        self.btn_edit_purchase.setIcon(get_line_icon("edit", size=15))
        self.btn_edit_purchase.setEnabled(False)
        self.btn_edit_purchase.clicked.connect(self.edit_selected_item)

        self.btn_refund = QPushButton("Estornar compra")
        self.btn_refund.setObjectName("SecondaryButton")
        self.btn_refund.setIcon(get_line_icon("refresh", size=15))
        self.btn_refund.setEnabled(False)
        self.btn_refund.clicked.connect(self.refund_selected_item)

        self.btn_delete_purchase = QPushButton("Excluir compra")
        self.btn_delete_purchase.setObjectName("SecondaryButton")
        self.btn_delete_purchase.setIcon(get_line_icon("trash", size=15))
        self.btn_delete_purchase.setEnabled(False)
        self.btn_delete_purchase.clicked.connect(self.delete_selected_item)

        item_act_bar.addWidget(self.btn_edit_purchase)
        item_act_bar.addWidget(self.btn_refund)
        item_act_bar.addWidget(self.btn_delete_purchase)
        item_act_bar.addStretch()

        lbl_hint = QLabel("Clique em uma linha para ver as parcelas restantes · Duplo clique para editar")
        lbl_hint.setObjectName("MutedText")
        lbl_hint.setStyleSheet("font-size: 11px;")
        item_act_bar.addWidget(lbl_hint)

        item_act_bar.addStretch()

        self.btn_format_card = QPushButton("Limpar lançamentos")
        self.btn_format_card.setObjectName("SecondaryButton")
        self.btn_format_card.setToolTip("Remove todos os lançamentos deste cartão para reimportar do zero")
        self.btn_format_card.clicked.connect(self.format_selected_card)
        item_act_bar.addWidget(self.btn_format_card)

        r_lay.addLayout(item_act_bar)
        c_lay.addWidget(self.invoice_card, stretch=1)

        self.main_stack.addWidget(content_page)

        # Página 1: Estado Vazio Amigável ("Adicione seu primeiro cartão")
        self.empty_cards_widget = EmptyStateWidget(
            title="Adicione seu primeiro cartão",
            subtitle="Cadastre seus cartões de crédito para acompanhar limites, faturas mensais e compras parceladas.",
            icon_name="card",
            action_text="+ Novo cartão",
            action_callback=self.open_new_card_dialog,
        )
        self.main_stack.addWidget(self.empty_cards_widget)

        root.addWidget(self.main_stack, stretch=1)

        self.installment_drawer = SideDrawer(
            title="Detalhe da Série Parcelada",
            subtitle="",
            width=440,
            overlay=True,
            parent=self,
        )

    def open_installment_drawer(self, occ: Occurrence) -> None:
        series = self.tx_service.list_installment_series(occ)
        if not series:
            return
        self.installment_drawer.populate_installment_series(
            occ=occ,
            series=series,
            theme_mode=self.db.settings.theme_mode,
            on_open_bill=None,
        )
        self.installment_drawer.open_drawer()

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

    def _rebuild_card_tiles(self, selected_card_id: Optional[str]) -> None:
        while self.cards_row_layout.count() > 0:
            item = self.cards_row_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.card_tiles.clear()

        for inv in self._invoices:
            is_sel = bool(selected_card_id and inv.card.id == selected_card_id)
            tile = CreditCardTile(inv, selected=is_sel, parent=self.cards_container)
            tile.clicked.connect(self._on_card_tile_clicked)
            tile.edit_requested.connect(self._on_card_tile_edit)
            tile.delete_requested.connect(self._on_card_tile_delete)
            self.cards_row_layout.addWidget(tile)
            self.card_tiles.append(tile)

        self.cards_row_layout.addStretch()

    def _on_card_tile_clicked(self, card_id: str) -> None:
        for idx, inv in enumerate(self._invoices):
            if inv.card.id == card_id:
                self.tbl_cards.blockSignals(True)
                self.tbl_cards.selectRow(idx)
                self.tbl_cards.blockSignals(False)
                for tile in self.card_tiles:
                    tile.set_selected(tile.card.id == card_id)
                self._expanded_occ_id = None
                self._show_invoice(inv)
                break

    def _on_card_tile_edit(self, card_id: str) -> None:
        self._on_card_tile_clicked(card_id)
        self.edit_selected_card()

    def _on_card_tile_delete(self, card_id: str) -> None:
        self._on_card_tile_clicked(card_id)
        self.delete_selected_card()

    def refresh_data(self) -> None:
        profile_id, month, year, search_text = self.get_context()
        period_changed = self._last_context_period != (year, month)
        self._last_context_period = (year, month)

        prev_card_id = (
            self._selected_invoice.card.id if self._selected_invoice else None
        )
        prev_invoice_month = (
            (self._selected_invoice.ano, self._selected_invoice.mes)
            if self._selected_invoice
            else None
        )

        cards = self.card_service.list_cards(profile_id=profile_id)
        if search_text.strip():
            q = search_text.strip().lower()
            cards = [c for c in cards if q in c.nome.lower()]

        # Faturas vinculadas ao período do cabeçalho global (avança automaticamente
        # para a fatura aberta do próximo mês quando o ciclo do mês corrente já fechou)
        self._invoices = [
            self.card_service.resolve_invoice_for_context(c.id, year, month)
            for c in cards
        ]

        total_faturas = sum(inv.total for inv in self._invoices)
        total_abertas = sum(inv.total for inv in self._invoices if not inv.paga)
        limite_total = sum(c.limite for c in cards)
        usado_total = sum(inv.usado for inv in self._invoices)
        disponivel_total = max(0.0, limite_total - usado_total)
        open_cnt = sum(1 for inv in self._invoices if not inv.paga and inv.total > 0)

        self.lbl_kpi_total.setText(format_currency(total_faturas))
        self.lbl_kpi_total_sub.setText(f"{len(self._invoices)} cartões ativos")

        self.lbl_kpi_open.setText(format_currency(total_abertas))
        self.lbl_kpi_open_sub.setText(f"{open_cnt} faturas com saldo aberto")

        self.lbl_kpi_limit.setText(format_currency(limite_total))
        self.lbl_kpi_limit_sub.setText(f"Comprometido: {format_currency(usado_total)}")

        self.lbl_kpi_avail.setText(format_currency(disponivel_total))
        self.lbl_kpi_avail_sub.setText("Soma dos limites disponíveis")

        self.badge_limit_used.setText(f"{format_currency(usado_total)} utilizado")
        self.badge_limit_avail.setText(f"{format_currency(disponivel_total)} disponível")
        used_pct = min(100, int(round((usado_total / limite_total) * 100.0))) if limite_total > 0 else 0
        self.bar_total_limit.setValue(used_pct)
        self.lbl_limit_pct.setText(f"{used_pct}% utilizado de {format_currency(limite_total)}")

        # Sincroniza tabela oculta por compatibilidade
        self.tbl_cards.blockSignals(True)
        self.tbl_cards.setRowCount(0)
        sel_row = 0
        for idx, inv in enumerate(self._invoices):
            self.tbl_cards.insertRow(idx)
            self.tbl_cards.setItem(idx, 0, QTableWidgetItem(inv.card.nome))
            self.tbl_cards.setItem(idx, 1, QTableWidgetItem(f"F:{inv.card.dia_fecha:02d}/V:{inv.card.dia_venc:02d}"))
            self.tbl_cards.setItem(idx, 2, QTableWidgetItem(inv.status))
            self.tbl_cards.setItem(idx, 3, QTableWidgetItem(format_currency(inv.total)))
            self.tbl_cards.setItem(idx, 4, QTableWidgetItem(format_currency(inv.disponivel)))
            if prev_card_id and inv.card.id == prev_card_id:
                sel_row = idx

        if not self._invoices:
            self.tbl_cards.blockSignals(False)
            self._selected_invoice = None
            self._rebuild_card_tiles(None)
            self.main_stack.setCurrentWidget(self.empty_cards_widget)
            self._show_invoice(None)
            return

        self.main_stack.setCurrentWidget(self.main_stack.widget(0))
        self.tbl_cards.selectRow(sel_row)
        self.tbl_cards.blockSignals(False)

        target_card = self._invoices[sel_row].card
        if not period_changed and prev_invoice_month and prev_card_id == target_card.id:
            inv_to_show = self.card_service.get_invoice(
                target_card.id, prev_invoice_month[0], prev_invoice_month[1]
            )
            self._invoices[sel_row] = inv_to_show
        else:
            inv_to_show = self._invoices[sel_row]
        self._rebuild_card_tiles(target_card.id)
        self._show_invoice(inv_to_show)

    def _on_card_selection_changed(self) -> None:
        row = self.tbl_cards.currentRow()
        if 0 <= row < len(self._invoices):
            target = self._invoices[row]
            for tile in self.card_tiles:
                tile.set_selected(tile.card.id == target.card.id)
            self._expanded_occ_id = None
            self._show_invoice(target)

    def _show_invoice(self, inv: Optional[InvoiceDTO]) -> None:
        self._selected_invoice = inv
        self.tbl_items.setRowCount(0)
        if inv is None:
            self.lbl_invoice_title.setText("Nenhum cartão selecionado")
            self.lbl_invoice_big_total.setText("R$ 0,00")
            self.lbl_invoice_meta.setText("")
            self.lbl_best_day_text.setText("Selecione um cartão para visualizar o melhor dia de compra.")
            self.lbl_inv_items_count.setText("0")
            self.pill_inv_all.setText("Todos 0")
            self.pill_inv_parc.setText("Parcelados 0")
            self.btn_prev_inv.setEnabled(False)
            self.btn_next_inv.setEnabled(False)
            self.btn_open_inv.setEnabled(False)
            self.cb_invoice_month.setEnabled(False)
            self.cb_invoice_month.blockSignals(True)
            self.cb_invoice_month.clear()
            self.cb_invoice_month.blockSignals(False)
            self.cb_filter_category.setEnabled(False)
            self.btn_add_purchase.setEnabled(False)
            self.btn_edit_purchase.setEnabled(False)
            self.btn_delete_purchase.setEnabled(False)
            self.btn_pay_reopen.setEnabled(False)
            self.btn_advance.setEnabled(False)
            self.btn_card_actions.setEnabled(False)
            self.btn_refund.setEnabled(False)
            self.btn_format_card.setEnabled(False)
            return

        self.btn_prev_inv.setEnabled(True)
        self.btn_next_inv.setEnabled(True)
        self.btn_open_inv.setEnabled(True)
        self.cb_invoice_month.setEnabled(True)
        self.cb_filter_category.setEnabled(True)
        self.btn_add_purchase.setEnabled(True)
        self.btn_pay_reopen.setEnabled(True)
        self.btn_advance.setEnabled(True)
        self.btn_card_actions.setEnabled(True)
        self.btn_format_card.setEnabled(True)

        # Logo pequeno (26px) + Nome do cartão no cabeçalho da fatura
        pix = get_card_institution_pixmap(
            card_name=inv.card.nome,
            brand_filename=brand_icon_filename(inv.card.brand_key),
            color_hex=inv.card.color_hex,
            account_name=inv.card.conta_nome,
            size=26,
        )
        self.lbl_invoice_logo.setPixmap(pix)
        self.lbl_invoice_title.setText(inv.card.nome)

        # Badge de status da fatura
        st = inv.status
        variant = (
            "success"
            if inv.paga
            else ("danger" if st == "Vencida" else ("warning" if st == "Fechada" else "info"))
        )
        self.badge_invoice_status.setText("Fatura paga" if inv.paga else st)
        self.badge_invoice_status.set_variant(variant)

        # Resumo numérico da fatura + Banner Melhor dia de compra estilo Arthas
        self.lbl_invoice_big_total.setText(format_currency(inv.total))
        pct = int(round((inv.total / inv.limite) * 100)) if inv.limite > 0 else 0
        self.lbl_invoice_meta.setText(
            f"{pct}% do limite · Fecha dia {format_date_br(inv.data_fechamento.isoformat())} · "
            f"Vence dia {format_date_br(inv.data_vencimento.isoformat())} · "
            f"Disponível: {format_currency(inv.disponivel)}"
        )
        best_day = 1 if inv.card.dia_fecha >= 31 else inv.card.dia_fecha + 1
        self.lbl_best_day_text.setText(
            f"Melhor dia de compra no {inv.card.nome}: a partir do dia {best_day:02d}, "
            f"as compras entram na próxima fatura (vencimento dia {inv.card.dia_venc:02d})."
        )

        # Botão Pagar fatura (Primário quando em aberto, Secundário quando já paga)
        if inv.paga:
            self.btn_pay_reopen.setText("Desfazer pagamento")
            self.btn_pay_reopen.setObjectName("SecondaryButton")
            self.btn_pay_reopen.setIcon(get_line_icon("refresh", size=16))
        else:
            self.btn_pay_reopen.setText("Pagar fatura")
            self.btn_pay_reopen.setObjectName("PrimaryButton")
            self.btn_pay_reopen.setIcon(get_line_icon("check", color="#FFFFFF", size=16))
        self.btn_pay_reopen.style().unpolish(self.btn_pay_reopen)
        self.btn_pay_reopen.style().polish(self.btn_pay_reopen)

        self._populate_invoice_combo(inv)
        self._populate_category_filter(inv)
        self._render_invoice_items()

    def _populate_category_filter(self, inv: InvoiceDTO) -> None:
        prev_cat = str(self.cb_filter_category.currentData() or "ALL")
        self.cb_filter_category.blockSignals(True)
        self.cb_filter_category.clear()
        self.cb_filter_category.addItem("Todas as categorias", "ALL")

        cats_seen: List[str] = []
        for occ in inv.items:
            c_name = occ.categoria_nome or "Sem categoria"
            if c_name not in cats_seen:
                cats_seen.append(c_name)
        for c_name in sorted(cats_seen):
            self.cb_filter_category.addItem(c_name, c_name)

        idx = self.cb_filter_category.findData(prev_cat)
        self.cb_filter_category.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_filter_category.blockSignals(False)

    def _on_category_filter_changed(self, _index: int = 0) -> None:
        self._expanded_occ_id = None
        self._render_invoice_items()

    def _set_inv_type_filter(self, ftype: str) -> None:
        self._inv_type_filter = ftype
        self._expanded_occ_id = None
        self.pill_inv_all.setProperty("active", ftype == "ALL")
        self.pill_inv_parc.setProperty("active", ftype == "PARC")
        self.pill_inv_all.update()
        self.pill_inv_parc.update()
        self._render_invoice_items()

    @staticmethod
    def _format_installment_expansion_text(occ: Occurrence) -> str:
        """Gera o texto explicativo das parcelas restantes ao expandir uma linha da fatura."""
        if occ.num_parcelas > 1 and not occ.is_fixed:
            restantes = max(0, occ.num_parcelas - occ.num_parcela)
            valor_futuro = round(restantes * occ.total, 2)
            if restantes > 0:
                return (
                    f"Parcela {occ.num_parcela} de {occ.num_parcelas} · "
                    f"restam {restantes} parcela(s) · "
                    f"{format_currency(valor_futuro)} a pagar nas próximas faturas"
                )
            return (
                f"Parcela {occ.num_parcela} de {occ.num_parcelas} (última parcela) · "
                f"sem parcelas futuras"
            )
        if occ.is_fixed:
            return "Despesa fixa mensal recorrente no cartão · cobrada continuamente nas próximas faturas"
        return "Lançamento à vista · sem parcelas futuras"

    def _render_invoice_items(self) -> None:
        self.tbl_items.setRowCount(0)
        inv = self._selected_invoice
        if inv is None:
            self._on_item_selection_changed()
            return

        all_cnt = len(inv.items)
        parc_cnt = sum(1 for o in inv.items if o.is_installment)
        self.pill_inv_all.setText(f"Todos {all_cnt}")
        self.pill_inv_parc.setText(f"Parcelados {parc_cnt}")

        cat_filter = str(self.cb_filter_category.currentData() or "ALL")
        if cat_filter == "ALL":
            items_pool = list(inv.items)
        else:
            items_pool = [
                o for o in inv.items if (o.categoria_nome or "Sem categoria") == cat_filter
            ]

        if self._inv_type_filter == "PARC":
            self._filtered_items = [o for o in items_pool if o.is_installment]
        else:
            self._filtered_items = items_pool

        self.lbl_inv_items_count.setText(str(len(self._filtered_items)))

        f_bold = QFont()
        f_bold.setBold(True)

        row_cursor = 0
        for occ in self._filtered_items:
            self.tbl_items.insertRow(row_cursor)
            dt_compra = (occ.data_evento or occ.data_vencimento).isoformat()

            # 0: Data
            it_dt = QTableWidgetItem(format_date_br(dt_compra))
            it_dt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_dt.setData(Qt.ItemDataRole.UserRole, occ)
            self.tbl_items.setItem(row_cursor, 0, it_dt)

            # 1: Descrição
            it_desc = QTableWidgetItem(occ.descricao)
            it_desc.setData(Qt.ItemDataRole.UserRole, occ)
            self.tbl_items.setItem(row_cursor, 1, it_desc)

            # 2: Parcela (com mini-barra visual clicável quando parcelado; texto vazio evita sobreposição sob o widget)
            parc_str = occ.parcela_label or "1/1"
            it_parc = QTableWidgetItem("" if occ.is_installment else parc_str)
            it_parc.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if occ.is_installment:
                it_parc.setToolTip(f"Parcela {parc_str}")
            elif parc_str in ("1/1", "—", "À vista"):
                it_parc.setForeground(QColor("#7B8190"))
            it_parc.setData(Qt.ItemDataRole.UserRole, occ)
            self.tbl_items.setItem(row_cursor, 2, it_parc)

            if occ.is_installment:
                mini = InstallmentMiniBar(
                    occ.num_parcela,
                    occ.num_parcelas,
                    accent_hex=PRIMARY_BLUE,
                )
                mini.clicked.connect(lambda o=occ: self.open_installment_drawer(o))
                m_wrap = QWidget()
                m_lay = QHBoxLayout(m_wrap)
                m_lay.setContentsMargins(2, 0, 2, 0)
                m_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                m_lay.addWidget(mini)
                self.tbl_items.setCellWidget(row_cursor, 2, m_wrap)

            # 3: Categoria com dot colorido
            if len(occ.splits) > 1:
                cat_txt = f"Rateio ({len(occ.splits)} categorias)"
                cat_icon = create_color_badge_icon("#7B8190", "R", size=16)
            else:
                cat_txt = occ.categoria_nome or "Sem categoria"
                if occ.subcategoria_nome:
                    cat_txt = f"{occ.categoria_nome} ▸ {occ.subcategoria_nome}"
                cat_color = occ.categoria_cor or "#7B8190"
                initial = occ.categoria_nome[:1] if occ.categoria_nome else "•"
                cat_icon = create_color_badge_icon(cat_color, initial, size=16)
            it_cat = QTableWidgetItem(cat_icon, cat_txt)
            it_cat.setData(Qt.ItemDataRole.UserRole, occ)
            self.tbl_items.setItem(row_cursor, 3, it_cat)

            # 4: Situação (Badge)
            st_label = "Pago" if occ.efetivada else "Em fatura"
            st_var = "success" if occ.efetivada else "warning"
            it_st = QTableWidgetItem(st_label)
            it_st.setForeground(QColor(0, 0, 0, 0))
            it_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_st.setData(Qt.ItemDataRole.UserRole, occ)
            self.tbl_items.setItem(row_cursor, 4, it_st)

            badge = Badge(st_label, variant=st_var)
            b_wrap = QWidget()
            b_lay = QHBoxLayout(b_wrap)
            b_lay.setContentsMargins(0, 0, 0, 0)
            b_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_lay.addWidget(badge)
            self.tbl_items.setCellWidget(row_cursor, 4, b_wrap)

            # 5: Valor
            sign = "+" if occ.total < 0 else "−"
            it_val = QTableWidgetItem(f"{sign} {format_currency(abs(occ.total))}")
            it_val.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_val.setFont(f_bold)
            it_val.setForeground(
                QColor(INCOME_GREEN if occ.total < 0 else EXPENSE_RED)
            )
            it_val.setData(Qt.ItemDataRole.UserRole, occ)
            self.tbl_items.setItem(row_cursor, 5, it_val)

            row_cursor += 1

            # Linha expansível de detalhes de parcelas restantes
            if self._expanded_occ_id and occ.id == self._expanded_occ_id:
                self.tbl_items.insertRow(row_cursor)
                self.tbl_items.setSpan(row_cursor, 0, 1, 6)
                exp_text = self._format_installment_expansion_text(occ)
                it_exp = QTableWidgetItem(f"   ↳  {exp_text}")
                it_exp.setData(Qt.ItemDataRole.UserRole, occ)
                it_exp.setForeground(QColor("#7B8190"))
                self.tbl_items.setItem(row_cursor, 0, it_exp)
                self.tbl_items.setRowHeight(row_cursor, 34)
                row_cursor += 1

        self._on_item_selection_changed()

    def _toggle_expand_occ_id(self, occ_id: str) -> None:
        self._expanded_occ_id = None if self._expanded_occ_id == occ_id else occ_id
        self._render_invoice_items()

    def _selected_occurrence_item(self) -> Optional[Occurrence]:
        row = self.tbl_items.currentRow()
        if row < 0:
            return None
        it = self.tbl_items.item(row, 0)
        if it is not None:
            occ = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(occ, Occurrence):
                return occ
        if self._selected_invoice and 0 <= row < len(self._selected_invoice.items):
            return self._selected_invoice.items[row]
        return None

    def _on_item_cell_clicked(self, row: int, _col: int) -> None:
        it = self.tbl_items.item(row, 0)
        if it is None:
            return
        occ = it.data(Qt.ItemDataRole.UserRole)
        if not isinstance(occ, Occurrence):
            return
        if self._expanded_occ_id == occ.id:
            self._expanded_occ_id = None
        else:
            self._expanded_occ_id = occ.id
        self._render_invoice_items()
        # Restaura seleção na linha principal do item clicado
        for r in range(self.tbl_items.rowCount()):
            cand = self.tbl_items.item(r, 0)
            if cand and cand.data(Qt.ItemDataRole.UserRole) == occ:
                self.tbl_items.selectRow(r)
                break

    def _on_item_selection_changed(self) -> None:
        has_sel = self._selected_occurrence_item() is not None
        self.btn_edit_purchase.setEnabled(has_sel)
        self.btn_delete_purchase.setEnabled(has_sel)
        self.btn_refund.setEnabled(has_sel)

    def _populate_invoice_combo(self, inv: InvoiceDTO) -> None:
        self.cb_invoice_month.blockSignals(True)
        self.cb_invoice_month.clear()

        today = date.today()
        base_today = date(today.year, today.month, 1)
        months_set = set()
        for off in range(-6, 7):
            d = add_months(base_today, off)
            months_set.add((d.year, d.month))
        months_set.add((inv.ano, inv.mes))

        open_inv = self.card_service.get_open_invoice(inv.card.id, today)
        months_set.add((open_inv.ano, open_inv.mes))

        sorted_months = sorted(list(months_set))
        sel_idx = 0
        for i, (yr, mo) in enumerate(sorted_months):
            cand = self.card_service.get_invoice(inv.card.id, yr, mo)
            is_open = (cand.ano == open_inv.ano and cand.mes == open_inv.mes)
            if cand.paga:
                label = f"{mo:02d}/{yr} — Paga · {format_currency(cand.total)}"
            elif is_open:
                label = (
                    f"{mo:02d}/{yr} — Aberta (Atual) · Fecha {cand.data_fechamento.strftime('%d/%m')} "
                    f"· {format_currency(cand.total)}"
                )
            elif cand.status == "Fechada":
                label = (
                    f"{mo:02d}/{yr} — Fechada · Vence {cand.data_vencimento.strftime('%d/%m')} "
                    f"· {format_currency(cand.total)}"
                )
            elif cand.status == "Vencida":
                label = (
                    f"{mo:02d}/{yr} — Vencida · Venceu {cand.data_vencimento.strftime('%d/%m')} "
                    f"· {format_currency(cand.total)}"
                )
            else:
                label = f"{mo:02d}/{yr} — {cand.status} · {format_currency(cand.total)}"

            self.cb_invoice_month.addItem(label, (yr, mo))
            if (yr, mo) == (inv.ano, inv.mes):
                sel_idx = i

        self.cb_invoice_month.setCurrentIndex(sel_idx)
        self.cb_invoice_month.blockSignals(False)

    def _on_invoice_month_selected(self, index: int) -> None:
        if self._selected_invoice is None or index < 0:
            return
        data = self.cb_invoice_month.itemData(index)
        if not data:
            return
        yr, mo = data
        if (yr, mo) != (self._selected_invoice.ano, self._selected_invoice.mes):
            self._expanded_occ_id = None
            new_inv = self.card_service.get_invoice(
                self._selected_invoice.card.id, yr, mo
            )
            self._show_invoice(new_inv)

    def _on_prev_invoice(self) -> None:
        if self._selected_invoice is None:
            return
        self._expanded_occ_id = None
        cur_d = date(self._selected_invoice.ano, self._selected_invoice.mes, 1)
        prev_d = add_months(cur_d, -1)
        new_inv = self.card_service.get_invoice(
            self._selected_invoice.card.id, prev_d.year, prev_d.month
        )
        self._show_invoice(new_inv)

    def _on_next_invoice(self) -> None:
        if self._selected_invoice is None:
            return
        self._expanded_occ_id = None
        cur_d = date(self._selected_invoice.ano, self._selected_invoice.mes, 1)
        next_d = add_months(cur_d, 1)
        new_inv = self.card_service.get_invoice(
            self._selected_invoice.card.id, next_d.year, next_d.month
        )
        self._show_invoice(new_inv)

    def _on_jump_open_invoice(self) -> None:
        if self._selected_invoice is None:
            return
        self._expanded_occ_id = None
        open_inv = self.card_service.get_open_invoice(self._selected_invoice.card.id)
        self._show_invoice(open_inv)

    def realign_selected_card_purchases(self) -> None:
        if self._selected_invoice is None:
            QMessageBox.information(
                self,
                "Atenção",
                "Selecione um cartão para verificar e realinhar os lançamentos.",
            )
            return
        card = self._selected_invoice.card
        changes = self.card_service.preview_realign_card_expenses(card.id)
        if not changes:
            QMessageBox.information(
                self,
                "Lançamentos Alinhados",
                f"Todas as compras do cartão <b>{card.nome}</b> já estão alinhadas com o ciclo atual "
                f"(Fechamento dia <b>{card.dia_fecha:02d}</b> · Vencimento dia <b>{card.dia_venc:02d}</b>).<br>"
                f"Nenhum ajuste é necessário.",
            )
            return

        dlg = RealignExpensesDialog(card, changes, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        count = self.card_service.realign_card_expenses(card.id)
        QMessageBox.information(
            self,
            "Realinhamento Concluído",
            f"<b>{count}</b> compra(s) foram movidas com sucesso para suas respectivas faturas "
            f"de acordo com o ciclo do cartão {card.nome}.",
        )
        self.on_data_mutated()
        self.refresh_data()

    # ------------------------------------------------------------------ #
    # Ações de Cartão e Fatura
    # ------------------------------------------------------------------ #
    def open_new_card_dialog(self) -> None:
        profile_id, _, _, _ = self.get_context()
        dlg = CardFormDialog(self.db, profile_id=profile_id, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.card_service.create_card(
            nome=dlg.resolved_card_name(),
            limite=float(dlg.sp_limite.value()),
            dia_fecha=int(dlg.sp_fecha.value()),
            dia_venc=int(dlg.sp_venc.value()),
            id_conta=(
                str(dlg.cb_conta.currentData()) if dlg.cb_conta.currentData() else None
            ),
            profile_id=profile_id,
            color_hex=str(dlg.cb_cor.currentData() or "#1E88E5"),
            brand_key=str(dlg.cb_brand.currentData() or "visa"),
            padrao=dlg.chk_padrao.isChecked(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def edit_selected_card(self) -> None:
        if self._selected_invoice is None:
            return
        card = self._selected_invoice.card
        dlg = CardFormDialog(
            self.db, profile_id=card.id_profile, card=card, parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.card_service.update_card(
            card.id,
            nome=dlg.resolved_card_name(),
            limite=float(dlg.sp_limite.value()),
            dia_fecha=int(dlg.sp_fecha.value()),
            dia_venc=int(dlg.sp_venc.value()),
            id_conta=(
                str(dlg.cb_conta.currentData()) if dlg.cb_conta.currentData() else None
            ),
            color_hex=str(dlg.cb_cor.currentData() or "#1E88E5"),
            brand_key=str(dlg.cb_brand.currentData() or "visa"),
            padrao=dlg.chk_padrao.isChecked(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def delete_selected_card(self) -> None:
        if self._selected_invoice is None:
            return
        card = self._selected_invoice.card
        ans = QMessageBox.question(
            self,
            "Excluir Cartão de Crédito",
            f"Deseja excluir o cartão '{card.nome}' e todas as suas despesas vinculadas?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.card_service.delete_card(card.id)
        self.on_data_mutated()
        self.refresh_data()

    def open_new_purchase_for_selected_card(self) -> None:
        if self._selected_invoice is None:
            return
        profile_id, month, year, _ = self.get_context()
        default_dt = date(year, month, min(date.today().day, 28))
        dlg = ExpenseDialog(
            self.db,
            profile_id=profile_id,
            default_date=default_dt,
            card_mode=True,
            preselect_card_id=self._selected_invoice.card.id,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from app.domain.models import REC_PARCELADA

        rec_code = str(dlg.cb_rec.currentData() or REC_UNICA)
        num_parc = int(dlg.sp_parcelas.value()) if rec_code == REC_PARCELADA else 1
        self.tx_service.create_expense(
            descricao=dlg.ed_desc.text().strip(),
            valor=float(dlg.sp_valor.value()),
            data_vencimento=_qdate_to_py(dlg.dt_venc.date()),
            data_evento=_qdate_to_py(dlg.dt_evento.date()),
            profile_id=profile_id,
            id_cartao=str(dlg.cb_cartao.currentData()),
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
            obs=dlg.ed_obs.text().strip(),
            tag_ids=dlg.selected_tag_ids(),
        )
        self.on_data_mutated()
        self.refresh_data()

    def pay_or_reopen_selected_invoice(self) -> None:
        inv = self._selected_invoice
        if inv is None:
            return
        if inv.paga:
            self.card_service.reopen_invoice(inv.card.id, inv.ano, inv.mes)
        else:
            self.card_service.pay_invoice(
                inv.card.id,
                inv.ano,
                inv.mes,
                id_conta=inv.id_conta_pagamento or inv.card.id_conta,
                data_pagamento=inv.data_vencimento,
            )
        self.on_data_mutated()
        self.refresh_data()

    def advance_selected_invoice(self) -> None:
        inv = self._selected_invoice
        if inv is None:
            return
        profile_id, _, _, _ = self.get_context()
        dlg = InvoiceAdvanceDialog(self.db, profile_id, inv, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        id_conta = str(dlg.cb_conta.currentData() or "")
        if not id_conta:
            QMessageBox.warning(
                self, "Conta obrigatória", "Selecione uma conta para debitar o adiantamento."
            )
            return
        qd = dlg.dt_pag.date()
        self.card_service.add_invoice_advance(
            inv.card.id,
            inv.ano,
            inv.mes,
            valor=float(dlg.sp_valor.value()),
            id_conta=id_conta,
            data_pagamento=date(qd.year(), qd.month(), qd.day()),
            descricao=dlg.ed_desc.text().strip() or "Adiantamento de fatura",
        )
        self.on_data_mutated()
        self.refresh_data()

    def refund_selected_item(self) -> None:
        inv = self._selected_invoice
        if inv is None:
            return
        occ = self._selected_occurrence_item()
        if occ is None:
            QMessageBox.information(
                self,
                "Selecione uma compra",
                "Selecione um lançamento na tabela da fatura para estornar.",
            )
            return
        ans = QMessageBox.question(
            self,
            "Estornar Compra no Cartão",
            f"Deseja lançar um crédito de estorno de {format_currency(abs(occ.total))} "
            f"para '{occ.descricao}' nesta fatura?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.card_service.refund_card_expense(occ)
        self.on_data_mutated()
        self.refresh_data()

    def edit_selected_item(self) -> None:
        inv = self._selected_invoice
        if inv is None:
            return
        occ = self._selected_occurrence_item()
        if occ is None:
            QMessageBox.information(
                self,
                "Selecione uma compra",
                "Selecione um lançamento na tabela da fatura para editar.",
            )
            return
        self._open_edit_dialog_for_occurrence(occ)

    def delete_selected_item(self) -> None:
        inv = self._selected_invoice
        if inv is None:
            return
        occ = self._selected_occurrence_item()
        if occ is None:
            QMessageBox.information(
                self,
                "Selecione uma compra",
                "Selecione um lançamento na tabela da fatura para excluir.",
            )
            return
        scope = "this"
        if occ.num_parcelas > 1 or occ.is_fixed:
            dlg = QDialog(self)
            dlg.setWindowTitle("Excluir Lançamento Parcelado / Recorrente")
            dlg.setMinimumWidth(420)
            v = QVBoxLayout(dlg)
            v.setContentsMargins(20, 20, 20, 20)
            v.setSpacing(12)
            lbl = QLabel(
                f"Como deseja excluir <b>{occ.descricao}</b> ({occ.parcela_label or 'Parcelado'})?"
            )
            lbl.setWordWrap(True)
            v.addWidget(lbl)
            rb_this = QRadioButton("Somente esta parcela desta fatura")
            rb_future = QRadioButton("Esta e todas as próximas parcelas")
            rb_all = QRadioButton("Toda a série de parcelas (inclusive anteriores)")
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
                f"Deseja realmente excluir a compra '{occ.descricao}' ({format_currency(occ.total)}) desta fatura?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self.tx_service.delete_occurrence(occ, scope=scope)
        self.on_data_mutated()
        self.refresh_data()

    def format_selected_card(self) -> None:
        inv = self._selected_invoice
        if inv is None:
            QMessageBox.information(
                self, "Atenção", "Selecione um cartão para limpar os lançamentos."
            )
            return
        card = inv.card
        ans = QMessageBox.warning(
            self,
            "Limpar Lançamentos do Cartão",
            f"ATENÇÃO: Deseja realmente excluir TODOS os lançamentos vinculados ao cartão '{card.nome}'?\n\n"
            f"Esta operação removerá todas as compras e faturas deste cartão do sistema, "
            f"permitindo que você reimporte seus extratos do zero.\n\n"
            f"Tem certeza que deseja continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        count = self.card_service.wipe_card_expenses(card.id)
        self.on_data_mutated()
        self.refresh_data()
        QMessageBox.information(
            self,
            "Cartão Limpo",
            f"O cartão '{card.nome}' teve seus lançamentos removidos com sucesso!\n"
            f"Total de {count} lançamento(s) excluído(s).",
        )

    def _show_items_context_menu(self, pos) -> None:
        item = self.tbl_items.itemAt(pos)
        if item is None:
            return
        occ = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(occ, Occurrence):
            return
        menu = QMenu(self)
        act_edit = menu.addAction(get_line_icon("edit", size=16), "Editar compra")
        act_refund = menu.addAction(get_line_icon("refresh", size=16), "Estornar compra")
        menu.addSeparator()
        act_delete = menu.addAction(get_line_icon("trash", size=16), "Excluir compra")
        chosen = menu.exec(self.tbl_items.viewport().mapToGlobal(pos))
        if chosen == act_edit:
            self._open_edit_dialog_for_occurrence(occ)
        elif chosen == act_delete:
            self.delete_selected_item()
        elif chosen == act_refund:
            self.refund_selected_item()

    def edit_selected_invoice_month(self) -> None:
        inv = self._selected_invoice
        if inv is None:
            QMessageBox.information(
                self, "Atenção", "Selecione um cartão para ajustar a fatura."
            )
            return
        m_fecha, m_venc, m_status = self.card_service.get_invoice_manual_overrides(
            inv.card.id, inv.ano, inv.mes
        )
        dlg = InvoiceMonthDialog(
            self.db,
            inv,
            manual_fecha=m_fecha,
            manual_venc=m_venc,
            manual_status=m_status,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if dlg.is_restore():
                self.card_service.reset_invoice_month(inv.card.id, inv.ano, inv.mes)
            else:
                self.card_service.update_invoice_month(
                    inv.card.id, inv.ano, inv.mes, **dlg.get_data()
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))
            return
        self.on_data_mutated()
        self.refresh_data()

    def _on_item_double_clicked(self, item: QTableWidgetItem) -> None:
        occ = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(occ, Occurrence):
            inv = self._selected_invoice
            if inv is None or not (0 <= item.row() < len(inv.items)):
                return
            occ = inv.items[item.row()]
        self._open_edit_dialog_for_occurrence(occ)

    def _open_edit_dialog_for_occurrence(self, occ: Occurrence) -> None:
        dlg = ExpenseDialog(
            self.db,
            profile_id=occ.id_profile,
            default_date=occ.data_vencimento,
            card_mode=True,
            preselect_card_id=occ.id_cartao,
            occurrence=occ,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
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
                data_evento=_qdate_to_py(dlg.dt_evento.date()),
                id_conta=str(dlg.cb_conta.currentData()) if not is_card and dlg.cb_conta.currentData() else None,
                id_cartao=str(dlg.cb_cartao.currentData()) if is_card and dlg.cb_cartao.currentData() else None,
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
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível salvar a edição", str(exc))
            return
        self.on_data_mutated()
        self.refresh_data()
