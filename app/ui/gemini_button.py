"""Botão do Assistente Gemini (header) com brilho suave apenas no hover (sem custo de CPU em repouso)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QWidget

from app.config.app_settings import IMAGES_DIR

NEW_SPARKLE_TILE = IMAGES_DIR / "plutos_ai_sparkle_tile_256.png"
NEW_SPARKLE_ICON = IMAGES_DIR / "plutos_ai_sparkle_256.png"
GEMINI_ICON_PATH = IMAGES_DIR / "gemini_3d_sparkle.png"


class GeminiButton(QPushButton):
    """Botão com o ícone sparkle do Plutos; o glow suave em terracotta só anima no hover."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("GeminiButton")
        self.setFixedSize(36, 36)
        self.setIconSize(QSize(30, 30))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Lançamento Inteligente com IA  ·  Ctrl+K")
        if NEW_SPARKLE_TILE.exists():
            self.setIcon(QIcon(str(NEW_SPARKLE_TILE)))
        elif NEW_SPARKLE_ICON.exists():
            self.setIcon(QIcon(str(NEW_SPARKLE_ICON)))
        elif GEMINI_ICON_PATH.exists():
            self.setIcon(QIcon(str(GEMINI_ICON_PATH)))
        else:
            self.setText("✦")
        self.setFlat(True)
        self.setStyleSheet(
            "QPushButton#GeminiButton { background: transparent; border: none; border-radius: 18px; padding: 0; }"
        )
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setOffset(0, 0)
        self._glow.setColor(QColor(229, 96, 61, 180))
        self._glow.setBlurRadius(0)
        self.setGraphicsEffect(self._glow)
        self._anim = QPropertyAnimation(self._glow, b"blurRadius", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _animate_to(self, radius: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._glow.blurRadius())
        self._anim.setEndValue(radius)
        self._anim.start()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._animate_to(26)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._animate_to(0)
        super().leaveEvent(event)
