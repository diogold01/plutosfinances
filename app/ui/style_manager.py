"""Gerenciador de fontes, formatação monetária e folhas de estilo QSS (Temas Claro e Escuro)."""

from __future__ import annotations

from typing import Dict

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from app.config.app_settings import FONTS_DIR
from app.config.theme_palette import ThemePalette

PT_BR_MONTHS: Dict[int, str] = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

CURRENCY_SYMBOLS: Dict[str, str] = {
    "BRL": "R$",
    "USD": "US$",
    "EUR": "€",
    "GBP": "£",
}


def format_currency(value: float | int | None, currency: str = "BRL") -> str:
    """Formata um valor numérico no padrão monetário brasileiro (ex.: R$ 1.234,56)."""
    val = float(value or 0.0)
    symbol = CURRENCY_SYMBOLS.get(currency.upper(), "R$")
    sign = "-" if val < -0.004 else ""
    abs_val = abs(val)
    formatted = f"{abs_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{symbol} {formatted}"


def format_month_year(mes: int, ano: int) -> str:
    """Retorna 'Outubro / 2026'."""
    name = PT_BR_MONTHS.get(int(mes), f"Mês {mes}")
    return f"{name} / {int(ano)}"


def format_date_br(date_str: str | None) -> str:
    """Formata uma string ISO 'YYYY-MM-DD' no padrão brasileiro 'DD/MM/YYYY'."""
    if not date_str:
        return "—"
    raw = str(date_str).strip()[:10]
    parts = raw.split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return raw



def load_bundled_fonts() -> str:
    """Registra as fontes TTF/OTF originais do pacote em QFontDatabase."""
    primary_family = "Segoe UI"
    if not FONTS_DIR.exists():
        return primary_family

    for font_name in ("sans_regular.ttf", "sans_medium.ttf", "sans_bold.ttf"):
        fpath = FONTS_DIR / font_name
        if fpath.exists():
            font_id = QFontDatabase.addApplicationFont(str(fpath))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    primary_family = families[0]
    return primary_family


def build_stylesheet(palette: ThemePalette) -> str:
    """Gera a folha de estilo QSS completa do Plutos inspirada no protótipo de redesign."""
    p = palette
    return f"""
    QMainWindow, QDialog {{
        background-color: {p.app_background};
        color: {p.text_primary};
    }}
    QWidget {{
        color: {p.text_primary};
        font-family: "Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
        font-size: 13px;
    }}
    QFrame#DesktopHeader {{
        background-color: {p.surface_header};
        border-bottom: 1px solid {p.border_subtle};
    }}
    QFrame#SideMenu {{
        background-color: {p.surface_sidebar};
        border-right: 1px solid {p.border_subtle};
    }}
    QFrame#SideMenu QScrollArea,
    QFrame#SideMenu QWidget,
    QScrollArea#SideMenuScroll,
    QScrollArea#SideMenuScroll > QWidget,
    QScrollArea#SideMenuScroll > QWidget > QWidget {{
        background-color: transparent;
        background: transparent;
        border: none;
    }}
    QFrame#CardSurface {{
        background-color: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: 12px;
    }}
    QFrame#KpiCard {{
        background-color: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: 12px;
        padding: 16px;
    }}
    QFrame#KpiCard:hover {{
        border: 1px solid {p.border_subtle};
    }}
    QLabel#SectionTitle {{
        font-size: 22px;
        font-weight: 700;
        letter-spacing: -0.01em;
        color: {p.text_primary};
    }}
    QLabel#SubTitle {{
        font-size: 13px;
        color: {p.text_secondary};
    }}
    QLabel#BrandTitle {{
        font-size: 18px;
        font-weight: 700;
        letter-spacing: -0.01em;
        color: {p.text_primary};
    }}
    QLabel#BrandBadge {{
        background-color: {p.primary};
        color: #FFFFFF;
        border: none;
        border-radius: 8px;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        font-size: 15px;
        font-weight: 700;
        qproperty-alignment: AlignCenter;
    }}
    QLabel#KpiValue {{
        font-size: 26px;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: {p.text_primary};
    }}
    QLabel#MutedText {{
        color: {p.text_muted};
        font-size: 12px;
    }}
    QFrame#PeriodPill {{
        background-color: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: 18px;
    }}
    QPushButton#NavButton {{
        text-align: left;
        padding: 9px 12px;
        border: none;
        border-radius: 8px;
        background-color: transparent;
        color: {p.text_secondary};
        font-weight: 500;
        font-size: 13px;
    }}
    QPushButton#NavButton:hover {{
        background-color: {p.app_background};
        color: {p.text_primary};
    }}
    QPushButton#NavButton[active="true"] {{
        background-color: {p.primary_active_pill};
        border: none;
        color: {p.primary};
        font-weight: 600;
    }}
    QPushButton#PrimaryFab {{
        background-color: {p.primary};
        color: #FFFFFF;
        border: 1px solid {p.primary};
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton#PrimaryFab:hover {{
        background-color: {p.primary_hover};
        border-color: {p.primary_hover};
    }}
    QPushButton#PrimaryButton {{
        background-color: {p.primary};
        color: #FFFFFF;
        border: 1px solid {p.primary};
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {p.primary_hover};
        border-color: {p.primary_hover};
    }}
    QPushButton#SecondaryButton {{
        background-color: {p.surface_card};
        color: {p.text_primary};
        border: 1px solid {p.border_subtle};
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton#SecondaryButton:hover {{
        background-color: {p.app_background};
        border-color: {p.border_subtle};
        color: {p.text_primary};
    }}
    QPushButton#GhostButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 13px;
        font-weight: 500;
        color: {p.text_secondary};
    }}
    QPushButton#GhostButton:hover {{
        background-color: {p.app_background};
        color: {p.text_primary};
    }}
    QPushButton#SuccessButton {{
        background-color: {p.income_badge_bg};
        color: {p.income_green};
        border: 1px solid {p.income_green};
        border-radius: 8px;
        padding: 8px 14px;
        font-weight: 500;
        font-size: 13px;
    }}
    QPushButton#SuccessButton:hover {{
        background-color: {p.income_green};
        color: #FFFFFF;
    }}
    QPushButton#DangerButton {{
        background-color: transparent;
        color: {p.expense_red};
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 8px 14px;
        font-weight: 500;
        font-size: 13px;
    }}
    QPushButton#DangerButton:hover {{
        background-color: {p.expense_badge_bg};
        border-color: {p.expense_red};
    }}
    QPushButton#IconPillButton, QPushButton#IconButton {{
        background-color: transparent;
        border: none;
        border-radius: 8px;
        padding: 6px;
        min-width: 34px;
        max-width: 34px;
        min-height: 34px;
        max-height: 34px;
        color: {p.text_secondary};
    }}
    QPushButton#IconPillButton:hover, QPushButton#IconButton:hover {{
        background-color: {p.app_background};
        color: {p.text_primary};
    }}
    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QTextEdit {{
        background-color: {p.surface_card};
        color: {p.text_primary};
        border: 1px solid {p.border_subtle};
        border-radius: 8px;
        padding: 7px 12px;
        selection-background-color: {p.primary};
        selection-color: #FFFFFF;
    }}
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus, QTextEdit:focus {{
        border: 1px solid {p.primary};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button, QDateEdit::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button, QDateEdit::down-button {{
        width: 18px;
        background: transparent;
        border: none;
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QDateEdit::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover, QDateEdit::down-button:hover {{
        background-color: {p.app_background};
    }}
    QCheckBox, QRadioButton {{
        spacing: 8px;
        color: {p.text_primary};
        font-size: 13px;
    }}
    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 4px;
        border: 1px solid {p.border_subtle};
        background-color: {p.surface_card};
    }}
    QCheckBox::indicator:hover {{
        border-color: {p.primary};
        background-color: {p.primary_active_pill};
    }}
    QCheckBox::indicator:checked {{
        border-color: {p.primary};
        background-color: {p.primary};
    }}
    QCheckBox::indicator:disabled {{
        border-color: {p.border_subtle};
        background-color: {p.app_background};
    }}
    QRadioButton::indicator {{
        width: 17px;
        height: 17px;
        border-radius: 9px;
        border: 1px solid {p.border_subtle};
        background-color: {p.surface_card};
    }}
    QRadioButton::indicator:hover {{
        border-color: {p.primary};
        background-color: {p.primary_active_pill};
    }}
    QRadioButton::indicator:checked {{
        border-color: {p.primary};
        background-color: {p.primary};
    }}
    QRadioButton::indicator:disabled {{
        border-color: {p.border_subtle};
        background-color: {p.app_background};
    }}
    QDialogButtonBox QPushButton {{
        min-width: 80px;
        padding: 8px 16px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 500;
        background-color: {p.surface_card};
        color: {p.text_primary};
        border: 1px solid {p.border_subtle};
    }}
    QDialogButtonBox QPushButton:hover {{
        background-color: {p.app_background};
        border-color: {p.border_subtle};
    }}
    QDialogButtonBox QPushButton:default,
    QDialogButtonBox QPushButton[default="true"] {{
        background-color: {p.primary};
        color: #FFFFFF;
        border: 1px solid {p.primary};
    }}
    QDialogButtonBox QPushButton:default:hover,
    QDialogButtonBox QPushButton[default="true"]:hover {{
        background-color: {p.primary_hover};
        border-color: {p.primary_hover};
    }}
    QGroupBox {{
        font-weight: 600;
        font-size: 13px;
        border: 1px solid {p.border_subtle};
        border-radius: 8px;
        margin-top: 18px;
        padding-top: 14px;
        background-color: {p.surface_card};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 4px;
        color: {p.text_primary};
    }}
    QToolTip {{
        background-color: {p.text_primary};
        color: {p.app_background};
        border: none;
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 11px;
    }}
    QMessageBox {{
        background-color: {p.surface_card};
    }}
    QMessageBox QLabel {{
        color: {p.text_primary};
        font-size: 13px;
    }}
    QLabel#FormLabel, QLabel[form="true"] {{
        color: {p.text_secondary};
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#HintText, QLabel[hint="true"] {{
        color: {p.text_muted};
        font-size: 11px;
    }}
    QLabel#Chip, QFrame#Chip {{
        background-color: {p.app_background};
        color: {p.text_primary};
        border-radius: 8px;
        padding: 4px 10px;
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#Dot {{
        min-width: 8px;
        max-width: 8px;
        min-height: 8px;
        max-height: 8px;
        border-radius: 4px;
    }}
    QLineEdit#SearchInput {{
        background-color: {p.app_background};
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 7px 12px;
        color: {p.text_primary};
    }}
    QLineEdit#SearchInput:focus {{
        background-color: {p.surface_card};
        border: 1px solid {p.primary};
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: 8px;
    }}
    QTableWidget, QTreeWidget, QListWidget {{
        background-color: {p.surface_card};
        alternate-background-color: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: 12px;
        gridline-color: transparent;
        outline: 0;
    }}
    QHeaderView {{
        background-color: {p.surface_card};
        border: none;
    }}
    QHeaderView::section {{
        background-color: {p.surface_card};
        color: {p.text_secondary};
        font-weight: 500;
        font-size: 12px;
        padding: 10px 14px;
        border: none;
        border-bottom: 1px solid {p.border_subtle};
        text-align: left;
    }}
    QTableCornerButton::section {{
        background-color: {p.surface_card};
        border: none;
        border-bottom: 1px solid {p.border_subtle};
    }}
    QTableWidget::item, QTreeWidget::item, QListWidget::item {{
        padding: 11px 14px;
        border-bottom: 1px solid {p.border_subtle};
        color: {p.text_primary};
        font-size: 13px;
    }}
    QTableWidget::item:hover, QTreeWidget::item:hover, QListWidget::item:hover {{
        background-color: {p.app_background};
    }}
    QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
        background-color: {p.primary_active_pill};
        color: {p.text_primary};
    }}
    /* Badges de Status e Tipos */
    QLabel#BadgeDefault {{
        background-color: {p.app_background};
        color: {p.text_secondary};
        border-radius: 99px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#BadgeSuccess {{
        background-color: {p.income_badge_bg};
        color: {p.income_green};
        border-radius: 99px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#BadgeDanger {{
        background-color: {p.expense_badge_bg};
        color: {p.expense_red};
        border-radius: 99px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#BadgeWarning {{
        background-color: {p.warning_badge_bg};
        color: {p.warning_orange};
        border-radius: 99px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#BadgeInfo {{
        background-color: {p.transfer_badge_bg};
        color: {p.transfer_indigo};
        border-radius: 99px;
        padding: 3px 10px;
        font-size: 12px;
        font-weight: 500;
    }}
    QTabWidget::pane {{
        border: 1px solid {p.border_subtle};
        border-radius: 12px;
        background-color: {p.surface_card};
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {p.text_secondary};
        padding: 10px 18px;
        font-weight: 500;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {p.primary};
        border-bottom: 2px solid {p.primary};
    }}
    QStatusBar {{
        background-color: {p.surface_sidebar};
        color: {p.text_muted};
        border-top: 1px solid {p.border_subtle};
        font-size: 11px;
    }}
    QProgressBar {{
        background-color: {p.app_background};
        border: none;
        border-radius: 99px;
        text-align: center;
        height: 8px;
        min-height: 8px;
        max-height: 8px;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background-color: {p.primary};
        border-radius: 99px;
    }}
    QMenu {{
        background-color: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: 12px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 12px;
        border-radius: 6px;
        color: {p.text_primary};
        font-size: 13px;
        font-weight: 500;
    }}
    QMenu::item:selected {{
        background-color: {p.app_background};
        color: {p.text_primary};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {p.border_subtle};
        margin: 4px 6px;
    }}
    QScrollArea {{
        background-color: transparent;
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 7px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.border_subtle};
        min-height: 24px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p.text_muted};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        background: none;
        border: none;
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 7px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: {p.border_subtle};
        min-width: 24px;
        border-radius: 3px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {p.text_muted};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        background: none;
        border: none;
        width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}
    QSplitter::handle {{
        background-color: {p.border_subtle};
    }}
    /* QCalendarWidget */
    QCalendarWidget {{
        background-color: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: 10px;
    }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{
        background-color: {p.surface_header};
        border-bottom: 1px solid {p.border_subtle};
        border-top-left-radius: 9px;
        border-top-right-radius: 9px;
        min-height: 42px;
    }}
    QCalendarWidget QToolButton {{
        color: {p.text_primary};
        background-color: transparent;
        font-weight: 600;
        font-size: 13px;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 4px 10px;
        margin: 3px;
    }}
    QCalendarWidget QToolButton:hover {{
        background-color: {p.primary_active_pill};
        color: {p.primary};
        border: 1px solid {p.border_subtle};
    }}
    QCalendarWidget QToolButton:pressed {{
        background-color: {p.surface_card};
    }}
    QCalendarWidget QToolButton::menu-indicator {{
        image: none;
        width: 0px;
    }}
    QCalendarWidget QToolButton#qt_calendar_prevmonth,
    QCalendarWidget QToolButton#qt_calendar_nextmonth {{
        font-size: 18px;
        font-weight: bold;
        min-width: 32px;
        max-width: 32px;
        min-height: 28px;
        max-height: 28px;
        padding: 0px;
    }}
    QCalendarWidget QSpinBox {{
        background-color: {p.surface_card};
        color: {p.text_primary};
        border: 1px solid {p.border_subtle};
        border-radius: 6px;
        padding: 2px 6px;
        font-weight: 600;
        font-size: 13px;
        selection-background-color: {p.primary};
        selection-color: #FFFFFF;
    }}
    QCalendarWidget QSpinBox::up-button,
    QCalendarWidget QSpinBox::down-button {{
        width: 16px;
        background: transparent;
    }}
    QCalendarWidget QMenu {{
        background-color: {p.surface_card};
        color: {p.text_primary};
        border: 1px solid {p.border_subtle};
        border-radius: 6px;
        padding: 4px;
    }}
    QCalendarWidget QMenu::item {{
        padding: 6px 18px;
        border-radius: 4px;
        color: {p.text_primary};
    }}
    QCalendarWidget QMenu::item:selected {{
        background-color: {p.primary_active_pill};
        color: {p.primary};
    }}
    QCalendarWidget QTableView {{
        background-color: {p.surface_card};
        alternate-background-color: {p.surface_card};
        color: {p.text_primary};
        selection-background-color: {p.primary_active_pill};
        selection-color: {p.primary};
        gridline-color: {p.border_subtle};
        border: none;
        outline: 0;
    }}
    QCalendarWidget QTableView::item {{
        color: {p.text_primary};
    }}
    QCalendarWidget QTableView::item:hover {{
        background-color: {p.primary_active_pill};
    }}
    QCalendarWidget QTableView::item:selected {{
        background-color: {p.primary_active_pill};
        color: {p.primary};
        font-weight: bold;
    }}
    QCalendarWidget QTableView:disabled {{
        color: {p.text_muted};
    }}
    """


def apply_app_theme(app: QApplication, mode: str) -> ThemePalette:
    """Aplica a folha de estilo QSS do tema selecionado ('light' ou 'dark') na aplicação."""
    palette = ThemePalette.for_mode(mode)
    app.setStyleSheet(build_stylesheet(palette))
    return palette

