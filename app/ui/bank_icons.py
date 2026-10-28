"""Utilitários de ícones de bancos (160 instituições), bandeiras de cartão e avatares."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap

from app.config.app_settings import BANKS_ICONS_DIR, CREDIT_CARD_ICONS_DIR

# Nomes amigáveis para os principais bancos brasileiros
KNOWN_BANK_LABELS: Dict[str, str] = {
    "ic_nubank": "Nubank",
    "ic_itau": "Itaú Unibanco",
    "ic_itau_personnalite": "Itaú Personnalité",
    "ic_bb": "Banco do Brasil",
    "ic_bradesco": "Bradesco",
    "ic_bradesco_prime": "Bradesco Prime",
    "ic_caixa": "Caixa Econômica Federal",
    "ic_santander": "Santander",
    "ic_inter": "Banco Inter",
    "ic_c6": "C6 Bank",
    "ic_btg": "BTG Pactual",
    "ic_xp": "XP Investimentos",
    "ic_rico": "Rico Investimentos",
    "ic_clear": "Clear Corretora",
    "ic_nuinvest": "NuInvest",
    "ic_sicredi": "Sicredi",
    "ic_sicoob": "Sicoob",
    "ic_picpay": "PicPay",
    "ic_mercadopago": "Mercado Pago",
    "ic_pagbank": "PagBank / PagSeguro",
    "ic_neon": "Neon",
    "ic_next": "Next",
    "ic_sofisa": "Banco Sofisa Direto",
    "ic_daycoval": "Banco Daycoval",
    "ic_banco_pan": "Banco PAN",
    "ic_bmg": "Banco BMG",
    "ic_banrisul": "Banrisul",
    "ic_brb": "BRB - Banco de Brasília",
    "ic_bv": "Banco BV",
    "ic_safra": "Banco Safra",
    "ic_original": "Banco Original",
    "ic_nomad": "Nomad",
    "ic_wise": "Wise",
    "ic_avenue": "Avenue",
    "ic_binance": "Binance",
    "ic_alelo": "Alelo",
    "ic_sodexo": "Sodexo / Pluxee",
    "ic_vr": "VR Benefícios",
    "ic_ticket": "Ticket",
    "ic_flash": "Flash Benefícios",
    "ic_caju": "Caju Benefícios",
}


def format_bank_label(filename: str) -> str:
    """Converte o nome do arquivo (ex.: 'ic_banco_do_brasil.png') em nome legível."""
    stem = Path(filename).stem.lower()
    if stem in KNOWN_BANK_LABELS:
        return KNOWN_BANK_LABELS[stem]
    clean = stem
    if clean.startswith("ic_"):
        clean = clean[3:]
    return clean.replace("_", " ").title()


def list_available_bank_icons() -> List[Tuple[str, str, Path]]:
    """
    Retorna lista de `(filename, label_amigavel, full_path)` de todos os ícones
    de bancos em `app/assets/banks/`, priorizando os bancos mais populares no topo.
    """
    if not BANKS_ICONS_DIR.exists():
        return []

    priority_stems = list(KNOWN_BANK_LABELS.keys())
    items: List[Tuple[int, str, str, Path]] = []
    for entry in BANKS_ICONS_DIR.iterdir():
        if not entry.is_file() or entry.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        stem = entry.stem.lower()
        prio = priority_stems.index(stem) if stem in priority_stems else 999
        label = format_bank_label(entry.name)
        items.append((prio, label, entry.name, entry))

    items.sort(key=lambda x: (x[0], x[1]))
    return [(fname, label, path) for _, label, fname, path in items]


def get_bank_pixmap(image_key: str, size: int = 36) -> QPixmap:
    """Carrega o ícone do banco arredondado ou gera um avatar padrão caso não exista."""
    candidate = BANKS_ICONS_DIR / (image_key or "")
    if candidate.exists() and candidate.is_file():
        src = QPixmap(str(candidate))
        if not src.isNull():
            scaled = src.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            out = QPixmap(size, size)
            out.fill(Qt.GlobalColor.transparent)
            painter = QPainter(out)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            path.addRoundedRect(0, 0, size, size, size * 0.25, size * 0.25)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            return out

    return create_color_badge_pixmap("#2196F3", "B", size=size)


def get_bank_icon(image_key: str, size: int = 32) -> QIcon:
    return QIcon(get_bank_pixmap(image_key, size=size))


def create_color_badge_pixmap(
    hex_color: str,
    text: str = "",
    size: int = 28,
    circle: bool = True,
) -> QPixmap:
    """Gera um badge circular ou quadrado arredondado na cor informada com inicial opcional."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor(hex_color or "#2196F3")
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    if circle:
        painter.drawEllipse(1, 1, size - 2, size - 2)
    else:
        painter.drawRoundedRect(1, 1, size - 2, size - 2, 6, 6)

    if text:
        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", max(8, int(size * 0.42)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, text[:2].upper())

    painter.end()
    return pix


def create_color_badge_icon(
    hex_color: str,
    text: str = "",
    size: int = 24,
    circle: bool = True,
) -> QIcon:
    return QIcon(create_color_badge_pixmap(hex_color, text=text, size=size, circle=circle))


def get_card_brand_pixmap(brand_filename: str, size: int = 28) -> QPixmap:
    """Carrega o ícone da bandeira do cartão (`app/assets/credit_card/ic_*.png`)."""
    candidate = CREDIT_CARD_ICONS_DIR / (brand_filename or "ic_credit_card.png")
    if candidate.exists() and candidate.is_file():
        src = QPixmap(str(candidate))
        if not src.isNull():
            return src.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return create_color_badge_pixmap("#1E88E5", "CC", size=size, circle=False)


def get_card_brand_icon(brand_filename: str, size: int = 24) -> QIcon:
    return QIcon(get_card_brand_pixmap(brand_filename, size=size))


# Mapeamento heurístico de nomes de bancos/emissores para ícones em `app/assets/banks/`
_BANK_KEYWORD_TO_FILE: List[Tuple[str, str]] = [
    ("nubank", "ic_nubank.png"),
    ("ultravioleta", "ic_nubank.png"),
    ("roxinho", "ic_nubank.png"),
    ("personnalite", "ic_itau_person.png"),
    ("personnalité", "ic_itau_person.png"),
    ("itaucard", "ic_itaucard.png"),
    ("itaú", "ic_itau.png"),
    ("itau", "ic_itau.png"),
    ("bradesco prime", "ic_bradesco_prime.png"),
    ("bradesco", "ic_bradesco.png"),
    ("santander", "ic_santander.png"),
    ("ourocard", "ic_ourocard.png"),
    ("banco do brasil", "ic_bb.png"),
    ("inter", "ic_intermedium.png"),
    ("caixa", "ic_caixa.png"),
    ("c6", "ic_c_bank.png"),
    ("btg", "ic_btg_pactual.png"),
    ("xp", "ic_xp.png"),
    ("picpay", "ic_pic_pay.png"),
    ("pic pay", "ic_pic_pay.png"),
    ("mercado pago", "ic_mercadopago.png"),
    ("mercadopago", "ic_mercadopago.png"),
    ("mercado livre", "ic_mercadopago.png"),
    ("pagbank", "ic_pagseguro.png"),
    ("pagseguro", "ic_pagseguro.png"),
    ("neon", "ic_neon.png"),
    ("next", "ic_next.png"),
    ("sicredi", "ic_sicredi.png"),
    ("sicoob", "ic_sicoob.png"),
    ("pan", "ic_banco_pan.png"),
    ("safra", "ic_safra.png"),
    ("original", "ic_original.png"),
    ("will", "ic_will_bank.png"),
    ("nomad", "ic_nomad.png"),
    ("wise", "ic_wise.png"),
    ("porto", "porto_seguro.png"),
    ("votorantim", "ic_banco_votorantim.png"),
    ("banrisul", "ic_banrisul.png"),
    ("brb", "ic_brb.png"),
    ("bmg", "ic_bmg_digital.png"),
    ("alelo", "ic_alelo.png"),
    ("ticket", "ic_ticket.png"),
    ("pluxee", "ic_pluxee.png"),
    ("sodexo", "ic_pluxee.png"),
    ("caju", "ic_caju.png"),
    ("flash", "ic_banco_flash.png"),
    ("cora", "ic_cora.png"),
    ("stone", "ic_stone.png"),
    ("revolut", "ic_revolut.png"),
    ("n26", "ic_n26.png"),
    ("ame", "ic_ame_digital.png"),
    ("meliuz", "ic_meliuz.png"),
    ("méliuz", "ic_meliuz.png"),
    ("iti", "ic_iti.png"),
    ("sofisa", "ic_sofisa.png"),
    ("daycoval", "ic_daycoval.png"),
    ("agibank", "ic_agibank.png"),
    ("banese", "ic_banese.png"),
    ("banestes", "ic_banestes.png"),
    ("banpara", "ic_banpara.png"),
    ("rico", "ic_rico.png"),
    ("clear", "ic_clear.png"),
    ("genial", "ic_genial.png"),
    ("toro", "ic_toro_investimentos.png"),
]


def resolve_bank_image_key(card_name: str, account_name: str = "") -> str:
    """Identifica o arquivo de logo do banco emissor pelo nome do cartão ou da conta."""
    combined = f"{card_name or ''} {account_name or ''}".lower()
    for kw, fname in _BANK_KEYWORD_TO_FILE:
        if kw in combined:
            candidate = BANKS_ICONS_DIR / fname
            if candidate.exists():
                return fname
    padded = f" {combined} "
    if " bb " in padded or " nu " in padded:
        fname = "ic_bb.png" if " bb " in padded else "ic_nubank.png"
        if (BANKS_ICONS_DIR / fname).exists():
            return fname
    if " bv " in padded and (BANKS_ICONS_DIR / "ic_banco_votorantim.png").exists():
        return "ic_banco_votorantim.png"
    return ""


def get_card_institution_pixmap(
    card_name: str,
    brand_filename: str = "",
    color_hex: str = "#E5603D",
    account_name: str = "",
    account_image_key: str = "",
    size: int = 26,
) -> QPixmap:
    """
    Retorna um logo pequeno (24–28px) da instituição/banco do cartão:
    1. Tenta pelo nome do cartão/conta nos logos de banco (`app/assets/banks/`).
    2. Tenta pelo `account_image_key` da conta vinculada.
    3. Caso seja um cartão genérico, usa o ícone da bandeira ou badge colorido com a inicial.
    """
    bank_key = resolve_bank_image_key(card_name, account_name)
    if not bank_key and account_image_key:
        cand = BANKS_ICONS_DIR / account_image_key
        if cand.exists() and cand.is_file():
            bank_key = account_image_key

    if bank_key:
        return get_bank_pixmap(bank_key, size=size)

    if brand_filename and brand_filename != "ic_credit_card.png":
        cand_brand = CREDIT_CARD_ICONS_DIR / brand_filename
        if cand_brand.exists() and cand_brand.is_file():
            return get_card_brand_pixmap(brand_filename, size=size)

    initial = (card_name or "C").strip()[:1].upper()
    return create_color_badge_pixmap(color_hex or "#E5603D", initial, size=size, circle=False)


