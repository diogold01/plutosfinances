"""Paleta de cores oficial e conversores ARGB 32-bit extraídos da aplicação de referência."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


def argb_int_to_hex(signed_int: int | None, include_alpha: bool = False) -> str:
    """Converte um inteiro 32-bit com sinal (ex: -14575885) no formato hexadecimal (#2196F3)."""
    if signed_int is None:
        return "#2196F3"
    unsigned = int(signed_int) & 0xFFFFFFFF
    a = (unsigned >> 24) & 0xFF
    r = (unsigned >> 16) & 0xFF
    g = (unsigned >> 8) & 0xFF
    b = unsigned & 0xFF
    if include_alpha:
        return f"#{a:02X}{r:02X}{g:02X}{b:02X}"
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_argb_int(hex_color: str) -> int:
    """Converte uma cor hexadecimal (#RRGGBB ou #AARRGGBB) para inteiro 32-bit com sinal do SQLite."""
    clean = hex_color.strip().lstrip("#")
    if len(clean) == 6:
        clean = "FF" + clean
    if len(clean) != 8:
        clean = "FF2196F3"
    unsigned = int(clean, 16)
    if unsigned >= 0x80000000:
        return unsigned - 0x100000000
    return unsigned


# Paleta de cores oficial para seleção em Categorias, Subcategorias, Contas, Cartões, Metas e Tags
CATEGORY_SWATCH_COLORS: List[str] = [
    "#E5603D",  # Plutos Orange / Accent
    "#1F9D6A",  # Forest Green / Success
    "#D64545",  # Crimson Red / Danger
    "#C98A12",  # Warm Amber / Warning
    "#3A78D8",  # Royal Blue / Info
    "#2196F3",  # Primary Blue
    "#039BE5",  # Light Blue
    "#42A5F5",  # Soft Blue
    "#1E88E5",  # Deep Blue
    "#3F51B5",  # Indigo
    "#5C6BC0",  # Soft Indigo
    "#7E57C2",  # Deep Purple
    "#AB47BC",  # Purple
    "#EF5350",  # Red
    "#FFA726",  # Orange
    "#FF9800",  # Deep Orange
    "#FBC02D",  # Yellow Gold
    "#FDD835",  # Bright Yellow
    "#7CB342",  # Light Green
    "#66BB6A",  # Soft Green
    "#4CAF50",  # Green
    "#2BAF2B",  # Forest Green
    "#17A05E",  # Emerald Green
    "#26A69A",  # Teal Light
    "#009688",  # Teal
    "#00897B",  # Dark Teal
    "#00BCD4",  # Cyan
    "#8D6E63",  # Brown Light
    "#795548",  # Brown
    "#757575",  # Grey
    "#616161",  # Dark Grey
]


# Tokens estruturais de Raio (Border Radius) e Espaçamento conforme Plutos Redesign
RADIUS_SM = 8     # Botões, inputs, chips, search bar
RADIUS_MD = 12    # Cards, modais, dropdown menus
RADIUS_PILL = 99  # Badges de status, barras de progresso
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 16
SPACING_LG = 24


@dataclass(frozen=True)
class ThemePalette:
    """Tokens semânticos de cores e estilo para os modos Claro (Light) e Escuro (Dark)."""

    mode: str
    primary: str
    primary_hover: str
    primary_active_pill: str
    app_background: str
    surface_card: str
    surface_header: str
    surface_sidebar: str
    border_subtle: str
    text_primary: str
    text_secondary: str
    text_muted: str
    income_green: str
    income_badge_bg: str
    expense_red: str
    expense_badge_bg: str
    warning_orange: str
    warning_badge_bg: str
    transfer_indigo: str
    transfer_badge_bg: str

    # Propriedades de conveniência alinhadas com os nomes curtos do CSS do protótipo
    @property
    def bg(self) -> str:
        return self.app_background

    @property
    def sf(self) -> str:
        return self.surface_card

    @property
    def ln(self) -> str:
        return self.border_subtle

    @property
    def tx(self) -> str:
        return self.text_primary

    @property
    def mu(self) -> str:
        return self.text_secondary

    @property
    def ac(self) -> str:
        return self.primary

    @property
    def acs(self) -> str:
        return self.primary_active_pill

    @property
    def gr(self) -> str:
        return self.income_green

    @property
    def rd(self) -> str:
        return self.expense_red

    @property
    def am(self) -> str:
        return self.warning_orange

    @property
    def bl(self) -> str:
        return self.transfer_indigo

    @classmethod
    def light(cls) -> "ThemePalette":
        return cls(
            mode="light",
            primary="#5B5BD6",            # --ac: Índigo Artha primário
            primary_hover="#4A4AC4",      # Hover refinado do botão primário
            primary_active_pill="#EEF0FF",# --acs: Fundo suave do item ativo de navegação
            app_background="#F8FAFC",     # --bg: Fundo claro SaaS (cool slate)
            surface_card="#FFFFFF",       # --sf: Superfície de cards e painéis
            surface_header="#FFFFFF",     # --sf: Topbar padronizada
            surface_sidebar="#FFFFFF",    # --sf: Sidebar 216px com separador sutil
            border_subtle="#E2E8F0",      # --ln: Bordas sutis nítidas (1px)
            text_primary="#0F172A",       # --tx: Texto principal de alto contraste
            text_secondary="#64748B",     # --mu: Rótulos e textos secundários (WCAG AA)
            text_muted="#64748B",         # --mu: Textos atenuados
            income_green="#16A34A",       # --gr: Verde esmeralda para receitas
            income_badge_bg="#DCFCE7",    # Fundo pastel verde
            expense_red="#DC2626",        # --rd: Vermelho para despesas
            expense_badge_bg="#FEE2E2",   # Fundo pastel vermelho
            warning_orange="#D97706",     # --am: Âmbar para alertas e pendências
            warning_badge_bg="#FEF3C7",   # Fundo pastel âmbar
            transfer_indigo="#4F46E5",    # --bl: Índigo para transferências e destaques
            transfer_badge_bg="#EEF2FF",  # Fundo pastel índigo
        )

    @classmethod
    def dark(cls) -> "ThemePalette":
        return cls(
            mode="dark",
            primary="#6366F1",            # --ac: Índigo Artha vibrante no modo escuro
            primary_hover="#7578F5",      # Hover primário no modo escuro
            primary_active_pill="#23254A",# --acs: Fundo sutil ativo escuro
            app_background="#0F1117",     # --bg: Fundo escuro imersivo
            surface_card="#181B23",       # --sf: Superfície de cards escuro
            surface_header="#181B23",     # --sf: Topbar escuro
            surface_sidebar="#181B23",    # --sf: Sidebar escuro
            border_subtle="#282D3A",      # --ln: Linhas divisórias escuras
            text_primary="#F1F5F9",       # --tx: Texto primário escuro (contraste > 13:1)
            text_secondary="#94A3B8",     # --mu: Texto secundário escuro legível (WCAG AA)
            text_muted="#94A3B8",         # --mu: Textos atenuados escuro legível (WCAG AA)
            income_green="#3CC08B",       # --gr: Verde vibrante para tema escuro
            income_badge_bg="#163326",    # Fundo suave verde no escuro
            expense_red="#F87171",        # --rd: Vermelho vibrante no escuro
            expense_badge_bg="#361E22",   # Fundo suave vermelho no escuro
            warning_orange="#FBBF24",     # --am: Âmbar vibrante no escuro
            warning_badge_bg="#342A18",   # Fundo suave âmbar no escuro
            transfer_indigo="#818CF8",    # --bl: Índigo claro vibrante no escuro
            transfer_badge_bg="#1E2238",  # Fundo suave índigo no escuro
        )

    @classmethod
    def for_mode(cls, mode: str) -> "ThemePalette":
        return cls.dark() if str(mode).lower() == "dark" else cls.light()


# Constantes semânticas diretas para uso em views, badges e gráficos (Estética Artha Indigo)
PRIMARY_ACCENT = "#5B5BD6"
PRIMARY_BLUE = "#5B5BD6"  # Mantido para retrocompatibilidade
INCOME_GREEN = "#1F9D6A"
EXPENSE_RED = "#D64545"
WARNING_ORANGE = "#C98A12"
WARNING_AMBER = "#C98A12"
TRANSFER_AMBER = "#3A78D8"
TRANSFER_BLUE = "#3A78D8"
CATEGORY_SWATCHES = [
    "#E5603D",  # Plutos Terracotta / Laranja característico
    "#1F9D6A",  # Forest Green
    "#D64545",  # Warm Crimson
    "#C98A12",  # Warm Ochre / Amber
    "#3A78D8",  # Royal Blue
    *CATEGORY_SWATCH_COLORS,
]


