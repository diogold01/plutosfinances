"""
Componentes de interface globais e reutilizáveis do Plutos.
Padroniza Botões, Inputs, Cards de Métricas, Badges de Status, Modais e Empty States
conforme as diretrizes de design do protótipo Plutos Redesign.
"""

from __future__ import annotations

from typing import Callable, Optional
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
    Exibe título atenuado, valor numérico tabular em destaque (26px) e indicador sutil.
    """

    def __init__(
        self,
        title: str,
        value: str,
        variant: str = "neutral",
        subtitle: Optional[str] = None,
        icon_name: Optional[str] = None,
        accent_color: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
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
        lay.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        if icon_name:
            lbl_ico = QLabel()
            lbl_ico.setPixmap(get_line_pixmap(icon_name, color=accent_color or "#7B8190", size=14))
            top_row.addWidget(lbl_ico)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("MutedText")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()
        lay.addLayout(top_row)

        self.lbl_value = QLabel(value)
        self.lbl_value.setObjectName("KpiValue")
        if accent_color:
            self.lbl_value.setStyleSheet(f"color: {accent_color};")
        elif variant == "positive":
            self.lbl_value.setStyleSheet("color: #1F9D6A;")
        elif variant == "negative":
            self.lbl_value.setStyleSheet("color: #D64545;")
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
            self.lbl_value.setStyleSheet("color: #1F9D6A;")
        elif variant == "negative":
            self.lbl_value.setStyleSheet("color: #D64545;")
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
            "background-color: #FDECE6; border-radius: 27px; color: #E5603D;"
        )
        self.lbl_icon.setPixmap(get_line_pixmap(icon_name, color="#E5603D", size=24))
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
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: transparent; border-bottom: 1px solid #E8EAEE;")
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
