"""
Módulo centralizado de ícones em linha (SVG Line Icons) do Plutos.
Fornece ícones vetoriais consistentes em 18px (stroke 1.8, stroke-linecap round),
eliminando emojis e glifos inconsistentes conforme as diretrizes de design.
"""

from __future__ import annotations

from typing import Dict, Optional
from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Caminhos vetoriais extraídos 1:1 do protótipo Plutos Redesign
SVG_PATHS: Dict[str, str] = {
    "home": "M3 11l9-8 9 8v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    "bank": "M3 10l9-6 9 6M5 10v8M9 10v8M15 10v8M19 10v8M3 20h18",
    "list": "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    "card": "M2 6h20v12H2zM2 10h20",
    "pie": "M12 3v9h9A9 9 0 1 1 12 3z",
    "target": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10z",
    "file": "M6 2h9l5 5v15H6zM14 2v6h6M9 13h7M9 17h7",
    "chart": "M3 3v18h18M7 15v3M12 9v9M17 5v13",
    "folder": "M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
    "tag": "M3 12V3h9l9 9-9 9zM7.5 7.5h.01",
    "cal": "M3 5h18v16H3zM3 10h18M8 2v4M16 2v4",
    "tool": "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 4v4M8 10v4M16 16v4",
    "db": "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    "plus": "M12 5v14M5 12h14",
    "search": "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3",
    "bell": "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21h4",
    "moon": "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
    "sun": "M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z",
    "refresh": "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
    "l": "M15 18l-6-6 6-6",
    "rt": "M9 18l6-6-6-6",
    "dn": "M12 5v14M19 12l-7 7-7-7",
    "up": "M12 19V5M5 12l7-7 7 7",
    "swap": "M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7",
    "up2": "M12 3v12M7 8l5-5 5 5M4 21h16",
    "dl": "M12 3v12M7 10l5 5 5-5M4 21h16",
    "check": "M20 6L9 17l-5-5",
    "trash": "M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2",
    "edit": "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z",
    "menu": "M3 12h18M3 6h18M3 18h18",
    "sparkle": "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM19 16v4M17 18h4",
    "x": "M6 6l12 12M18 6L6 18",
    "chev": "M6 9l6 6 6-6",
    "clock": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
    "bag": "M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18M16 10a4 4 0 0 1-8 0",
    "utensils": "M18 2v20M21 2v6a3 3 0 0 1-3 3M18 5h3M6 2v7a3 3 0 0 1-3 3M6 2v20M3 2v7a3 3 0 0 0 3 3",
    "zap": "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
    "wallet": "M21 7v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2zm-5 5h.01",
}

_PIXMAP_CACHE: Dict[tuple, QPixmap] = {}


def build_svg_xml(path_d: str, color: str = "#7B8190", size: int = 18, stroke_width: float = 1.8) -> str:
    """Monta a string XML do SVG com viewport 24x24 padronizado."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{path_d}"/>'
        f'</svg>'
    )


def get_line_pixmap(
    name: str,
    color: str = "#7B8190",
    size: int = 18,
    stroke_width: float = 1.8,
) -> QPixmap:
    """Renderiza um ícone SVG para QPixmap com renderização suave e cache."""
    cache_key = (name, color, size, stroke_width)
    if cache_key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[cache_key]

    path_d = SVG_PATHS.get(name, SVG_PATHS["plus"])
    svg_xml = build_svg_xml(path_d, color, size, stroke_width)

    # Renderiza em resolução 2x para garantir nitidez em telas de alta densidade
    scale_factor = 2
    render_size = size * scale_factor

    renderer = QSvgRenderer(QByteArray(svg_xml.encode("utf-8")))
    pixmap = QPixmap(render_size, render_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()

    # Define devicePixelRatio para que o Qt exiba com nitidez perfeita
    pixmap.setDevicePixelRatio(scale_factor)
    _PIXMAP_CACHE[cache_key] = pixmap
    return pixmap


def get_line_icon(
    name: str,
    color: str = "#7B8190",
    size: int = 18,
    stroke_width: float = 1.8,
    active_color: Optional[str] = None,
) -> QIcon:
    """Retorna um QIcon com suporte a estado normal e ativo."""
    icon = QIcon()
    normal_pix = get_line_pixmap(name, color=color, size=size, stroke_width=stroke_width)
    icon.addPixmap(normal_pix, QIcon.Mode.Normal)

    if active_color:
        active_pix = get_line_pixmap(name, color=active_color, size=size, stroke_width=stroke_width)
        icon.addPixmap(active_pix, QIcon.Mode.Active)
        icon.addPixmap(active_pix, QIcon.Mode.Selected)

    return icon
