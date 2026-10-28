"""Tela Nativa de Calendário Financeiro (`CalendarioView`)."""

from __future__ import annotations

from datetime import date
from typing import Callable, Dict, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import (
    EXPENSE_RED,
    INCOME_GREEN,
    PRIMARY_BLUE,
    TRANSFER_AMBER,
    WARNING_ORANGE,
    ThemePalette,
)
from app.database.connection_manager import ConnectionManager
from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.analytics_service import (
    AnalyticsService,
    DayCalendarSummary,
)
from app.ui.components import Badge, EmptyStateWidget
from app.ui.icons import get_line_icon
from app.ui.style_manager import format_currency, format_date_br


class CalendarioView(QWidget):
    """
    Calendário Financeiro nativo com marcação dos dias com movimentação e
    detalhamento lateral dos lançamentos da data selecionada.
    """

    def __init__(
        self,
        db: ConnectionManager,
        get_context: Callable[[], Tuple[str, int, int, str]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.get_context = get_context
        self.analytics = AnalyticsService(db)
        self._daily_map: Dict[int, DayCalendarSummary] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_t = QLabel("Calendário")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Visualize vencimentos, receitas e despesas distribuídos pelos dias do mês"
        )
        lbl_s.setObjectName("MutedText")
        title_box.addWidget(lbl_t)
        title_box.addWidget(lbl_s)
        root.addLayout(title_box)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Card Esquerdo: Calendário Nativo
        cal_card = QFrame()
        cal_card.setObjectName("CardSurface")
        c_lay = QVBoxLayout(cal_card)
        c_lay.setContentsMargins(16, 16, 16, 16)
        c_lay.setSpacing(10)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        prev_btn = self.calendar.findChild(QToolButton, "qt_calendar_prevmonth")
        next_btn = self.calendar.findChild(QToolButton, "qt_calendar_nextmonth")
        if prev_btn:
            prev_btn.setIcon(QIcon())
            prev_btn.setText("‹")
        if next_btn:
            next_btn.setIcon(QIcon())
            next_btn.setText("›")

        self.calendar.selectionChanged.connect(self._on_day_selected)
        c_lay.addWidget(self.calendar)
        splitter.addWidget(cal_card)

        # Card Direito: Lançamentos da Data Selecionada
        detail_card = QFrame()
        detail_card.setObjectName("CardSurface")
        d_lay = QVBoxLayout(detail_card)
        d_lay.setContentsMargins(16, 16, 16, 16)
        d_lay.setSpacing(12)

        f_bold = QFont()
        f_bold.setPointSize(11)
        f_bold.setBold(True)
        self.lbl_day_title = QLabel("Lançamentos do Dia")
        self.lbl_day_title.setFont(f_bold)
        self.lbl_day_summary = QLabel("")
        self.lbl_day_summary.setObjectName("MutedText")
        d_lay.addWidget(self.lbl_day_title)
        d_lay.addWidget(self.lbl_day_summary)

        self.stack = QStackedWidget()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Tipo", "Descrição", "Categoria", "Situação", "Valor"]
        )
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(3, 120)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stack.addWidget(self.table)

        self.empty_day_widget = EmptyStateWidget(
            title="Nenhum lançamento no dia",
            subtitle="Não há receitas, despesas ou vencimentos agendados para esta data.",
            icon_name="calendar",
        )
        self.stack.addWidget(self.empty_day_widget)

        d_lay.addWidget(self.stack, stretch=1)
        splitter.addWidget(detail_card)
        splitter.setSizes([460, 640])
        root.addWidget(splitter, stretch=1)

    def refresh_data(self) -> None:
        profile_id, month, year, _ = self.get_context()
        mode = self.db.settings.date_reference_mode
        self._daily_map = self.analytics.daily_calendar_summary(
            year, month, profile_id=profile_id, mode=mode
        )

        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        # 1. Limpa todas as formatações específicas prévias
        empty_fmt = QTextCharFormat()
        for qd in list(self.calendar.dateTextFormat().keys()):
            self.calendar.setDateTextFormat(qd, empty_fmt)

        # 2. Reseta formato padrão dos dias da semana
        fmt_base = QTextCharFormat()
        fmt_base.setForeground(QBrush(QColor(pal.text_muted)))
        for dow in (
            Qt.DayOfWeek.Monday,
            Qt.DayOfWeek.Tuesday,
            Qt.DayOfWeek.Wednesday,
            Qt.DayOfWeek.Thursday,
            Qt.DayOfWeek.Friday,
            Qt.DayOfWeek.Saturday,
            Qt.DayOfWeek.Sunday,
        ):
            self.calendar.setWeekdayTextFormat(dow, fmt_base)

        hdr_fmt = QTextCharFormat()
        hdr_fmt.setForeground(QBrush(QColor(pal.text_secondary)))
        hdr_fmt.setFontWeight(QFont.Weight.Bold)
        self.calendar.setHeaderTextFormat(hdr_fmt)

        # 3. Formata os dias do mês corrente
        first_day = QDate(year, month, 1)
        days_in_month = first_day.daysInMonth() if first_day.isValid() else 31
        normal_fmt = QTextCharFormat()
        normal_fmt.setForeground(QBrush(QColor(pal.text_primary)))
        for d in range(1, days_in_month + 1):
            qd = QDate(year, month, d)
            if qd.isValid():
                self.calendar.setDateTextFormat(qd, normal_fmt)

        # 4. Formata dias com movimentação financeira ativa
        for day_num, summary in self._daily_map.items():
            qd = QDate(year, month, day_num)
            if not qd.isValid():
                continue
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Bold)
            if summary.despesas > summary.receitas:
                fmt.setForeground(QBrush(QColor(pal.expense_red)))
            elif summary.receitas > 0:
                fmt.setForeground(QBrush(QColor(pal.income_green)))
            else:
                fmt.setForeground(QBrush(QColor(pal.primary)))
            self.calendar.setDateTextFormat(qd, fmt)

        cur_qd = self.calendar.selectedDate()
        self.calendar.setCurrentPage(year, month)
        if cur_qd.year() != year or cur_qd.month() != month:
            target_day = next(iter(self._daily_map.keys()), 1)
            self.calendar.setSelectedDate(QDate(year, month, target_day))
        else:
            self._on_day_selected()

    def _on_day_selected(self) -> None:
        qd = self.calendar.selectedDate()
        dt_str = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        self.lbl_day_title.setText(f"Lançamentos de {format_date_br(dt_str)}")
        summary = self._daily_map.get(qd.day())

        if summary is None or not summary.occurrences:
            self.table.setRowCount(0)
            self.lbl_day_summary.setText("Nenhuma movimentação registrada para esta data.")
            self.stack.setCurrentWidget(self.empty_day_widget)
            return

        self.stack.setCurrentWidget(self.table)
        self.lbl_day_summary.setText(
            f"Receitas: {format_currency(summary.receitas)}  ·  "
            f"Despesas: {format_currency(summary.despesas)}  ·  "
            f"Saldo do Dia: {format_currency(summary.saldo_dia)}"
        )

        self.table.setRowCount(0)
        f_bold = QFont()
        f_bold.setBold(True)
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        for idx, occ in enumerate(summary.occurrences):
            self.table.insertRow(idx)

            if occ.kind == KIND_RECEITA:
                k_lbl, k_col = "Receita", INCOME_GREEN
            elif occ.kind == KIND_DESPESA:
                k_lbl, k_col = "Despesa", EXPENSE_RED
            else:
                k_lbl, k_col = "Transferência", TRANSFER_AMBER

            it_k = QTableWidgetItem(k_lbl)
            it_k.setForeground(QColor(k_col))
            it_k.setFont(f_bold)
            self.table.setItem(idx, 0, it_k)

            it_desc = QTableWidgetItem(occ.descricao)
            self.table.setItem(idx, 1, it_desc)

            it_cat = QTableWidgetItem(occ.categoria_nome or "Transferência")
            it_cat.setForeground(QColor(pal.text_secondary))
            self.table.setItem(idx, 2, it_cat)

            # Badge de situação
            st_var = "success" if occ.efetivada else "warning"
            badge = Badge(occ.status_label, variant=st_var)
            c_w = QWidget()
            c_lay = QHBoxLayout(c_w)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lay.addWidget(badge)
            self.table.setCellWidget(idx, 3, c_w)

            it_v = QTableWidgetItem(format_currency(occ.total))
            it_v.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_v.setFont(f_bold)
            it_v.setForeground(QColor(k_col))
            self.table.setItem(idx, 4, it_v)
