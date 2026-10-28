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
            primary="#E5603D",           # --ac: Plutos Terracotta / Laranja característico
            primary_hover="#D45230",     # Hover refinado do botão primário
            primary_active_pill="#FDECE6",# --acs: Fundo sutil do item ativo de navegação
            app_background="#F4F5F7",    # --bg: Fundo geral da aplicação
            surface_card="#FFFFFF",      # --sf: Superfície de cards e painéis
            surface_header="#FFFFFF",    # --sf: Topbar padronizada
            surface_sidebar="#FFFFFF",   # --sf: Sidebar 216px com separador de linha
            border_subtle="#E8EAEE",     # --ln: Bordas sutis
            text_primary="#1B1D22",      # --tx: Texto de alto contraste
            text_secondary="#7B8190",    # --mu: Rótulos e textos secundários
            text_muted="#7B8190",        # --mu: Textos atenuados
            income_green="#1F9D6A",      # --gr: Verde para receitas e valores positivos
            income_badge_bg="#E8F5F0",   # 16% verde srgb
            expense_red="#D64545",       # --rd: Vermelho para despesas e valores negativos
            expense_badge_bg="#FBECED",  # 16% vermelho srgb
            warning_orange="#C98A12",    # --am: Âmbar/amarelo para alertas e pendências
            warning_badge_bg="#F9F3E7",  # 16% âmbar srgb
            transfer_indigo="#3A78D8",   # --bl: Azul para transferências e informações
            transfer_badge_bg="#EBF1FB", # 16% azul srgb
        )

    @classmethod
    def dark(cls) -> "ThemePalette":
        return cls(
            mode="dark",
            primary="#E5603D",           # --ac: Laranja característico Plutos
            primary_hover="#EF7555",     # Hover primário no modo escuro
            primary_active_pill="#3A241D",# --acs: Fundo sutil ativo escuro
            app_background="#131519",    # --bg: Fundo escuro imersivo
            surface_card="#1B1E24",      # --sf: Superfície de cards escuro
            surface_header="#1B1E24",    # --sf: Topbar escuro
            surface_sidebar="#1B1E24",   # --sf: Sidebar escuro
            border_subtle="#2A2E36",     # --ln: Linhas divisórias escuras
            text_primary="#ECEEF2",      # --tx: Texto primário escuro
            text_secondary="#8B92A1",    # --mu: Texto secundário escuro
            text_muted="#8B92A1",        # --mu: Textos atenuados escuro
            income_green="#3CC08B",      # --gr: Verde vibrante para tema escuro
            income_badge_bg="#1A3328",   # Fundo suave verde no escuro
            expense_red="#EF6A6A",       # --rd: Vermelho vibrante no escuro
            expense_badge_bg="#362224",  # Fundo suave vermelho no escuro
            warning_orange="#E3A93A",    # --am: Âmbar vibrante no escuro
            warning_badge_bg="#342B1D",  # Fundo suave âmbar no escuro
            transfer_indigo="#6AA0F0",   # --bl: Azul claro vibrante no escuro
            transfer_badge_bg="#202A3C", # Fundo suave azul no escuro
        )

    @classmethod
    def for_mode(cls, mode: str) -> "ThemePalette":
        return cls.dark() if str(mode).lower() == "dark" else cls.light()


# Constantes semânticas diretas para uso em views, badges e gráficos (Estética Plutos Redesign)
PRIMARY_ACCENT = "#E5603D"
PRIMARY_BLUE = "#E5603D"  # Mantido para retrocompatibilidade
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


