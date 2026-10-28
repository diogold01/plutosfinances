"""Camada de interface gráfica nativa (PySide6 / Qt6 Widgets)."""

from .main_window import MainWindow
from .style_manager import apply_app_theme, format_currency, load_bundled_fonts

__all__ = [
    "MainWindow",
    "apply_app_theme",
    "format_currency",
    "load_bundled_fonts",
]
