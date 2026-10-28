"""Gera os ícones (.ico e .png) e o logotipo editorial da marca Plutos (estética Claude)."""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)


def render_plutos_icon_image(size: int = 256) -> QImage:
    """Renderiza o ícone vetorial do Plutos (Terracota Claude #D97757 + Estrela/Moeda Grega em Linho #FAF9F5)."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    s = float(size)
    pad = s * 0.055
    rect = QRectF(pad, pad, s - 2 * pad, s - 2 * pad)
    radius = s * 0.235

    # Fundo squircle Terracota Claude com gradiente sutil
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor("#E08060"))
    grad.setColorAt(0.55, QColor("#D97757"))
    grad.setColorAt(1.0, QColor("#B9583B"))

    bg_path = QPainterPath()
    bg_path.addRoundedRect(rect, radius, radius)
    p.fillPath(bg_path, grad)

    # Borda interna sutil em creme quente
    inner_pen = QPen(QColor(250, 249, 245, 65))
    inner_pen.setWidthF(max(1.2, s * 0.014))
    p.setPen(inner_pen)
    inner_rect = rect.adjusted(s * 0.02, s * 0.02, -s * 0.02, -s * 0.02)
    p.drawRoundedRect(inner_rect, radius * 0.92, radius * 0.92)

    cx, cy = s * 0.5, s * 0.5

    # Anel clássico grego pontilhado/contínuo sutil ao redor do emblema
    ring_pen = QPen(QColor(250, 249, 245, 95))
    ring_pen.setWidthF(max(1.5, s * 0.018))
    p.setPen(ring_pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    ring_r = s * 0.31
    p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

    # Estrela / Centelha Claude de 8 pontas + Losango de riqueza (Plutos)
    star_path = QPainterPath()
    outer_r = s * 0.245
    mid_r = s * 0.145
    inner_r = s * 0.062
    points = 8
    for i in range(points * 2):
        angle = (i * math.pi / points) - (math.pi / 2.0)
        if i % 2 == 0:
            r = outer_r if (i % 4 == 0) else mid_r
        else:
            r = inner_r
        px = cx + r * math.cos(angle)
        py = cy + r * math.sin(angle)
        if i == 0:
            star_path.moveTo(px, py)
        else:
            star_path.lineTo(px, py)
    star_path.closeSubpath()

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FAF9F5"))
    p.drawPath(star_path)

    # Núcleo central em terracota escuro + ponto de luz creme
    p.setBrush(QColor("#C66444"))
    p.drawEllipse(QPointF(cx, cy), s * 0.048, s * 0.048)
    p.setBrush(QColor("#FAF9F5"))
    p.drawEllipse(QPointF(cx, cy), s * 0.022, s * 0.022)

    p.end()
    return img


def render_plutos_wordmark_image(width: int = 440, height: int = 96) -> QImage:
    """Renderiza o logotipo horizontal 'Plutos' com o ícone terracota e tipografia serifada editorial."""
    img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    icon_img = render_plutos_icon_image(84)
    p.drawImage(6, 6, icon_img)

    font_title = QFont("Georgia", 30, QFont.Weight.Bold)
    p.setFont(font_title)
    p.setPen(QColor("#2B2A27"))
    p.drawText(QRectF(102, 8, 320, 52), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "Plutos")

    font_sub = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
    font_sub.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.2)
    p.setFont(font_sub)
    p.setPen(QColor("#D97757"))
    p.drawText(QRectF(104, 54, 320, 26), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "GESTÃO DE RIQUEZA")

    p.end()
    return img


def save_multisize_ico(target_ico: Path, sizes: list[int] = [16, 24, 32, 48, 64, 128, 256]) -> None:
    """Gera um arquivo .ICO nativo do Windows contendo múltiplos tamanhos PNG."""
    png_payloads: list[tuple[int, bytes]] = []
    for sz in sizes:
        qimg = render_plutos_icon_image(sz)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        buf.close()
        png_payloads.append((sz, bytes(ba)))

    count = len(png_payloads)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + (16 * count)
    dir_entries = bytearray()
    data_blobs = bytearray()

    for sz, png_bytes in png_payloads:
        w_byte = 0 if sz >= 256 else sz
        h_byte = 0 if sz >= 256 else sz
        entry = struct.pack(
            "<BBBBHHII",
            w_byte,
            h_byte,
            0,
            0,
            1,
            32,
            len(png_bytes),
            offset,
        )
        dir_entries.extend(entry)
        data_blobs.extend(png_bytes)
        offset += len(png_bytes)

    target_ico.parent.mkdir(parents=True, exist_ok=True)
    target_ico.write_bytes(header + bytes(dir_entries) + bytes(data_blobs))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    images_dir = Path(__file__).resolve().parent.parent / "app" / "assets" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    icon_256 = render_plutos_icon_image(256)
    for png_name in ("ic_logo_plutos.png", "ic_logo_mf.png", "ic_app_logo.png"):
        icon_256.save(str(images_dir / png_name), "PNG")

    wordmark = render_plutos_wordmark_image(440, 96)
    for wm_name in ("ic_logo_plutos_nome.png", "ic_logo_mf_nome.png"):
        wordmark.save(str(images_dir / wm_name), "PNG")

    for ico_name in ("plutos.ico", "minhas_financas.ico"):
        save_multisize_ico(images_dir / ico_name)

    print("Ativos visuais da marca Plutos gerados com sucesso.")


if __name__ == "__main__":
    main()
