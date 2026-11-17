"""
Componentes de interface globais e reutilizáveis do Plutos.
Padroniza Botões, Inputs, Cards de Métricas, Badges de Status, Modais e Empty States
conforme as diretrizes de design do protótipo Plutos Redesign.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Callable, List, Optional, Tuple
from PySide6.QtCore import QRectF, Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import ThemePalette
from app.ui.icons import get_line_icon, get_line_pixmap


class Badge(QLabel):
    """
    Badge semântico em pílula (radius 99px) para status de transações,
    contas, cartões e categorias (ex.: 'Efetivado', 'Pendente', 'Pago', 'Alerta').
    """

    VARIANTS = {
        "success": "BadgeSuccess",
        "danger": "BadgeDanger",
        "warning": "BadgeWarning",
        "info": "BadgeInfo",
        "neutral": "BadgeDefault",
    }

    def __init__(
        self,
        text: str,
        variant: str = "neutral",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.set_variant(variant)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_variant(self, variant: str) -> None:
        obj_name = self.VARIANTS.get(variant.lower(), "BadgeDefault")
        self.setObjectName(obj_name)
        self.style().unpolish(self)
        self.style().polish(self)


class KpiCard(QFrame):
    """
    Card padrão para exibição de métricas (KPIs), saldos, receitas e despesas.
    Exibe título atenuado, valor numérico tabular em destaque (26px), micro-ícone
    à direita e suporte opcional a tint semântico suave.
    """

    def __init__(
        self,
        title: str,
        value: str,
        variant: str = "neutral",
        subtitle: Optional[str] = None,
        icon_name: Optional[str] = None,
        accent_color: Optional[str] = None,
        tint: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        if tint in ("positive", "negative", "info", "warning"):
            self.setProperty("tint", tint)
        self._build_ui(title, value, variant, subtitle, icon_name, accent_color)

    def _build_ui(
        self,
        title: str,
        value: str,
        variant: str,
        subtitle: Optional[str] = None,
        icon_name: Optional[str] = None,
        accent_color: Optional[str] = None,
    ) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MutedText")
        self.lbl_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 0.04em;"
        )
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()

        if icon_name:
            lbl_ico = QLabel()
            lbl_ico.setObjectName("KpiIconPill")
            lbl_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ico_color = accent_color or (
                "#16A34A"
                if variant == "positive"
                else ("#DC2626" if variant == "negative" else "#64748B")
            )
            lbl_ico.setPixmap(get_line_pixmap(icon_name, color=ico_color, size=14))
            top_row.addWidget(lbl_ico)

        lay.addLayout(top_row)

        self.lbl_value = QLabel(value)
        self.lbl_value.setObjectName("KpiValue")
        if accent_color:
            self.lbl_value.setStyleSheet(f"color: {accent_color};")
        elif variant == "positive":
            self.lbl_value.setStyleSheet("color: #16A34A;")
        elif variant == "negative":
            self.lbl_value.setStyleSheet("color: #DC2626;")
        lay.addWidget(self.lbl_value)

        self.lbl_subtitle = QLabel(subtitle or "")
        self.lbl_subtitle.setObjectName("MutedText")
        self.lbl_subtitle.setVisible(bool(subtitle))
        lay.addWidget(self.lbl_subtitle)

    def set_title(self, text: str) -> None:
        self.lbl_title.setText(text)

    def set_value(self, value: str, variant: Optional[str] = None) -> None:
        self.update_value(value, variant)

    def set_subtitle(self, text: str) -> None:
        self.lbl_subtitle.setText(text)
        self.lbl_subtitle.setVisible(bool(text))

    def update_value(self, value: str, variant: Optional[str] = None) -> None:
        self.lbl_value.setText(value)
        if variant == "positive":
            self.lbl_value.setStyleSheet("color: #16A34A;")
        elif variant == "negative":
            self.lbl_value.setStyleSheet("color: #DC2626;")
        elif variant == "neutral":
            self.lbl_value.setStyleSheet("")


class EmptyStateWidget(QFrame):
    """
    Widget amigável para telas e tabelas vazias (ex.: 'Nenhum lançamento no mês',
    'Adicione seu primeiro cartão', 'Nenhuma tag em uso').
    """

    def __init__(
        self,
        title: str,
        subtitle: str,
        icon_name: str = "folder",
        action_text: str = "",
        action_callback: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
        action_label: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CardSurface")
        act_text = action_label or action_text
        act_cb = on_action or action_callback
        self._build_ui(title, subtitle, icon_name, act_text, act_cb)

    def _build_ui(
        self,
        title: str,
        subtitle: str,
        icon_name: str,
        action_text: str,
        action_callback: Optional[Callable[[], None]],
    ) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 40, 32, 40)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Ícone circular sutil
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(54, 54)
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setStyleSheet(
            "background-color: #EEF0FF; border-radius: 27px; color: #5B5BD6;"
        )
        self.lbl_icon.setPixmap(get_line_pixmap(icon_name, color="#5B5BD6", size=24))
        lay.addWidget(self.lbl_icon, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_title)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setObjectName("MutedText")
        self.lbl_sub.setWordWrap(True)
        self.lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.lbl_sub)

        if action_text and action_callback:
            lay.addSpacing(6)
            btn = QPushButton(action_text)
            btn.setObjectName("PrimaryButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(action_callback)
            lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)


class BaseModalDialog(QDialog):
    """
    Diálogo modal base com padrão visual coerente:
    Cabeçalho com título, subtítulo, separador sutil, área de conteúdo e barra de ações.
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        min_width: int = 480,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(min_width)

        self._root_lay = QVBoxLayout(self)
        self._root_lay.setContentsMargins(24, 20, 24, 20)
        self._root_lay.setSpacing(16)

        # Cabeçalho do modal
        if title or subtitle:
            hdr = QVBoxLayout()
            hdr.setSpacing(2)
            self._lbl_title = QLabel(title)
            self._lbl_title.setObjectName("SectionTitle")
            self._lbl_title.setStyleSheet("font-size: 18px; font-weight: 700;")
            hdr.addWidget(self._lbl_title)

            if subtitle:
                self._lbl_sub = QLabel(subtitle)
                self._lbl_sub.setObjectName("SubTitle")
                hdr.addWidget(self._lbl_sub)

            self._root_lay.addLayout(hdr)

            sep = QFrame()
            sep.setObjectName("ModalSeparator")
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setFixedHeight(1)
            self._root_lay.addWidget(sep)

        # Área de conteúdo customizado
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        self._root_lay.addWidget(self.content_widget, stretch=1)

        # Rodapé com ações primárias e secundárias
        self.btn_row = QHBoxLayout()
        self.btn_row.setSpacing(10)
        self.btn_row.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_row.addWidget(self.btn_cancel)

        self.btn_confirm = QPushButton("Confirmar")
        self.btn_confirm.setObjectName("PrimaryButton")
        self.btn_confirm.setDefault(True)
        self.btn_confirm.clicked.connect(self.accept)
        self.btn_row.addWidget(self.btn_confirm)

        self._root_lay.addLayout(self.btn_row)

    def set_confirm_text(self, text: str) -> None:
        self.btn_confirm.setText(text)

    def set_cancel_text(self, text: str) -> None:
        self.btn_cancel.setText(text)


class SegmentedBar(QFrame):
    """Barra segmentada estilo pill/aba para alternância limpa entre modos ou filtros."""

    changed = Signal(str)

    def __init__(
        self,
        items: List[Tuple[str, str]],
        active_key: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentedControl")
        self._buttons: dict[str, QPushButton] = {}
        self._current_key: str = active_key or (items[0][0] if items else "")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)

        for key, label in items:
            btn = QPushButton(label)
            btn.setObjectName("SegmentButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", key == self._current_key)
            btn.clicked.connect(lambda _=False, k=key: self.set_active(k, emit=True))
            lay.addWidget(btn)
            self._buttons[key] = btn

    @property
    def current_key(self) -> str:
        return self._current_key

    def set_active(self, key: str, *, emit: bool = False) -> None:
        if key not in self._buttons:
            return
        self._current_key = key
        for k, btn in self._buttons.items():
            btn.setProperty("active", k == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if emit:
            self.changed.emit(key)


class SideDrawer(QFrame):
    """Drawer lateral direito reutilizável para Filtros Avançados e Detalhe de Parcelas."""

    closed = Signal()

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        width: int = 360,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SideDrawer")
        self.setFixedWidth(width)
        self.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        self.lbl_eyebrow = QLabel("")
        self.lbl_eyebrow.setObjectName("MutedText")
        self.lbl_eyebrow.setStyleSheet(
            "font-size: 10px; font-weight: 700; letter-spacing: 0.06em;"
        )
        self.lbl_eyebrow.setVisible(False)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("SectionTitle")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.lbl_title.setWordWrap(True)

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setObjectName("MutedText")
        self.lbl_subtitle.setWordWrap(True)
        self.lbl_subtitle.setVisible(bool(subtitle))

        title_col.addWidget(self.lbl_eyebrow)
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_subtitle)
        hdr.addLayout(title_col, 1)

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("IconButton")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setIcon(get_line_icon("x", size=15))
        self.btn_close.setToolTip("Fechar painel")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close_drawer)
        hdr.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(hdr)

        sep = QFrame()
        sep.setObjectName("ModalSeparator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setObjectName("SideDrawerScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body_host = QWidget()
        self.body_layout = QVBoxLayout(body_host)
        self.body_layout.setContentsMargins(0, 2, 4, 2)
        self.body_layout.setSpacing(12)
        self.body_layout.addStretch()
        scroll.setWidget(body_host)
        root.addWidget(scroll, 1)

        self.footer_layout = QHBoxLayout()
        self.footer_layout.setSpacing(8)
        root.addLayout(self.footer_layout)

    def set_header(self, title: str, subtitle: str = "", eyebrow: str = "") -> None:
        self.lbl_eyebrow.setText(eyebrow.upper())
        self.lbl_eyebrow.setVisible(bool(eyebrow))
        self.lbl_title.setText(title)
        self.lbl_subtitle.setText(subtitle)
        self.lbl_subtitle.setVisible(bool(subtitle))

    def clear_body(self) -> None:
        while self.body_layout.count() > 1:
            item = self.body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_sublayout(item.layout())

    @classmethod
    def _clear_sublayout(cls, lay) -> None:
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                cls._clear_sublayout(it.layout())

    def open_drawer(self) -> None:
        self.setVisible(True)

    def close_drawer(self) -> None:
        self.setVisible(False)
        self.closed.emit()


class InstallmentMiniBar(QWidget):
    """Pílula visual compacta com contador `k/n`, micro-segmentos e clique para detalhes."""

    clicked = Signal()

    def __init__(
        self,
        current: int,
        total: int,
        accent_hex: str = "#5B5BD6",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._current = max(1, int(current))
        self._total = max(self._current, int(total))
        self._accent_hex = accent_hex
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Parcela {self._current} de {self._total} — Clique para ver detalhes")
        self.setFixedHeight(24)
        self.setMinimumWidth(104)
        self.setMaximumWidth(134)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        accent = QColor(self._accent_hex)
        pill_bg = QColor(accent)
        pill_bg.setAlpha(24)
        pill_border = QColor(accent)
        pill_border.setAlpha(72)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setPen(QPen(pill_border, 1.0))
        painter.setBrush(pill_bg)
        painter.drawRoundedRect(rect, 11.5, 11.5)

        label = f"{self._current}/{self._total}"
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(QRectF(8, 0, 34, self.height()), Qt.AlignmentFlag.AlignVCenter, label)

        # Mini-segmentos visuais proporcionais (máx. 8 blocos para legibilidade)
        blocks = min(8, self._total)
        filled_blocks = max(1, round((self._current / self._total) * blocks))
        start_x = 42.0
        block_w = 5.0
        gap = 2.0
        y = (self.height() - 8.0) / 2.0
        empty_color = QColor(accent)
        empty_color.setAlpha(45)

        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(blocks):
            painter.setBrush(accent if i < filled_blocks else empty_color)
            painter.drawRoundedRect(QRectF(start_x + i * (block_w + gap), y, block_w, 8.0), 1.5, 1.5)

        # Chevron discreto à direita
        chev_x = start_x + blocks * (block_w + gap) + 3.0
        if chev_x + 5 < self.width():
            painter.setPen(QPen(accent, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            cy = self.height() / 2.0
            painter.drawLine(int(chev_x), int(cy - 3), int(chev_x + 3), int(cy))
            painter.drawLine(int(chev_x + 3), int(cy), int(chev_x), int(cy + 3))

        painter.end()


class DonutProgressRing(QWidget):
    """Anel de progresso circular `k/n` para o Drawer de Detalhe de Parcelas."""

    def __init__(self, size: int = 84, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current = 1
        self._total = 1
        self._subtitle = "parcela atual"
        self._accent_hex = "#5B5BD6"
        self.setFixedSize(size, size)

    def set_progress(
        self,
        current: int,
        total: int,
        subtitle: str = "parcela atual",
        accent_hex: str = "#5B5BD6",
    ) -> None:
        self._current = max(0, int(current))
        self._total = max(1, int(total))
        self._subtitle = subtitle
        self._accent_hex = accent_hex
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pen_w = 7.0
        margin = pen_w / 2.0 + 3.0
        ring_rect = QRectF(margin, margin, self.width() - 2 * margin, self.height() - 2 * margin)

        track_color = QColor("#94A3B8")
        track_color.setAlpha(60)
        painter.setPen(QPen(track_color, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring_rect, 0, 360 * 16)

        ratio = min(1.0, max(0.0, self._current / self._total))
        span_angle = int(-ratio * 360 * 16)
        accent = QColor(self._accent_hex)
        painter.setPen(QPen(accent, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(ring_rect, 90 * 16, span_angle)

        # Texto central: "k/n" + subtítulo
        center_font = painter.font()
        center_font.setPointSize(11)
        center_font.setBold(True)
        painter.setFont(center_font)
        painter.setPen(self.palette().windowText().color())
        painter.drawText(
            QRectF(10, self.height() * 0.25, self.width() - 20, self.height() * 0.30),
            Qt.AlignmentFlag.AlignCenter,
            f"{self._current}/{self._total}",
        )

        sub_font = painter.font()
        sub_font.setPointSize(6)
        sub_font.setBold(False)
        painter.setFont(sub_font)
        painter.setPen(QColor("#64748B"))
        painter.drawText(
            QRectF(12, self.height() * 0.53, self.width() - 24, self.height() * 0.22),
            Qt.AlignmentFlag.AlignCenter,
            self._subtitle,
        )
        painter.end()


def compute_month_pace_pct(
    year: int, month: int, today: Optional[date] = None
) -> Tuple[int, int, float]:
    """Retorna `(dia_decorrido, dias_no_mes, ritmo_esperado_pct)` para o mês consultado."""
    ref_today = today or date.today()
    days_in_month = calendar.monthrange(int(year), int(month))[1]
    if (int(year), int(month)) < (ref_today.year, ref_today.month):
        return days_in_month, days_in_month, 100.0
    if (int(year), int(month)) > (ref_today.year, ref_today.month):
        return 0, days_in_month, 0.0
    elapsed = min(days_in_month, max(1, ref_today.day))
    return elapsed, days_in_month, round(elapsed / days_in_month * 100.0, 1)


class BudgetPaceProgressBar(QWidget):
    """Barra de progresso de orçamento com marcador vertical de ritmo esperado no mês."""

    def __init__(
        self,
        percentual: float = 0.0,
        expected_pct: float = 0.0,
        bar_color: str = "#16A34A",
        show_caption: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._percentual = max(0.0, float(percentual))
        self._expected_pct = min(100.0, max(0.0, float(expected_pct)))
        self._bar_color = bar_color
        self._show_caption = show_caption
        self.setMinimumHeight(34 if show_caption else 18)
        self.setMinimumWidth(120)

    def set_values(
        self,
        percentual: float,
        expected_pct: float,
        bar_color: Optional[str] = None,
    ) -> None:
        self._percentual = max(0.0, float(percentual))
        self._expected_pct = min(100.0, max(0.0, float(expected_pct)))
        if bar_color:
            self._bar_color = bar_color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bar_h = 8.0
        top_y = 4.0 if self._show_caption else (self.height() - bar_h) / 2.0
        left_x = 2.0
        usable_w = max(20.0, self.width() - 4.0)

        track = QColor("#94A3B8")
        track.setAlpha(55)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(left_x, top_y, usable_w, bar_h), 4.0, 4.0)

        fill_ratio = min(1.0, self._percentual / 100.0)
        if fill_ratio > 0.0:
            fill_w = max(bar_h, usable_w * fill_ratio)
            painter.setBrush(QColor(self._bar_color))
            painter.drawRoundedRect(QRectF(left_x, top_y, min(usable_w, fill_w), bar_h), 4.0, 4.0)

        # Marcador vertical de ritmo esperado (ex.: esperado 53%)
        if 0.0 < self._expected_pct <= 100.0:
            mark_x = left_x + usable_w * (self._expected_pct / 100.0)
            mark_color = self.palette().windowText().color()
            mark_color.setAlpha(210)
            painter.setPen(QPen(mark_color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(int(mark_x), int(top_y - 2), int(mark_x), int(top_y + bar_h + 2))

        if self._show_caption:
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            caption_color = QColor("#64748B")
            painter.setPen(caption_color)
            caption = f"{self._percentual:.0f}% · esperado {self._expected_pct:.0f}%"
            painter.drawText(
                QRectF(left_x, top_y + bar_h + 3.0, usable_w, 16.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                caption,
            )

        painter.end()
