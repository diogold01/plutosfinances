"""Widgets de UI do Lançamento Inteligente (Ctrl+K) — Especificação visual oficial Plutos.

Somente interface: nenhuma chamada de rede, IA, banco ou serviços de persistência.
Toda a lógica (worker, validação, persistência e catálogo) é ligada externamente
através dos sinais e métodos públicos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from PySide6.QtCore import QDate, QEvent, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.config.app_settings import IMAGES_DIR
from app.config.theme_palette import RADIUS_MD, RADIUS_PILL, RADIUS_SM, ThemePalette
from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA
from app.ui.components import BaseModalDialog
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import format_currency

Option = Tuple[str, str]  # (id, rótulo)
SPARKLE_TILE_IMG = IMAGES_DIR / "plutos_ai_sparkle_tile_256.png"
SPARKLE_ICON_IMG = IMAGES_DIR / "plutos_ai_sparkle_256.png"


# --------------------------------------------------------------------------- #
# QSS dinâmico — todas as cores vêm estritamente do ThemePalette
# --------------------------------------------------------------------------- #
def build_ai_entry_qss(p: ThemePalette) -> str:
    return f"""
    QWidget#EntryList {{ background: transparent; }}
    QScrollArea#EntryScroll {{ background: transparent; border: none; }}

    QFrame#AIInputBox {{
        background: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: {RADIUS_MD}px;
    }}
    QFrame#AIInputBox[focused="true"] {{
        border: 1.5px solid {p.primary};
    }}
    QPlainTextEdit#AIInput {{
        background: transparent;
        border: none;
        color: {p.text_primary};
        font-size: 14px;
        selection-background-color: {p.primary};
        selection-color: #FFFFFF;
    }}

    /* Botões Primários e Secundários consistentes em qualquer contexto */
    QPushButton#PrimaryButton {{
        background: {p.primary};
        color: #FFFFFF;
        border: 1px solid {p.primary};
        border-radius: {RADIUS_SM}px;
        font-weight: 600;
        font-size: 13px;
        padding: 0 18px;
        min-height: 36px;
    }}
    QPushButton#PrimaryButton:hover {{
        background: {p.primary_hover};
        border-color: {p.primary_hover};
    }}
    QPushButton#PrimaryButton:disabled {{
        background: {p.border_subtle};
        color: {p.text_secondary};
        border-color: {p.border_subtle};
    }}

    QPushButton#SecondaryButton {{
        background: {p.surface_card};
        color: {p.text_primary};
        border: 1px solid {p.border_subtle};
        border-radius: {RADIUS_SM}px;
        font-weight: 500;
        font-size: 13px;
        padding: 0 16px;
        min-height: 36px;
    }}
    QPushButton#SecondaryButton:hover {{
        border-color: {p.primary};
        color: {p.primary};
    }}

    QPushButton#GhostButton {{
        background: transparent;
        color: {p.primary};
        border: none;
        font-weight: 600;
        font-size: 13px;
        padding: 0 8px;
        min-height: 32px;
    }}
    QPushButton#GhostButton:hover {{
        text-decoration: underline;
    }}

    /* Card de Lançamento */
    QFrame#EntryCard {{
        background: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: {RADIUS_MD}px;
    }}
    QLabel#EntryKind {{
        color: {p.text_secondary};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#EntryDot[kind="expense"] {{
        background: {p.expense_red};
        border-radius: 3px;
    }}
    QLabel#EntryDot[kind="income"] {{
        background: {p.income_green};
        border-radius: 3px;
    }}
    QLabel#EntryDot[kind="transfer"] {{
        background: {p.transfer_indigo};
        border-radius: 3px;
    }}

    QLineEdit#EntryTitleEdit {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {RADIUS_SM}px;
        padding: 2px 4px;
        font-size: 15px;
        font-weight: 600;
        color: {p.text_primary};
    }}
    QLineEdit#EntryAmountEdit {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {RADIUS_SM}px;
        padding: 2px 4px;
        font-size: 17px;
        font-weight: 700;
        text-align: right;
    }}
    QLineEdit#EntryTitleEdit:hover, QLineEdit#EntryAmountEdit:hover {{
        border: 1px solid {p.border_subtle};
    }}
    QLineEdit#EntryTitleEdit:focus, QLineEdit#EntryAmountEdit:focus {{
        border: 1px solid {p.primary};
        background: {p.surface_card};
    }}
    QLineEdit#EntryAmountEdit[kind="expense"] {{
        color: {p.expense_red};
    }}
    QLineEdit#EntryAmountEdit[kind="income"] {{
        color: {p.income_green};
    }}
    QLineEdit#EntryAmountEdit[kind="transfer"] {{
        color: {p.transfer_indigo};
    }}

    /* Pílulas Interativas */
    QPushButton#EntryPill {{
        background: {p.app_background};
        border: 1px solid {p.border_subtle};
        border-radius: 17px;
        padding: 0 28px 0 12px;
        color: {p.text_primary};
        font-size: 13px;
        font-weight: 500;
        text-align: left;
        min-height: 34px;
        max-height: 34px;
    }}
    QPushButton#EntryPill:hover {{
        border: 1px solid {p.primary};
    }}
    QPushButton#EntryPill[variant="fallback"] {{
        background: {p.warning_badge_bg};
        border: 1px solid {p.warning_orange};
        color: {p.warning_orange};
        font-weight: 600;
    }}
    QPushButton#EntryPill[variant="success"] {{
        background: {p.income_badge_bg};
        border: 1px solid {p.income_green};
        color: {p.income_green};
        font-weight: 600;
        padding: 0 14px;
    }}
    QPushButton#EntryPill[variant="outline"] {{
        background: {p.surface_card};
        border: 1px solid {p.border_subtle};
        color: {p.text_secondary};
        padding: 0 14px;
    }}

    QPushButton#EntryRemove {{
        background: transparent;
        border: none;
        border-radius: {RADIUS_SM}px;
        min-width: 32px;
        max-width: 32px;
        min-height: 32px;
        max-height: 32px;
    }}
    QPushButton#EntryRemove:hover {{
        background: {p.app_background};
    }}

    QPushButton#AISuggestion {{
        background: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: 16px;
        padding: 0 14px;
        min-height: 32px;
        max-height: 32px;
        font-size: 12px;
        color: {p.text_primary};
    }}
    QPushButton#AISuggestion:hover {{
        border: 1px solid {p.primary};
        color: {p.primary};
    }}

    QPushButton#DialogCloseBtn {{
        background: transparent;
        border: none;
        border-radius: {RADIUS_SM}px;
        min-width: 30px;
        max-width: 30px;
        min-height: 30px;
        max-height: 30px;
    }}
    QPushButton#DialogCloseBtn:hover {{
        background: {p.border_subtle};
    }}

    QLabel#AIStatusOk {{
        color: {p.income_green};
        font-size: 13px;
        font-weight: 600;
    }}
    QLabel#AIHint {{
        color: {p.text_secondary};
        font-size: 12px;
    }}
    QLabel#AIError {{
        color: {p.expense_red};
        font-size: 13px;
    }}
    QLabel#AIIconTile {{
        background: {p.primary_active_pill};
        border-radius: {RADIUS_MD}px;
    }}
    QLabel#AIFallbackDot {{
        background: {p.warning_orange};
        border-radius: 4px;
    }}
    """


def _repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def _kbd_badge(key_text: str, label_text: str, p: ThemePalette) -> str:
    """Gera o badge com borda arredondada para atalhos de teclado no rodapé."""
    return (
        f"<span style='background: {p.surface_card}; border: 1px solid {p.border_subtle}; "
        f"border-radius: 4px; padding: 2px 7px; font-size: 11px; font-weight: 700; "
        f"color: {p.text_primary};'>{key_text}</span> "
        f"<span style='color: {p.text_secondary}; font-size: 12px;'>{label_text}</span>"
    )


# --------------------------------------------------------------------------- #
# View Models & Estruturas de Dados
# --------------------------------------------------------------------------- #
@dataclass
class EntryViewModel:
    """Modelo de apresentação desacoplado para exibição e edição na interface."""

    kind: str  # KIND_DESPESA | KIND_RECEITA | KIND_TRANSFERENCIA
    description: str
    amount: float
    when: date
    effective: bool
    account_id: Optional[str] = None
    destination_account_id: Optional[str] = None
    card_id: Optional[str] = None
    category_id: Optional[str] = None
    fallback_fields: Set[str] = field(default_factory=set)  # {"account", "category"}


@dataclass
class EntryOptions:
    """Listas de IDs e rótulos reais do perfil ativo para as pílulas."""

    accounts: List[Option]
    cards: List[Option]
    categories: Dict[str, List[Option]]  # chave = KIND_*


def parse_brl(text: str) -> Optional[float]:
    """Converte string monetária formatada (ex.: 'R$ 12,50' ou '- 45.90') para float."""
    t = (
        text.replace("R$", "")
        .replace("−", "")
        .replace("-", "")
        .replace("+", "")
        .replace(" ", "")
        .strip()
    )
    if not t:
        return None
    if "," not in t and t.count(".") == 1 and len(t.split(".")[1]) != 3:
        t = t.replace(".", ",")
    t = t.replace(".", "").replace(",", ".")
    try:
        val = float(t)
    except ValueError:
        return None
    return val if val > 0 else None


# --------------------------------------------------------------------------- #
# Pílula Interativa (PillButton): Ícone + Texto + Chevron com pintura antialias
# --------------------------------------------------------------------------- #
class PillButton(QPushButton):
    """Pílula clicável com chevron opcional e suporte a tooltip."""

    def __init__(
        self,
        text: str,
        icon_name: Optional[str],
        palette: ThemePalette,
        *,
        chevron: bool = True,
        variant: str = "default",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("EntryPill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._raw_text = text
        self._icon_name = icon_name
        self._with_chevron = chevron
        self._p = palette
        self._chev_pm = None
        self._variant = variant
        self.setProperty("variant", variant)
        self.setToolTip(text)
        self.apply_palette(palette)

    def set_pill_text(self, text: str) -> None:
        self._raw_text = text
        self.setToolTip(text)
        self.setText(text)

    def apply_palette(self, p: ThemePalette) -> None:
        self._p = p
        if self._variant == "success":
            color = p.income_green
        elif self._variant == "fallback":
            color = p.warning_orange
        else:
            color = p.text_secondary
        if self._icon_name:
            self.setIcon(get_line_icon(self._icon_name, color=color, size=15))
        self._chev_pm = (
            get_line_pixmap("chev", color=color, size=12)
            if self._with_chevron
            else None
        )
        self.update()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self.setProperty("variant", variant)
        self.apply_palette(self._p)
        _repolish(self)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._chev_pm is not None and self._variant not in ("success", "outline"):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.drawPixmap(
                self.width() - 22, (self.height() - 12) // 2, self._chev_pm
            )
            painter.end()


# --------------------------------------------------------------------------- #
# Card de Lançamento (EntryCard)
# --------------------------------------------------------------------------- #
class _CardCheckProxy:
    """Proxy de compatibilidade para controle programático de inclusão."""

    def __init__(self, card: EntryCard):
        self._card = card
        self._checked = True

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, val: bool) -> None:  # noqa: N802
        self._checked = bool(val)


class EntryCard(QFrame):
    """Card de visualização e edição instantânea de um lançamento identificado."""

    changed = Signal()
    removed = Signal(object)  # emite o próprio card

    def __init__(
        self,
        vm: EntryViewModel,
        options: EntryOptions,
        palette: ThemePalette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EntryCard")
        self.vm = vm
        self._options = options
        self._p = palette
        self.chk = _CardCheckProxy(self)
        self._build()

    def to_entry(self):
        from app.domain.services.ai_entry_service import ResolvedEntry

        return ResolvedEntry(
            tipo=self.vm.kind,
            descricao=self.vm.description,
            valor=self.vm.amount,
            data=self.vm.when,
            id_conta=self.vm.account_id,
            id_cartao=self.vm.card_id,
            id_categoria=self.vm.category_id,
            efetivada=self.vm.effective,
            id_conta_destino=self.vm.destination_account_id,
            campos_fallback=set(self.vm.fallback_fields),
        )

    # -- helpers de rótulos e cores ----------------------------------------- #
    def _kind_text(self) -> str:
        if self.vm.kind == KIND_RECEITA:
            return "RECEITA"
        if self.vm.kind == KIND_TRANSFERENCIA:
            return "TRANSFERÊNCIA"
        return "DESPESA NO CARTÃO" if self.vm.card_id else "DESPESA"

    def _kind_key(self) -> str:
        return {
            KIND_RECEITA: "income",
            KIND_TRANSFERENCIA: "transfer",
        }.get(self.vm.kind, "expense")

    def _status_text(self) -> str:
        if self.vm.card_id:
            return "Na fatura"
        if self.vm.kind == KIND_RECEITA:
            return "Recebido" if self.vm.effective else "Pendente"
        if self.vm.kind == KIND_TRANSFERENCIA:
            return "Efetivada" if self.vm.effective else "Pendente"
        return "Pago" if self.vm.effective else "Pendente"

    def _label_of(
        self, options: Sequence[Option], opt_id: Optional[str], fallback: str
    ) -> str:
        for oid, label in options:
            if oid == opt_id:
                return label
        return fallback

    def _amount_text(self) -> str:
        sign = {KIND_DESPESA: "− ", KIND_RECEITA: "+ "}.get(self.vm.kind, "")
        return f"{sign}{format_currency(self.vm.amount)}"

    # -- construção ---------------------------------------------------------- #
    def _build(self) -> None:
        p = self._p
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 16, 14)
        root.setSpacing(6)

        # Linha 1: [Dot + TIPO EM MAIÚSCULAS] à esquerda | [VALOR EM DESTAQUE] à direita
        line1 = QHBoxLayout()
        line1.setSpacing(6)

        self.dot = QLabel()
        self.dot.setObjectName("EntryDot")
        self.dot.setFixedSize(6, 6)
        self.dot.setProperty("kind", self._kind_key())

        self.lbl_kind = QLabel(self._kind_text())
        self.lbl_kind.setObjectName("EntryKind")

        line1.addWidget(self.dot)
        line1.addWidget(self.lbl_kind)
        line1.addStretch()

        self.ed_amount = QLineEdit(self._amount_text())
        self.ed_amount.setObjectName("EntryAmountEdit")
        self.ed_amount.setProperty("kind", self._kind_key())
        self.ed_amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.ed_amount.setFixedWidth(160)
        self.ed_amount.editingFinished.connect(self._on_amount)
        line1.addWidget(self.ed_amount)
        root.addLayout(line1)

        # Linha 2: Descrição editável (15px semibold, ocupa toda a largura)
        self.ed_title = QLineEdit(self.vm.description)
        self.ed_title.setObjectName("EntryTitleEdit")
        self.ed_title.setPlaceholderText("Descrição do lançamento")
        self.ed_title.editingFinished.connect(self._on_title)
        root.addWidget(self.ed_title)

        root.addSpacing(2)

        # Linha 3: Pílulas de Origem, Destino/Categoria, Data (e Na fatura para cartão)
        line3 = QHBoxLayout()
        line3.setSpacing(8)

        # 1. Pílula de Origem (Conta ou Cartão)
        if self.vm.card_id:
            src_label = self._label_of(self._options.cards, self.vm.card_id, "Cartão")
            src_icon, src_opts = "card", self._options.cards
        else:
            src_label = self._label_of(
                self._options.accounts, self.vm.account_id, "Conta"
            )
            src_icon, src_opts = "bank", self._options.accounts
        self.pill_source = PillButton(
            src_label,
            src_icon,
            p,
            variant="fallback" if "account" in self.vm.fallback_fields else "default",
        )
        self.pill_source.clicked.connect(
            lambda: self._pick(self.pill_source, src_opts, self._set_source)
        )
        line3.addWidget(self.pill_source)

        # 2. Pílula de Destino (Somente para Transferências)
        if self.vm.kind == KIND_TRANSFERENCIA:
            dest_label = self._label_of(
                self._options.accounts, self.vm.destination_account_id, "Conta Destino"
            )
            self.pill_dest = PillButton(
                dest_label,
                "swap",
                p,
                variant="fallback"
                if "destination" in self.vm.fallback_fields
                else "default",
            )
            self.pill_dest.clicked.connect(
                lambda: self._pick(
                    self.pill_dest, self._options.accounts, self._set_destination
                )
            )
            line3.addWidget(self.pill_dest)

        # 3. Pílula de Categoria (Despesas e Receitas)
        if self.vm.kind != KIND_TRANSFERENCIA:
            cat_opts = self._options.categories.get(self.vm.kind, [])
            cat_label = self._label_of(cat_opts, self.vm.category_id, "Categoria")
            is_fallback = "category" in self.vm.fallback_fields
            if is_fallback and not cat_label.startswith("• "):
                cat_label = f"• {cat_label}"
            self.pill_cat = PillButton(
                cat_label,
                "tag",
                p,
                variant="fallback" if is_fallback else "default",
            )
            self.pill_cat.clicked.connect(
                lambda: self._pick(self.pill_cat, cat_opts, self._set_category)
            )
            line3.addWidget(self.pill_cat)

        # 4. Pílula de Data com seletor de calendário
        self.pill_date = PillButton(self.vm.when.strftime("%d/%m/%Y"), "cal", p)
        self.pill_date.clicked.connect(self._pick_date)
        line3.addWidget(self.pill_date)

        # 5. Pílula de Status (Na fatura quando cartão fica na linha 3)
        st_icon = "clock" if self.vm.card_id else "check"
        st_variant = (
            "outline"
            if self.vm.card_id
            else ("success" if self.vm.effective else "outline")
        )
        self.pill_status = PillButton(
            self._status_text(),
            st_icon,
            p,
            chevron=False,
            variant=st_variant,
        )
        if not self.vm.card_id:
            self.pill_status.clicked.connect(self._toggle_status)
        else:
            self.pill_status.setToolTip("Lançamentos no cartão são computados na fatura")
            line3.addWidget(self.pill_status)

        line3.addStretch()
        root.addLayout(line3)

        # Linha 4: Pílula de Status (Pago/Recebido) à esquerda e Botão 'x' à direita
        line4 = QHBoxLayout()
        line4.setSpacing(8)

        if not self.vm.card_id:
            line4.addWidget(self.pill_status)

        line4.addStretch()

        btn_rm = QPushButton()
        btn_rm.setObjectName("EntryRemove")
        btn_rm.setIcon(get_line_icon("x", color=p.text_secondary, size=16))
        btn_rm.setToolTip("Remover este lançamento")
        btn_rm.setAccessibleName("Remover lançamento")
        btn_rm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rm.clicked.connect(lambda: self.removed.emit(self))
        line4.addWidget(btn_rm)

        root.addLayout(line4)

    # -- interações de menu / calendário ------------------------------------ #
    def _pick(
        self,
        pill: PillButton,
        options: Sequence[Option],
        on_pick: Callable[[str, str], None],
    ) -> None:
        menu = QMenu(pill)
        current = {
            self.vm.account_id,
            self.vm.destination_account_id,
            self.vm.card_id,
            self.vm.category_id,
        }
        for opt_id, label in options:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(opt_id in current)
            act.triggered.connect(lambda _=False, i=opt_id, l=label: on_pick(i, l))
        menu.exec(pill.mapToGlobal(pill.rect().bottomLeft()))

    def _set_source(self, opt_id: str, label: str) -> None:
        if self.vm.card_id:
            self.vm.card_id = opt_id
        else:
            self.vm.account_id = opt_id
            self.vm.fallback_fields.discard("account")
            self.pill_source.set_variant("default")
        self.pill_source.set_pill_text(label)
        self.changed.emit()

    def _set_destination(self, opt_id: str, label: str) -> None:
        self.vm.destination_account_id = opt_id
        self.vm.fallback_fields.discard("destination")
        if hasattr(self, "pill_dest"):
            self.pill_dest.set_variant("default")
            self.pill_dest.set_pill_text(label)
        self.changed.emit()

    def _set_category(self, opt_id: str, label: str) -> None:
        self.vm.category_id = opt_id
        self.vm.fallback_fields.discard("category")
        self.pill_cat.set_variant("default")
        clean_label = label.lstrip("• ")
        self.pill_cat.set_pill_text(clean_label)
        self.changed.emit()

    def _pick_date(self) -> None:
        menu = QMenu(self.pill_date)
        cal = QCalendarWidget()
        cal.setSelectedDate(
            QDate(self.vm.when.year, self.vm.when.month, self.vm.when.day)
        )

        def picked(qd: QDate) -> None:
            self.vm.when = date(qd.year(), qd.month(), qd.day())
            self.pill_date.set_pill_text(self.vm.when.strftime("%d/%m/%Y"))
            menu.close()
            self.changed.emit()

        cal.clicked.connect(picked)
        action = QWidgetAction(menu)
        action.setDefaultWidget(cal)
        menu.addAction(action)
        menu.exec(self.pill_date.mapToGlobal(self.pill_date.rect().bottomLeft()))

    def _toggle_status(self) -> None:
        if self.vm.card_id:
            return
        self.vm.effective = not self.vm.effective
        self.pill_status.set_pill_text(self._status_text())
        self.pill_status.set_variant("success" if self.vm.effective else "outline")
        self.changed.emit()

    def _on_title(self) -> None:
        text = self.ed_title.text().strip()
        if text:
            self.vm.description = text
            self.changed.emit()
        else:
            self.ed_title.setText(self.vm.description)

    def _on_amount(self) -> None:
        value = parse_brl(self.ed_amount.text())
        if value is not None:
            self.vm.amount = value
            self.changed.emit()
        self.ed_amount.setText(self._amount_text())


# --------------------------------------------------------------------------- #
# ScrollArea com redimensionamento dinâmico
# --------------------------------------------------------------------------- #
class DynamicEntryScrollArea(QScrollArea):
    """ScrollArea que adapta seu sizeHint dinamicamente ao conteúdo até a altura máxima."""

    def sizeHint(self) -> QSize:
        w = self.widget()
        if w and w.layout():
            w.layout().activate()
            lay_hint = w.layout().sizeHint()
            max_h = self.maximumHeight()
            return QSize(lay_hint.width(), min(lay_hint.height() + 14, max_h))
        return super().sizeHint()


# --------------------------------------------------------------------------- #
# Diálogo Modal Principal: AIQuickEntryDialogView
# --------------------------------------------------------------------------- #
class AIQuickEntryDialogView(BaseModalDialog):
    """Diálogo modal com redesign Spotlight Raycast nativo do Plutos."""

    interpret_requested = Signal(str)
    confirmed = Signal(list)  # list[EntryViewModel]
    manual_requested = Signal()

    SUGGESTIONS = [
        ("bag", "Pão 10 cartão", "pão 10 reais no cartão de crédito hoje"),
        ("utensils", "Almoço 45,90", "almoço 45,90 no cartão hoje"),
        ("zap", "Luz 180 conta", "conta de luz 180 paga hoje"),
        ("wallet", "Salário 3500", "salário 3500 recebido hoje"),
    ]

    def __init__(
        self,
        palette: ThemePalette,
        model_name: str = "gemini-3.5-flash-lite",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("", "", min_width=680, parent=parent)
        self.setWindowTitle("Lançamento inteligente")
        self._p = palette
        self._model_name = model_name
        self._state = "input"
        self._cards: List[EntryCard] = []
        self.setStyleSheet(build_ai_entry_qss(palette))
        self._build_interface()
        self.show_input_state()

    # -- construção de layout ----------------------------------------------- #
    def _build_interface(self) -> None:
        p = self._p

        # 1. Cabeçalho com Tile de Ícone Sparkle + Títulos + Botão Fechar
        head = QHBoxLayout()
        head.setSpacing(12)

        tile = QLabel()
        tile.setObjectName("AIIconTile")
        tile.setFixedSize(40, 40)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if SPARKLE_TILE_IMG.exists():
            pm = QPixmap(str(SPARKLE_TILE_IMG)).scaled(
                40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            tile.setPixmap(pm)
        else:
            tile.setPixmap(get_line_pixmap("sparkle", color=p.primary, size=22))
        head.addWidget(tile)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        lbl_t = QLabel("Lançamento inteligente")
        lbl_t.setObjectName("SectionTitle")
        lbl_t.setStyleSheet("font-size: 18px; font-weight: 700;")
        lbl_s = QLabel("Descreva um ou vários lançamentos, do jeito que você falaria.")
        lbl_s.setObjectName("SubTitle")
        titles.addWidget(lbl_t)
        titles.addWidget(lbl_s)
        head.addLayout(titles, stretch=1)

        btn_close = QPushButton()
        btn_close.setObjectName("DialogCloseBtn")
        btn_close.setIcon(get_line_icon("x", color=p.text_secondary, size=16))
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setToolTip("Fechar (Esc)")
        btn_close.clicked.connect(self.reject)
        head.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignTop)

        self._root_lay.insertLayout(0, head)

        # 2. Caixa de Entrada Estilo Raycast Command Box
        self.input_box = QFrame()
        self.input_box.setObjectName("AIInputBox")
        box = QHBoxLayout(self.input_box)
        box.setContentsMargins(14, 10, 10, 10)
        box.setSpacing(10)

        self.txt_input = QPlainTextEdit()
        self.txt_input.setObjectName("AIInput")
        self.txt_input.setPlaceholderText(
            "Ex.: almoço 45,90 no nubank\nuber 23 cartão\nrecebi 3500 de salário"
        )
        self.txt_input.setFixedHeight(72)
        self.txt_input.installEventFilter(self)
        box.addWidget(self.txt_input, stretch=1)

        self.btn_interpret = QPushButton("Interpretar")
        self.btn_interpret.setObjectName("PrimaryButton")
        self.btn_interpret.setFixedHeight(36)
        self.btn_interpret.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_interpret.clicked.connect(self._emit_interpret)
        box.addWidget(self.btn_interpret, alignment=Qt.AlignmentFlag.AlignBottom)

        self.content_layout.addWidget(self.input_box)

        # 3. Sugestões Clicáveis com Ícones Vetoriais
        self.suggestions = QWidget()
        sug = QHBoxLayout(self.suggestions)
        sug.setContentsMargins(0, 0, 0, 0)
        sug.setSpacing(8)

        lbl_exp = QLabel("Experimente")
        lbl_exp.setObjectName("AIHint")
        sug.addWidget(lbl_exp)

        for icon_name, label, full_prompt in self.SUGGESTIONS:
            b = QPushButton(f"  {label}")
            b.setObjectName("AISuggestion")
            b.setIcon(get_line_icon(icon_name, color=p.text_secondary, size=14))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, t=full_prompt: self._use_suggestion(t))
            sug.addWidget(b)

        sug.addStretch()
        self.content_layout.addWidget(self.suggestions)

        # 4. Mensagem de Erro e Atalho de Fallback Manual
        self.lbl_error = QLabel()
        self.lbl_error.setObjectName("AIError")
        self.lbl_error.setWordWrap(True)

        self.btn_manual = QPushButton("Lançar manualmente")
        self.btn_manual.setObjectName("GhostButton")
        self.btn_manual.setIcon(get_line_icon("plus", color=p.primary, size=14))
        self.btn_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_manual.clicked.connect(self._on_manual_clicked)

        self.error_row = QWidget()
        er = QHBoxLayout(self.error_row)
        er.setContentsMargins(0, 0, 0, 0)
        er.setSpacing(8)
        er.addWidget(self.lbl_error, stretch=1)
        er.addWidget(self.btn_manual)
        self.content_layout.addWidget(self.error_row)

        # 5. Barra de Status da Prévia
        self.status_row = QWidget()
        sr = QHBoxLayout(self.status_row)
        sr.setContentsMargins(0, 2, 0, 2)
        sr.setSpacing(8)

        ic_check = QLabel()
        ic_check.setPixmap(get_line_pixmap("check", color=p.income_green, size=16))
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("AIStatusOk")
        lbl_hint = QLabel("· revise e confirme")
        lbl_hint.setObjectName("AIHint")

        sr.addWidget(ic_check)
        sr.addWidget(self.lbl_status)
        sr.addWidget(lbl_hint)
        sr.addStretch()

        self.fallback_legend = QWidget()
        fl = QHBoxLayout(self.fallback_legend)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        dot = QLabel()
        dot.setObjectName("AIFallbackDot")
        dot.setFixedSize(8, 8)
        txt = QLabel("preenchido automaticamente")
        txt.setObjectName("AIHint")
        fl.addWidget(dot)
        fl.addWidget(txt)
        sr.addWidget(self.fallback_legend)

        self.content_layout.addWidget(self.status_row)

        # 6. Lista Rolável de Cards de Lançamento
        self.scroll = DynamicEntryScrollArea()
        self.scroll.setObjectName("EntryScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.scroll.setMaximumHeight(570)

        holder = QWidget()
        holder.setObjectName("EntryList")
        self.list_lay = QVBoxLayout(holder)
        self.list_lay.setContentsMargins(0, 0, 6, 0)
        self.list_lay.setSpacing(12)
        self.list_lay.addStretch()
        self.scroll.setWidget(holder)
        self.content_layout.addWidget(self.scroll)

        # 7. Rodapé com Atalhos de Teclado e Identificação do Modelo
        foot = QVBoxLayout()
        foot.setSpacing(3)
        self.lbl_keys = QLabel()
        self.lbl_keys.setObjectName("AIHint")
        self.lbl_model = QLabel(f"via {self._model_name}")
        self.lbl_model.setObjectName("AIHint")
        foot.addWidget(self.lbl_keys)
        foot.addWidget(self.lbl_model)
        self.btn_row.insertLayout(0, foot)

    # -- API pública -------------------------------------------------------- #
    def set_model_name(self, name: str) -> None:
        self._model_name = name
        self.lbl_model.setText(f"via {name}" if name else "")

    def set_loading(self, loading: bool) -> None:
        self.btn_interpret.setEnabled(not loading)
        self.txt_input.setReadOnly(loading)
        self.btn_interpret.setText(
            "Interpretando…" if loading else self._interpret_label()
        )

    def show_error(self, message: str) -> None:
        self.lbl_error.setText(message)
        self.error_row.setVisible(True)
        self.set_loading(False)

    def show_input_state(self) -> None:
        p = self._p
        self._state = "input"
        self.suggestions.setVisible(True)
        self.status_row.setVisible(False)
        self.scroll.setVisible(False)
        self.error_row.setVisible(False)
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setText("Confirmar")
        self.lbl_keys.setText("Enter interpreta  ·  Shift+Enter nova linha")
        self.btn_interpret.setText("Interpretar")
        self.btn_interpret.setObjectName("PrimaryButton")
        _repolish(self.btn_interpret)
        self.txt_input.setFocus()
        self.adjustSize()

    def show_preview(
        self, entries: List[EntryViewModel], options: EntryOptions
    ) -> None:
        p = self._p
        self._state = "preview"
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []

        for vm in entries:
            card = EntryCard(vm, options, self._p)
            card.removed.connect(self._remove_card)
            card.changed.connect(self._refresh_footer)
            self.list_lay.insertWidget(self.list_lay.count() - 1, card)
            self._cards.append(card)

        self.suggestions.setVisible(False)
        self.error_row.setVisible(False)
        self.status_row.setVisible(True)
        self.scroll.setVisible(True)
        self.lbl_keys.setText("Enter confirma  ·  Esc volta")
        self.btn_interpret.setText("Reinterpretar")
        self.btn_interpret.setObjectName("SecondaryButton")
        _repolish(self.btn_interpret)
        self.set_loading(False)
        self._refresh_footer()
        self.btn_confirm.setFocus()
        self.adjustSize()

    def collect_entries(self) -> List[EntryViewModel]:
        return [c.vm for c in self._cards]

    def done_ok(self) -> None:
        super().accept()

    # -- métodos internos de interação -------------------------------------- #
    def _interpret_label(self) -> str:
        return "Reinterpretar" if self._state == "preview" else "Interpretar"

    def _use_suggestion(self, text: str) -> None:
        self.txt_input.setPlainText(text)
        self._emit_interpret()

    def _emit_interpret(self) -> None:
        text = self.txt_input.toPlainText().strip()
        if text:
            self.interpret_requested.emit(text)

    def _remove_card(self, card: EntryCard) -> None:
        if card in self._cards:
            self._cards.remove(card)
        card.setParent(None)
        card.deleteLater()
        if not self._cards:
            self.show_input_state()
        else:
            self._refresh_footer()

    def _refresh_footer(self) -> None:
        n = len(self._cards)
        self.lbl_status.setText(
            f"{n} lançamento{'s' if n != 1 else ''} encontrado{'s' if n != 1 else ''}"
        )
        self.btn_confirm.setEnabled(n > 0)
        self.btn_confirm.setText(
            f"Confirmar {n} lançamento{'s' if n != 1 else ''}"
        )
        self.fallback_legend.setVisible(
            any(bool(c.vm.fallback_fields) for c in self._cards)
        )

    def _on_manual_clicked(self) -> None:
        self.manual_requested.emit()
        self.reject()

    def accept(self) -> None:  # noqa: D401
        if self._state == "preview" and self._cards:
            self.confirmed.emit(self.collect_entries())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and self._state == "preview":
            self.show_input_state()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if obj is self.txt_input:
            if ev.type() == QEvent.Type.FocusIn:
                self.input_box.setProperty("focused", True)
                _repolish(self.input_box)
            elif ev.type() == QEvent.Type.FocusOut:
                self.input_box.setProperty("focused", False)
                _repolish(self.input_box)
            elif ev.type() == QEvent.Type.KeyPress and ev.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
            ):
                if not (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._emit_interpret()
                    return True
        return super().eventFilter(obj, ev)
