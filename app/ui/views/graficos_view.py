"""Tela Nativa de Gráficos Interativos (`GraficosView` usando `PySide6.QtCharts`)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import (
    EXPENSE_RED,
    INCOME_GREEN,
    PRIMARY_BLUE,
    ThemePalette,
)
from app.database.connection_manager import ConnectionManager
from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.analytics_service import AnalyticsService


class GraficosView(QWidget):
    """
    Tela nativa de Gráficos (`PySide6.QtCharts`) com 4 painéis simultâneos:
    1. Rosca: Despesas por Categoria no Mês
    2. Rosca: Receitas por Categoria no Mês
    3. Barras Agrupadas: Receitas x Despesas (Últimos 6 ou 12 Meses)
    4. Linha: Evolução do Saldo Previsto e Resultado Mensal
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
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        t_col = QVBoxLayout()
        t_col.setSpacing(4)
        lbl_t = QLabel("Gráficos")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Distribuição por categorias, comparativo mensal de receitas e despesas e evolução de saldo"
        )
        lbl_s.setObjectName("MutedText")
        t_col.addWidget(lbl_t)
        t_col.addWidget(lbl_s)
        header.addLayout(t_col)
        header.addStretch()

        filter_box = QHBoxLayout()
        filter_box.setSpacing(8)
        lbl_h = QLabel("Período:")
        lbl_h.setStyleSheet("font-weight: 500;")

        self.cb_horizon = QComboBox()
        self.cb_horizon.setMinimumWidth(160)
        self.cb_horizon.addItem("Últimos 6 Meses", 6)
        self.cb_horizon.addItem("Últimos 12 Meses", 12)
        self.cb_horizon.currentIndexChanged.connect(lambda _: self.refresh_data())

        filter_box.addWidget(lbl_h)
        filter_box.addWidget(self.cb_horizon)
        header.addLayout(filter_box)
        root.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(16)

        self.cv_exp_pie = self._make_chart_view()
        self.cv_inc_pie = self._make_chart_view()
        self.cv_bars = self._make_chart_view()
        self.cv_line = self._make_chart_view()

        grid.addWidget(self._wrap_card(self.cv_exp_pie), 0, 0)
        grid.addWidget(self._wrap_card(self.cv_inc_pie), 0, 1)
        grid.addWidget(self._wrap_card(self.cv_bars), 1, 0)
        grid.addWidget(self._wrap_card(self.cv_line), 1, 1)
        root.addLayout(grid, stretch=1)

    @staticmethod
    def _make_chart_view() -> QChartView:
        cv = QChartView()
        cv.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cv.setStyleSheet("background: transparent; border: none;")
        return cv

    @staticmethod
    def _wrap_card(widget: QWidget) -> QFrame:
        card = QFrame()
        card.setObjectName("CardSurface")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.addWidget(widget)
        return card

    def refresh_data(self) -> None:
        profile_id, month, year, _ = self.get_context()
        mode = self.db.settings.date_reference_mode
        months_cnt = int(self.cb_horizon.currentData() or 6)

        exp_rows = self.analytics.category_breakdown(
            year, month, kind=KIND_DESPESA, profile_id=profile_id, mode=mode
        )
        inc_rows = self.analytics.category_breakdown(
            year, month, kind=KIND_RECEITA, profile_id=profile_id, mode=mode
        )
        evo = self.analytics.monthly_evolution(
            year, month, months_count=months_cnt, profile_id=profile_id, mode=mode
        )

        self._render_pie(self.cv_exp_pie, "Despesas por Categoria", exp_rows)
        self._render_pie(self.cv_inc_pie, "Receitas por Categoria", inc_rows)
        self._render_bars(self.cv_bars, evo)
        self._render_line(self.cv_line, evo)

    def _style_chart(self, chart: QChart, title: str) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        chart.setTitle(title)

        f = QFont("Segoe UI", 11)
        f.setBold(True)
        chart.setTitleFont(f)
        chart.setTitleBrush(QColor(pal.text_primary))

        chart.setBackgroundBrush(QColor(pal.surface_card))
        chart.setBackgroundPen(QPen(Qt.PenStyle.NoPen))
        chart.setBackgroundRoundness(8.0)

        f_leg = QFont("Segoe UI", 9)
        chart.legend().setFont(f_leg)
        chart.legend().setLabelColor(QColor(pal.text_secondary))

    def _render_pie(self, view: QChartView, title: str, rows: list) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        chart = QChart()
        self._style_chart(chart, title)

        series = QPieSeries()
        series.setHoleSize(0.50)

        if not rows:
            sl = series.append("Sem lançamentos", 1.0)
            sl.setColor(QColor(pal.surface_header))
            sl.setBorderColor(QColor(pal.surface_card))
        else:
            for r in rows[:8]:
                val = max(0.01, abs(r.total))
                sl = series.append(
                    f"{r.categoria_nome} ({r.percentual:.0f}%)", val
                )
                sl.setColor(QColor(r.cor_hex))
                sl.setBorderColor(QColor(pal.surface_card))
                sl.setBorderWidth(2)

        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        view.setChart(chart)

    def _render_bars(self, view: QChartView, evo: list) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        chart = QChart()
        self._style_chart(chart, "Receitas × Despesas por Mês")

        set_rec = QBarSet("Receitas")
        set_rec.setColor(QColor(INCOME_GREEN))

        set_desp = QBarSet("Despesas")
        set_desp.setColor(QColor(EXPENSE_RED))

        categories = []
        max_v = 100.0
        for p in evo:
            categories.append(p.label)
            set_rec.append(max(0.0, p.receitas))
            set_desp.append(max(0.0, p.despesas))
            max_v = max(max_v, p.receitas, p.despesas)

        series = QBarSeries()
        series.append(set_rec)
        series.append(set_desp)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsColor(QColor(pal.text_secondary))
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0.0, max_v * 1.15)
        axis_y.setLabelsColor(QColor(pal.text_secondary))
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        view.setChart(chart)

    def _render_line(self, view: QChartView, evo: list) -> None:
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        chart = QChart()
        self._style_chart(chart, "Evolução do Saldo Previsto e Resultado")

        line_saldo = QLineSeries()
        line_saldo.setName("Saldo Previsto")
        line_saldo.setColor(QColor(PRIMARY_BLUE))

        line_res = QLineSeries()
        line_res.setName("Resultado Mensal")
        line_res.setColor(QColor(INCOME_GREEN))

        min_v, max_v = 0.0, 100.0
        for idx, p in enumerate(evo):
            line_saldo.append(float(idx), p.saldo_contas)
            line_res.append(float(idx), p.resultado)
            min_v = min(min_v, p.saldo_contas, p.resultado)
            max_v = max(max_v, p.saldo_contas, p.resultado)

        chart.addSeries(line_saldo)
        chart.addSeries(line_res)
        chart.createDefaultAxes()
        for ax in chart.axes():
            ax.setLabelsColor(QColor(pal.text_secondary))
        view.setChart(chart)
