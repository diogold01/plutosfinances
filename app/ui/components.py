"""
Componentes de interface globais e reutilizáveis do Plutos.
Padroniza Botões, Inputs, Cards de Métricas, Badges de Status, Modais e Empty States
conforme as diretrizes de design do protótipo Plutos Redesign.
"""

from __future__ import annotations

import calendar
import math
from datetime import date
from typing import Callable, List, Optional, Tuple
from PySide6.QtCore import QEvent, QRectF, Qt, QSize, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import ThemePalette
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import get_current_ui_zoom


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
        self.setMinimumHeight(84)
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
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        if icon_name:
            lbl_ico = QLabel()
            lbl_ico.setObjectName("KpiIconPill")
            lbl_ico.setFixedSize(36, 36)
            lbl_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ico_color = accent_color or (
                "#16A34A"
                if variant == "positive"
                else ("#DC2626" if variant == "negative" else "#6366F1")
            )
            c = QColor(ico_color)
            if c.isValid():
                lbl_ico.setStyleSheet(
                    f"background-color: rgba({c.red()}, {c.green()}, {c.blue()}, 32); "
                    "border-radius: 10px;"
                )
            lbl_ico.setPixmap(get_line_pixmap(icon_name, color=ico_color, size=18))
            lay.addWidget(lbl_ico, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MutedText")
        self.lbl_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 0.04em;"
        )
        text_col.addWidget(self.lbl_title)

        self.lbl_value = QLabel(value)
        self.lbl_value.setObjectName("KpiValue")
        if accent_color:
            self.lbl_value.setStyleSheet(f"color: {accent_color}; font-size: 19px; font-weight: 700;")
        elif variant == "positive":
            self.lbl_value.setStyleSheet("color: #16A34A; font-size: 19px; font-weight: 700;")
        elif variant == "negative":
            self.lbl_value.setStyleSheet("color: #DC2626; font-size: 19px; font-weight: 700;")
        text_col.addWidget(self.lbl_value)

        self.lbl_subtitle = QLabel(subtitle or "")
        self.lbl_subtitle.setObjectName("MutedText")
        self.lbl_subtitle.setStyleSheet("font-size: 11px;")
        self.lbl_subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self.lbl_subtitle)

        lay.addLayout(text_col, 1)

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
        overlay: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._drawer_width = int(width)
        self._overlay = bool(overlay)
        self._scrim: Optional[QFrame] = None
        self.setObjectName("SideDrawer")
        self.setProperty("overlay", self._overlay)
        self.setFixedWidth(self._drawer_width)
        if self._overlay and parent is not None:
            self._scrim = QFrame(parent)
            self._scrim.setObjectName("DrawerScrim")
            self._scrim.setVisible(False)
            self._scrim.mousePressEvent = lambda ev: self.close_drawer()  # type: ignore[method-assign]
            parent.installEventFilter(self)
        self.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 4)
        hdr.setSpacing(12)
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        self.lbl_eyebrow = QLabel("")
        self.lbl_eyebrow.setObjectName("MutedText")
        self.lbl_eyebrow.setStyleSheet(
            "color: #5B5BD6; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;"
        )
        self.lbl_eyebrow.setVisible(False)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("SectionTitle")
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.lbl_title.setWordWrap(True)

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setObjectName("MutedText")
        self.lbl_subtitle.setStyleSheet("font-size: 12px;")
        self.lbl_subtitle.setWordWrap(True)
        self.lbl_subtitle.setVisible(bool(subtitle))

        title_col.addWidget(self.lbl_eyebrow)
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_subtitle)
        hdr.addLayout(title_col, 1)

        self.btn_close = QPushButton()
        self.btn_close.setObjectName("IconButton")
        self.btn_close.setFixedSize(32, 32)
        self.btn_close.setIcon(get_line_icon("x", size=16))
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
        self.body_layout.setContentsMargins(2, 6, 8, 8)
        self.body_layout.setSpacing(8)
        self.body_layout.addStretch()
        scroll.setWidget(body_host)
        root.addWidget(scroll, 1)

        self.footer_layout = QHBoxLayout()
        self.footer_layout.setContentsMargins(0, 8, 0, 0)
        self.footer_layout.setSpacing(10)
        root.addLayout(self.footer_layout)

    @property
    def scrim(self) -> Optional[QFrame]:
        return self._scrim

    def _sync_overlay_geometry(self) -> None:
        if not self._overlay:
            return
        host = self.parentWidget()
        if host is None:
            return
        hh = max(320, host.height())
        if self._scrim is not None:
            self._scrim.setGeometry(0, 0, host.width(), hh)
        self.setGeometry(max(0, host.width() - self._drawer_width), 0, self._drawer_width, hh)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if self._overlay and watched is self.parentWidget():
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                if self.isVisible():
                    self._sync_overlay_geometry()
        return super().eventFilter(watched, event)

    def setVisible(self, visible: bool) -> None:  # noqa: N802
        if not visible and self._scrim is not None:
            self._scrim.setVisible(False)
        if visible and self._overlay:
            self._sync_overlay_geometry()
            if self._scrim is not None:
                self._scrim.setVisible(True)
                self._scrim.raise_()
        super().setVisible(visible)
        if visible and self._overlay:
            self.raise_()

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

    def populate_installment_series(
        self,
        occ,
        series: List[dict],
        theme_mode: str = "light",
        on_open_bill: Optional[Callable[[], None]] = None,
    ) -> None:
        """Popula o drawer com anel de progresso e timeline espaçada estilo Arthas."""
        from app.config.theme_palette import INCOME_GREEN, PRIMARY_BLUE
        from app.domain.models import KIND_DESPESA
        from app.ui.style_manager import PT_BR_MONTHS, format_currency

        total_n = max(occ.num_parcelas, len(series))
        eyebrow = f"{'COMPRA' if occ.kind == KIND_DESPESA else 'RECEITA'} PARCELADA · {total_n}×"
        source_txt = occ.cartao_nome or occ.conta_nome or ""
        self.set_header(occ.descricao, source_txt, eyebrow=eyebrow)
        self.clear_body()

        while self.footer_layout.count():
            it = self.footer_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        pal = ThemePalette.for_mode(theme_mode)
        lay = self.body_layout

        # Bloco superior espaçado: DonutProgressRing + Resumo numérico
        top_card = QFrame()
        top_card.setObjectName("InstallmentSummaryBlock")
        top_card.setStyleSheet(
            f"QFrame#InstallmentSummaryBlock {{ background: transparent; border: none; border-bottom: 1px solid {pal.border_subtle}; border-radius: 0px; }}"
        )
        top_h = QHBoxLayout(top_card)
        top_h.setContentsMargins(6, 6, 6, 18)
        top_h.setSpacing(22)

        accent_hex = PRIMARY_BLUE if occ.kind == KIND_DESPESA else INCOME_GREEN
        ring = DonutProgressRing(size=96)
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
        stats_grid.setVerticalSpacing(10)
        stats_grid.setHorizontalSpacing(16)

        def _add_stat(r_idx: int, label_txt: str, val_txt: str, sub_txt: str = "", val_color: str = "") -> None:
            l_col = QVBoxLayout()
            l_col.setContentsMargins(0, 0, 0, 0)
            l_col.setSpacing(2)
            l1 = QLabel(label_txt)
            l1.setObjectName("MutedText")
            l1.setStyleSheet("font-size: 11px; font-weight: 500;")
            l_col.addWidget(l1)
            if sub_txt:
                l2 = QLabel(sub_txt)
                l2.setObjectName("MutedText")
                l2.setStyleSheet("font-size: 10px;")
                l_col.addWidget(l2)
            v_lbl = QLabel(val_txt)
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            v_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: 700; {f'color: {val_color};' if val_color else ''}"
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

        current_year_group: Optional[int] = None
        total_series_len = len(series)

        for idx_item, item in enumerate(series):
            n_cur = int(item["num_parcela"])
            is_cur = item["id"] == occ.id or n_cur == occ.num_parcela
            dt: Optional[date] = item["data_vencimento"]
            mon_lbl = PT_BR_MONTHS.get(dt.month, "")[:3] if dt else "—"

            if dt and dt.year != current_year_group:
                current_year_group = dt.year
                lbl_yr = QLabel(str(current_year_group))
                lbl_yr.setObjectName("MutedText")
                lbl_yr.setStyleSheet("font-size: 11px; font-weight: 700; padding: 12px 0 4px 4px;")
                lay.insertWidget(lay.count() - 1, lbl_yr)

            is_paid = bool(item["efetivada"] or n_cur < occ.num_parcela)
            state = "current" if is_cur else ("paid" if is_paid else "future")

            row_card = QFrame()
            row_card.setObjectName("TimelineItemCard")
            row_card.setProperty("current", is_cur)
            row_card.setMinimumHeight(54)
            rh = QHBoxLayout(row_card)
            rh.setContentsMargins(12, 10, 14, 10)
            rh.setSpacing(14)

            marker = TimelineStepMarker(
                state=state,
                is_first=(idx_item == 0),
                is_last=(idx_item == total_series_len - 1),
                accent_hex=accent_hex,
                line_hex=pal.border_subtle,
            )
            rh.addWidget(marker)

            lbl_m = QLabel(mon_lbl)
            lbl_m.setMinimumWidth(34)
            lbl_m.setObjectName("MutedText" if not is_cur else "")
            lbl_m.setStyleSheet("font-size: 12px; font-weight: 700;" if is_cur else "font-size: 12px; font-weight: 600;")
            rh.addWidget(lbl_m)

            mid_col = QVBoxLayout()
            mid_col.setContentsMargins(0, 0, 0, 0)
            mid_col.setSpacing(3)
            lbl_p = QLabel(f"Parcela {n_cur}/{total_n}")
            lbl_p.setStyleSheet("font-size: 13px; font-weight: 700;" if is_cur else "font-size: 13px; font-weight: 600;")
            if occ.is_card and dt:
                if state == "future":
                    sub_tl = f"fatura de {PT_BR_MONTHS.get(dt.month, '').lower()} de {dt.year}"
                else:
                    sub_tl = f"fatura vence {dt.strftime('%d/%m')}"
            elif dt:
                sub_tl = f"vencimento {dt.strftime('%d/%m/%Y')}"
            else:
                sub_tl = ""
            lbl_s = QLabel(sub_tl)
            lbl_s.setObjectName("MutedText")
            lbl_s.setStyleSheet("font-size: 11px;")
            mid_col.addWidget(lbl_p)
            mid_col.addWidget(lbl_s)
            rh.addLayout(mid_col, 1)

            right_col = QVBoxLayout()
            right_col.setContentsMargins(0, 0, 0, 0)
            right_col.setSpacing(4)
            right_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_v = QLabel(format_currency(item["valor"]))
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignRight)
            lbl_v.setStyleSheet(
                f"font-size: 13px; font-weight: 700; {f'color: {accent_hex};' if is_cur else ''}"
            )
            right_col.addWidget(lbl_v)

            if is_cur:
                tag = QLabel("FATURA ATUAL" if occ.is_card else "PARCELA ATUAL")
                tag.setObjectName("TimelineTagCurrent")
            elif is_paid:
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

        if occ.is_card and on_open_bill is not None:
            cur_dt = occ.data_vencimento
            m_name = PT_BR_MONTHS.get(cur_dt.month, "").lower()
            btn_open_bill = QPushButton(f"Abrir fatura de {m_name} de {cur_dt.year}")
            btn_open_bill.setObjectName("PrimaryButton")
            btn_open_bill.setMinimumHeight(42)
            btn_open_bill.clicked.connect(on_open_bill)
            self.footer_layout.addWidget(btn_open_bill, 1)

    def open_drawer(self) -> None:
        self.setVisible(True)

    def close_drawer(self) -> None:
        self.setVisible(False)
        self.closed.emit()


class FilterCountPill(QPushButton):
    """Pílula cápsula arredondada estilo Arthas (`Tudo [34]`, `• Receitas [8]`, `• Despesas [24]`)."""

    def __init__(
        self,
        text: str = "",
        dot_color: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self._dot_color = dot_color
        self.setObjectName("CountPillChip")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self._recalc_width()

    def _split_parts(self) -> Tuple[str, str]:
        raw = (self.text() or "").strip()
        if " " in raw:
            lbl, cnt = raw.rsplit(" ", 1)
            return lbl, cnt
        return raw, ""

    def _recalc_width(self) -> None:
        z = get_current_ui_zoom()
        lbl, cnt = self._split_parts()
        f_lbl = QFont(self.font())
        f_lbl.setPixelSize(max(9, int(round(12 * z))))
        f_lbl.setWeight(QFont.Weight.DemiBold)
        f_cnt = QFont(self.font())
        f_cnt.setPixelSize(max(8, int(round(11 * z))))
        f_cnt.setWeight(QFont.Weight.Bold)

        fm_l = QFontMetrics(f_lbl)
        fm_c = QFontMetrics(f_cnt)
        pad_x = int(round(14 * z))
        dot_space = int(round(13 * z)) if self._dot_color else 0
        cnt_w = max(int(round(20 * z)), fm_c.horizontalAdvance(cnt) + int(round(12 * z))) if cnt else 0
        gap_cnt = int(round(7 * z)) if cnt else 0
        w = pad_x + dot_space + fm_l.horizontalAdvance(lbl) + gap_cnt + cnt_w + pad_x
        self.setFixedHeight(max(22, int(round(32 * z))))
        self.setFixedWidth(max(int(round(64 * z)), w))

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._recalc_width()

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self._recalc_width()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        z = get_current_ui_zoom()
        is_dark = QApplication.palette().window().color().lightness() < 128
        pal = ThemePalette.dark() if is_dark else ThemePalette.light()
        raw_act = self.property("active")
        active = raw_act is True or str(raw_act).lower() == "true"

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        radius = (self.height() - 1.0) / 2.0

        if active:
            bg = QColor("#E2E8F0" if is_dark else "#0F172A")
            fg = QColor("#0F172A" if is_dark else "#FFFFFF")
            badge_bg = QColor(15, 23, 42, 34) if is_dark else QColor(255, 255, 255, 42)
            badge_fg = fg
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, radius, radius)
        else:
            bg = QColor(pal.surface_card)
            border_c = QColor(pal.primary if self.underMouse() else pal.border_subtle)
            fg = QColor(pal.text_primary)
            badge_bg = QColor("#252B3B" if is_dark else "#F1F5F9")
            badge_fg = QColor(pal.text_secondary)
            painter.setPen(QPen(border_c, 1.0))
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, radius, radius)

        lbl, cnt = self._split_parts()
        cur_x = float(round(14.0 * z))
        cy = self.height() / 2.0

        if self._dot_color:
            dot_c = QColor(self._dot_color)
            dot_d = max(4.5, 6.4 * z)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_c)
            painter.drawEllipse(QRectF(cur_x, cy - dot_d / 2.0, dot_d, dot_d))
            cur_x += float(round(13.0 * z))

        f_lbl = QFont(self.font())
        f_lbl.setPixelSize(max(9, int(round(12 * z))))
        f_lbl.setWeight(QFont.Weight.DemiBold)
        painter.setFont(f_lbl)
        painter.setPen(fg)
        lbl_w = float(QFontMetrics(f_lbl).horizontalAdvance(lbl))
        painter.drawText(
            QRectF(cur_x, 0.0, lbl_w + 2.0, float(self.height())),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            lbl,
        )
        cur_x += lbl_w + float(round(7.0 * z))

        if cnt:
            f_cnt = QFont(self.font())
            f_cnt.setPixelSize(max(8, int(round(11 * z))))
            f_cnt.setWeight(QFont.Weight.Bold)
            cnt_w = float(max(int(round(20 * z)), QFontMetrics(f_cnt).horizontalAdvance(cnt) + int(round(12 * z))))
            cnt_h = max(13.0, float(round(18.0 * z)))
            cnt_r = cnt_h / 2.0
            cnt_rect = QRectF(cur_x, cy - cnt_r, cnt_w, cnt_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(cnt_rect, cnt_r, cnt_r)
            painter.setFont(f_cnt)
            painter.setPen(badge_fg)
            painter.drawText(cnt_rect, Qt.AlignmentFlag.AlignCenter, cnt)

        painter.end()


class InstallmentMiniBar(QWidget):
    """Linha do tempo de pontos inline das parcelas: `[●─●─●─●─◉─○─○─○] 8/12` (sem fundo/pílula)."""

    clicked = Signal()

    PAID_HEX = "#7F77DD"
    CURRENT_RING_HEX = "#AFA9EC"
    FINAL_DOT_HEX = "#1D9E75"
    FINAL_RING_HEX = "#9FE1CB"
    MAX_DOTS = 12
    DOT_SIZE = 8.0
    LINE_WIDTH = 6.0
    LINE_HEIGHT = 1.5

    def __init__(
        self,
        current: int,
        total: int,
        accent_hex: str = "#7F77DD",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._current = max(1, int(current))
        self._total = max(self._current, int(total))
        self._accent_hex = accent_hex
        self._ring_alpha: float = 1.0
        self._pulse_anim: Optional[QVariantAnimation] = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Ver as {self._total} parcelas")
        self._update_fixed_size()

        if not self.is_final_installment:
            anim = QVariantAnimation(self)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(1800)
            anim.setLoopCount(-1)
            anim.valueChanged.connect(self._on_pulse_step)
            self._pulse_anim = anim

    @property
    def dots_count(self) -> int:
        return min(self.MAX_DOTS, self._total)

    @property
    def is_final_installment(self) -> bool:
        return self._current >= self._total

    @property
    def current_dot_index(self) -> int:
        if self._total <= self.MAX_DOTS:
            return max(0, min(self.dots_count - 1, self._current - 1))
        if self._current <= 1:
            return 0
        if self._current >= self._total:
            return self.MAX_DOTS - 1
        ratio = (self._current - 1) / float(self._total - 1)
        return max(1, min(self.MAX_DOTS - 2, round(ratio * (self.MAX_DOTS - 1))))

    def _on_pulse_step(self, value) -> None:
        t = float(value)
        self._ring_alpha = 0.5 * (1.0 + math.cos(2.0 * math.pi * t))
        self.update()

    def _update_fixed_size(self) -> None:
        dots_n = self.dots_count
        dots_span = dots_n * self.DOT_SIZE + max(0, dots_n - 1) * self.LINE_WIDTH
        f = QFont(self.font())
        f.setPixelSize(12)
        txt_w = QFontMetrics(f).horizontalAdvance(f"{self._current}/{self._total}")
        total_w = int(math.ceil(4.0 + dots_span + 7.0 + txt_w + 4.0))
        self.setFixedSize(max(44, total_w), 20)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._pulse_anim is not None and self._pulse_anim.state() != QVariantAnimation.State.Running:
            self._pulse_anim.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        if self._pulse_anim is not None and self._pulse_anim.state() == QVariantAnimation.State.Running:
            self._pulse_anim.stop()
        super().hideEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        is_dark = QApplication.palette().window().color().lightness() < 128
        pal = ThemePalette.dark() if is_dark else ThemePalette.light()

        paid_col = QColor(self.PAID_HEX)
        empty_border_col = (
            QColor(pal.border_subtle).lighter(185)
            if is_dark
            else QColor(pal.border_subtle).darker(112)
        )
        text_col = QColor(pal.text_secondary)

        dots_n = self.dots_count
        cur_idx = self.current_dot_index
        cy = self.height() / 2.0
        start_x = 4.0
        step = self.DOT_SIZE + self.LINE_WIDTH  # 14.0px

        # 1. Linhas conectoras (6px largura x 1.5px altura)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(dots_n - 1):
            cx_i = start_x + 4.0 + i * step
            seg_col = paid_col if i < cur_idx else empty_border_col
            painter.setBrush(seg_col)
            painter.drawRect(QRectF(cx_i + 4.0, cy - self.LINE_HEIGHT / 2.0, self.LINE_WIDTH, self.LINE_HEIGHT))

        # 2. Pontos (8px diâmetro) + anel externo na parcela atual
        for i in range(dots_n):
            cx_i = start_x + 4.0 + i * step
            if i < cur_idx:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(paid_col)
                painter.drawEllipse(QRectF(cx_i - 4.0, cy - 4.0, 8.0, 8.0))
            elif i == cur_idx:
                if self.is_final_installment:
                    ring_col = QColor(self.FINAL_RING_HEX)
                    painter.setPen(QPen(ring_col, 2.0))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QRectF(cx_i - 6.0, cy - 6.0, 12.0, 12.0))

                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(self.FINAL_DOT_HEX))
                    painter.drawEllipse(QRectF(cx_i - 4.0, cy - 4.0, 8.0, 8.0))
                else:
                    ring_col = QColor(self.CURRENT_RING_HEX)
                    ring_col.setAlpha(max(0, min(255, int(round(255.0 * self._ring_alpha)))))
                    painter.setPen(QPen(ring_col, 2.0))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(QRectF(cx_i - 6.0, cy - 6.0, 12.0, 12.0))

                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(paid_col)
                    painter.drawEllipse(QRectF(cx_i - 4.0, cy - 4.0, 8.0, 8.0))
            else:
                painter.setPen(QPen(empty_border_col, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QRectF(cx_i - 3.25, cy - 3.25, 6.5, 6.5))

        # 3. Texto "atual/total" em 12px à direita na cor secundária do tema
        dots_span = dots_n * self.DOT_SIZE + max(0, dots_n - 1) * self.LINE_WIDTH
        text_x = start_x + dots_span + 7.0
        f = QFont(painter.font())
        f.setPixelSize(12)
        f.setWeight(QFont.Weight.Medium)
        painter.setFont(f)
        painter.setPen(text_col)
        painter.drawText(
            QRectF(text_x, 0.0, max(20.0, self.width() - text_x), float(self.height())),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{self._current}/{self._total}",
        )

        painter.end()


class TimelineStepMarker(QWidget):
    """Indicador vertical de nó da timeline (linha superior/inferior + ponto de estado)."""

    def __init__(
        self,
        state: str = "future",
        is_first: bool = False,
        is_last: bool = False,
        accent_hex: str = "#5B5BD6",
        line_hex: str = "#CBD5E1",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._state = state  # "paid" | "current" | "future"
        self._is_first = is_first
        self._is_last = is_last
        self._accent_hex = accent_hex
        self._line_hex = line_hex
        self.setFixedWidth(20)
        self.setMinimumHeight(48)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0

        line_col = QColor(self._line_hex)
        painter.setPen(QPen(line_col, 1.6))
        if not self._is_first:
            painter.drawLine(int(cx), 0, int(cx), int(cy - 6))
        if not self._is_last:
            painter.drawLine(int(cx), int(cy + 6), int(cx), self.height())

        accent = QColor(self._accent_hex)
        inner_bg = self.palette().base().color()
        if self._state == "paid":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(QRectF(cx - 4.0, cy - 4.0, 8.0, 8.0))
        elif self._state == "current":
            painter.setPen(QPen(accent, 2.2))
            painter.setBrush(inner_bg)
            painter.drawEllipse(QRectF(cx - 5.5, cy - 5.5, 11.0, 11.0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(QRectF(cx - 2.4, cy - 2.4, 4.8, 4.8))
        else:
            painter.setPen(QPen(line_col, 1.6))
            painter.setBrush(inner_bg)
            painter.drawEllipse(QRectF(cx - 4.0, cy - 4.0, 8.0, 8.0))

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
        center_font.setPointSize(12)
        center_font.setBold(True)
        painter.setFont(center_font)
        painter.setPen(self.palette().windowText().color())
        painter.drawText(
            QRectF(10, self.height() * 0.24, self.width() - 20, self.height() * 0.30),
            Qt.AlignmentFlag.AlignCenter,
            f"{self._current}/{self._total}",
        )

        sub_font = painter.font()
        sub_font.setPointSize(7)
        sub_font.setBold(False)
        painter.setFont(sub_font)
        painter.setPen(QColor("#64748B"))
        painter.drawText(
            QRectF(12, self.height() * 0.54, self.width() - 24, self.height() * 0.22),
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
