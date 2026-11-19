"""Tela Nativa de Visão Geral / Resumo Mensal (`DashboardView` / `OverviewGrid`)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtCore import QMargins, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import (
    EXPENSE_RED,
    INCOME_GREEN,
    PRIMARY_BLUE,
    WARNING_ORANGE,
)
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.domain.models import KIND_DESPESA, KIND_TRANSFERENCIA
from app.domain.services.analytics_service import AnalyticsService
from app.domain.services.budget_service import BudgetService
from app.domain.services.credit_card_service import (
    CreditCardService,
    brand_icon_filename,
)
from app.domain.services.transaction_service import TransactionService
from app.ui.bank_icons import (
    create_color_badge_icon,
    get_bank_icon,
    get_card_brand_icon,
)
from app.ui.components import Badge, KpiCard
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import format_currency, format_date_br


class DashboardView(QWidget):
    """
    Visão Geral (Resumo / Dashboard) padronizada com o design system do Plutos:
    - 4 Cards KPI superiores (Saldo em Contas, Receitas do Mês, Despesas do Mês, Faturas de Cartões)
    - Painel 1: Minhas Contas (Saldos com logos compactos de banco)
    - Painel 2: Despesas por Categoria (Gráfico Donut QtCharts refinado)
    - Painel 3: Faturas de Cartões de Crédito (Status em badges, vencimento e valores tabulares)
    - Painel 4: Orçamentos do Mês (Progresso e status)
    """

    def __init__(
        self,
        db: ConnectionManager,
        get_context: Callable[[], Tuple[str, int, int, str]],
        navigate_to: Callable[[str], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.get_context = get_context
        self.navigate_to = navigate_to

        self.account_repo = AccountRepository(db)
        self.tx_service = TransactionService(db)
        self.card_service = CreditCardService(db, self.tx_service)
        self.budget_service = BudgetService(db, self.tx_service)
        self.analytics = AnalyticsService(db, self.tx_service)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Cabeçalho
        header = QHBoxLayout()
        t_col = QVBoxLayout()
        lbl_t = QLabel("Visão geral")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel("Resumo financeiro, contas, cartões e orçamentos do mês")
        lbl_s.setObjectName("MutedText")
        t_col.addWidget(lbl_t)
        t_col.addWidget(lbl_s)
        header.addLayout(t_col)
        header.addStretch()

        self.btn_go_tx = QPushButton("Ver extrato completo")
        self.btn_go_tx.setObjectName("SecondaryButton")
        self.btn_go_tx.setIcon(get_line_icon("list", size=16))
        self.btn_go_tx.clicked.connect(lambda: self.navigate_to("transacoes"))
        header.addWidget(self.btn_go_tx)
        root.addLayout(header)

        # 4 KPI Cards Superiores com micro-ícones e tint semântico
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.k_saldo, self.lbl_k_saldo, self.lbl_k_saldo_sub = self._make_kpi(
            "Saldo em Contas", PRIMARY_BLUE, icon_name="wallet", tint="info"
        )
        self.k_rec, self.lbl_k_rec, self.lbl_k_rec_sub = self._make_kpi(
            "Receitas do Mês", INCOME_GREEN, icon_name="arrow-up", tint="positive"
        )
        self.k_desp, self.lbl_k_desp, self.lbl_k_desp_sub = self._make_kpi(
            "Despesas do Mês", EXPENSE_RED, icon_name="arrow-down", tint="negative"
        )
        self.k_cc, self.lbl_k_cc, self.lbl_k_cc_sub = self._make_kpi(
            "Faturas de Cartão", WARNING_ORANGE, icon_name="card", tint="warning"
        )
        kpi_row.addWidget(self.k_saldo, 1)
        kpi_row.addWidget(self.k_rec, 1)
        kpi_row.addWidget(self.k_desp, 1)
        kpi_row.addWidget(self.k_cc, 1)
        root.addLayout(kpi_row)

        # Banner de alerta para lançamentos sem categoria
        self.uncat_banner = QFrame()
        self.uncat_banner.setObjectName("UncatBanner")
        ub_lay = QHBoxLayout(self.uncat_banner)
        ub_lay.setContentsMargins(14, 9, 14, 9)
        ub_lay.setSpacing(10)
        lbl_ub_ico = QLabel()
        lbl_ub_ico.setStyleSheet("background: transparent; border: none;")
        lbl_ub_ico.setPixmap(get_line_pixmap("tag", color=WARNING_ORANGE, size=15))
        self.lbl_uncat_text = QLabel("")
        self.lbl_uncat_text.setStyleSheet("background: transparent; border: none; font-size: 12px; font-weight: 500;")
        self.lbl_uncat_text.setWordWrap(True)
        self.btn_categorize = QPushButton("Categorizar")
        self.btn_categorize.setObjectName("SecondaryButton")
        self.btn_categorize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_categorize.clicked.connect(lambda: self.navigate_to("transacoes"))
        ub_lay.addWidget(lbl_ub_ico)
        ub_lay.addWidget(self.lbl_uncat_text, 1)
        ub_lay.addWidget(self.btn_categorize)
        self.uncat_banner.setVisible(False)
        root.addWidget(self.uncat_banner)

        # Banner de insight rápido do período
        self.insight_banner = QFrame()
        self.insight_banner.setObjectName("InsightBanner")
        ib_lay = QHBoxLayout(self.insight_banner)
        ib_lay.setContentsMargins(14, 9, 14, 9)
        ib_lay.setSpacing(10)
        lbl_ib_ico = QLabel()
        lbl_ib_ico.setStyleSheet("background: transparent; border: none;")
        lbl_ib_ico.setPixmap(get_line_pixmap("sparkle", color="#4F46E5", size=15))
        self.lbl_insight_text = QLabel("")
        self.lbl_insight_text.setStyleSheet("background: transparent; border: none; font-size: 12px; font-weight: 500;")
        self.lbl_insight_text.setWordWrap(True)
        self.btn_go_ai_diag = QPushButton("Diagnóstico IA")
        self.btn_go_ai_diag.setObjectName("SecondaryButton")
        self.btn_go_ai_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_go_ai_diag.clicked.connect(lambda: self.navigate_to("relatorios"))
        ib_lay.addWidget(lbl_ib_ico)
        ib_lay.addWidget(self.lbl_insight_text, 1)
        ib_lay.addWidget(self.btn_go_ai_diag)
        root.addWidget(self.insight_banner)

        # Área com rolagem suave para os painéis do Dashboard
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        body_host = QWidget()
        body_host.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(body_host)
        body_lay.setContentsMargins(0, 0, 4, 4)
        body_lay.setSpacing(14)

        # Grid 2 colunas de painéis limpos (sem grade de planilha)
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Painel 1 (0, 0): Contas bancárias em lista limpa
        c_acc = QFrame()
        c_acc.setObjectName("CardSurface")
        acc_lay = QVBoxLayout(c_acc)
        acc_lay.setContentsMargins(18, 16, 18, 16)
        acc_lay.setSpacing(10)
        acc_hdr = QHBoxLayout()
        lbl_acc_t = QLabel("Contas bancárias")
        lbl_acc_t.setStyleSheet("font-size: 14px; font-weight: 600;")
        btn_all_acc = QPushButton("Ver contas")
        btn_all_acc.setObjectName("SecondaryButton")
        btn_all_acc.setIcon(get_line_icon("bank", size=14))
        btn_all_acc.clicked.connect(lambda: self.navigate_to("contas"))
        acc_hdr.addWidget(lbl_acc_t)
        acc_hdr.addStretch()
        acc_hdr.addWidget(btn_all_acc)
        acc_lay.addLayout(acc_hdr)

        self.acc_scroll = QScrollArea()
        self.acc_scroll.setWidgetResizable(True)
        self.acc_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.acc_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.acc_list_widget = QWidget()
        self.acc_list_widget.setStyleSheet("background: transparent;")
        self.acc_list_layout = QVBoxLayout(self.acc_list_widget)
        self.acc_list_layout.setContentsMargins(0, 2, 4, 2)
        self.acc_list_layout.setSpacing(0)
        self.acc_scroll.setWidget(self.acc_list_widget)
        acc_lay.addWidget(self.acc_scroll, stretch=1)
        c_acc.setMinimumHeight(310)
        grid.addWidget(c_acc, 0, 0)

        # Painel 2 (0, 1): Gastos por categoria (Donut + legenda tabular com %)
        c_pie = QFrame()
        c_pie.setObjectName("CardSurface")
        pie_lay = QVBoxLayout(c_pie)
        pie_lay.setContentsMargins(18, 16, 18, 16)
        pie_lay.setSpacing(10)
        pie_hdr = QHBoxLayout()
        lbl_pie_t = QLabel("Gastos por categoria")
        lbl_pie_t.setStyleSheet("font-size: 14px; font-weight: 600;")
        btn_all_charts = QPushButton("Ver gráficos")
        btn_all_charts.setObjectName("SecondaryButton")
        btn_all_charts.setIcon(get_line_icon("pie-chart", size=14))
        btn_all_charts.clicked.connect(lambda: self.navigate_to("graficos"))
        pie_hdr.addWidget(lbl_pie_t)
        pie_hdr.addStretch()
        pie_hdr.addWidget(btn_all_charts)
        pie_lay.addLayout(pie_hdr)

        pie_body = QHBoxLayout()
        pie_body.setSpacing(12)
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.chart_view.setStyleSheet("background: transparent;")
        self.chart_view.setMinimumSize(180, 180)
        pie_body.addWidget(self.chart_view, 5)

        self.cat_legend_widget = QWidget()
        self.cat_legend_layout = QVBoxLayout(self.cat_legend_widget)
        self.cat_legend_layout.setContentsMargins(0, 8, 4, 8)
        self.cat_legend_layout.setSpacing(8)
        pie_body.addWidget(self.cat_legend_widget, 6)
        pie_lay.addLayout(pie_body, stretch=1)
        c_pie.setMinimumHeight(310)
        grid.addWidget(c_pie, 0, 1)

        # Painel 3 (1, 0): Resumo mensal (Gráfico de barras vertical 6 meses)
        c_monthly = QFrame()
        c_monthly.setObjectName("CardSurface")
        mon_lay = QVBoxLayout(c_monthly)
        mon_lay.setContentsMargins(18, 16, 18, 16)
        mon_lay.setSpacing(8)
        mon_hdr = QHBoxLayout()
        lbl_mon_t = QLabel("Resumo mensal")
        lbl_mon_t.setStyleSheet("font-size: 14px; font-weight: 600;")
        lbl_mon_sub = QLabel("Últimos 6 meses")
        lbl_mon_sub.setObjectName("MutedText")
        lbl_mon_sub.setStyleSheet("font-size: 12px;")
        mon_hdr.addWidget(lbl_mon_t)
        mon_hdr.addStretch()
        mon_hdr.addWidget(lbl_mon_sub)
        mon_lay.addLayout(mon_hdr)

        self.monthly_chart_view = QChartView()
        self.monthly_chart_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.monthly_chart_view.setStyleSheet("background: transparent;")
        self.monthly_chart_view.setMinimumHeight(200)
        mon_lay.addWidget(self.monthly_chart_view, stretch=1)
        c_monthly.setMinimumHeight(310)
        grid.addWidget(c_monthly, 1, 0)

        # Painel 4 (1, 1): Faturas de cartões em lista limpa
        c_cards = QFrame()
        c_cards.setObjectName("CardSurface")
        cc_lay = QVBoxLayout(c_cards)
        cc_lay.setContentsMargins(18, 16, 18, 16)
        cc_lay.setSpacing(10)
        cc_hdr = QHBoxLayout()
        lbl_cc_t = QLabel("Faturas de cartões")
        lbl_cc_t.setStyleSheet("font-size: 14px; font-weight: 600;")
        btn_all_cc = QPushButton("Ver cartões")
        btn_all_cc.setObjectName("SecondaryButton")
        btn_all_cc.setIcon(get_line_icon("card", size=14))
        btn_all_cc.clicked.connect(lambda: self.navigate_to("cartoes"))
        cc_hdr.addWidget(lbl_cc_t)
        cc_hdr.addStretch()
        cc_hdr.addWidget(btn_all_cc)
        cc_lay.addLayout(cc_hdr)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.cards_list_widget = QWidget()
        self.cards_list_widget.setStyleSheet("background: transparent;")
        self.cards_list_layout = QVBoxLayout(self.cards_list_widget)
        self.cards_list_layout.setContentsMargins(0, 2, 4, 2)
        self.cards_list_layout.setSpacing(0)
        self.cards_scroll.setWidget(self.cards_list_widget)
        cc_lay.addWidget(self.cards_scroll, stretch=1)
        c_cards.setMinimumHeight(310)
        grid.addWidget(c_cards, 1, 1)

        # Painel 5 (2, 0, span 2): Orçamentos do mês em cards de progresso
        c_bud = QFrame()
        c_bud.setObjectName("CardSurface")
        bud_lay = QVBoxLayout(c_bud)
        bud_lay.setContentsMargins(18, 16, 18, 16)
        bud_lay.setSpacing(10)
        bud_hdr = QHBoxLayout()
        lbl_bud_t = QLabel("Orçamentos do mês")
        lbl_bud_t.setStyleSheet("font-size: 14px; font-weight: 600;")
        btn_all_bud = QPushButton("Ver orçamentos")
        btn_all_bud.setObjectName("SecondaryButton")
        btn_all_bud.setIcon(get_line_icon("chart-bar", size=14))
        btn_all_bud.clicked.connect(lambda: self.navigate_to("orcamentos"))
        bud_hdr.addWidget(lbl_bud_t)
        bud_hdr.addStretch()
        bud_hdr.addWidget(btn_all_bud)
        bud_lay.addLayout(bud_hdr)

        self.budgets_list_widget = QWidget()
        self.budgets_list_layout = QVBoxLayout(self.budgets_list_widget)
        self.budgets_list_layout.setContentsMargins(0, 2, 0, 2)
        self.budgets_list_layout.setSpacing(8)
        bud_lay.addWidget(self.budgets_list_widget)
        grid.addWidget(c_bud, 2, 0, 1, 2)

        body_lay.addLayout(grid)
        body_lay.addStretch()
        scroll.setWidget(body_host)
        root.addWidget(scroll, stretch=1)

    def _make_kpi(
        self,
        title: str,
        accent_hex: str,
        *,
        icon_name: Optional[str] = None,
        tint: Optional[str] = None,
    ) -> Tuple[KpiCard, QLabel, QLabel]:
        card = KpiCard(
            title=title.upper(),
            value="R$ 0,00",
            variant="neutral",
            subtitle="",
            icon_name=icon_name,
            accent_color=accent_hex,
            tint=tint,
        )
        card.lbl_value.setStyleSheet(f"color: {accent_hex}; font-size: 22px; font-weight: 700;")
        card.lbl_subtitle.setStyleSheet("font-size: 11px;")
        return card, card.lbl_value, card.lbl_subtitle

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                DashboardView._clear_layout(item.layout())  # type: ignore[arg-type]

    def refresh_data(self) -> None:
        profile_id, month, year, _ = self.get_context()
        mode = self.db.settings.date_reference_mode
        from app.config.theme_palette import ThemePalette
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        # 1. Contas bancárias em lista limpa (sem grade de tabela)
        accounts = [
            a
            for a in self.account_repo.list_accounts_with_balances(
                profile_id=profile_id, mes=month, ano=year
            )
            if str(a.exibir_resumo or "S").upper() == "S"
        ]
        totals_acc = self.account_repo.get_consolidated_totals(
            profile_id=profile_id, mes=month, ano=year
        )
        self.lbl_k_saldo.setText(format_currency(totals_acc["saldo_atual"]))
        self.lbl_k_saldo_sub.setText(
            f"Previsto: {format_currency(totals_acc['saldo_previsto'])}"
        )

        self._clear_layout(self.acc_list_layout)
        if not accounts:
            lbl_empty_acc = QLabel("Nenhuma conta configurada para o resumo.")
            lbl_empty_acc.setObjectName("MutedText")
            lbl_empty_acc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.acc_list_layout.addWidget(lbl_empty_acc)
        else:
            for idx, acc in enumerate(accounts):
                row_f = QFrame()
                row_f.setObjectName("DashListRow")
                row_f.setMinimumHeight(52)
                row_f.setStyleSheet(
                    f"QFrame#DashListRow {{ background: transparent; border: none; "
                    f"{f'border-bottom: 1px solid {pal.border_subtle};' if idx < len(accounts) - 1 else ''} }}"
                )
                rh = QHBoxLayout(row_f)
                rh.setContentsMargins(2, 4, 2, 4)
                rh.setSpacing(10)

                ico_lbl = QLabel()
                ico_lbl.setFixedSize(24, 24)
                ico_lbl.setPixmap(get_bank_icon(acc.image_key, size=22).pixmap(22, 22))
                rh.addWidget(ico_lbl)

                name_lbl = QLabel(acc.descricao)
                name_lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
                rh.addWidget(name_lbl, 1)

                val_col = QVBoxLayout()
                val_col.setContentsMargins(0, 0, 0, 0)
                val_col.setSpacing(0)
                val_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                cur_lbl = QLabel(format_currency(acc.saldo_atual))
                cur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                cur_lbl.setStyleSheet("font-size: 12px; font-weight: 700;")
                prev_lbl = QLabel(f"Prev: {format_currency(acc.saldo_previsto)}")
                prev_lbl.setObjectName("MutedText")
                prev_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                prev_lbl.setStyleSheet("font-size: 10px;")
                val_col.addWidget(cur_lbl)
                val_col.addWidget(prev_lbl)
                rh.addLayout(val_col)

                self.acc_list_layout.addWidget(row_f)
            self.acc_list_layout.addStretch()

        # 2. Transações do mês
        occs = self.tx_service.list_occurrences(
            year, month, mode=mode, profile_id=profile_id
        )
        tx_sum = self.tx_service.summarize(occs)
        self.lbl_k_rec.setText(format_currency(tx_sum["receitas"]))
        self.lbl_k_rec_sub.setText(
            f"Recebido: {format_currency(tx_sum['receitas_efetivadas'])}"
        )
        self.lbl_k_desp.setText(format_currency(tx_sum["despesas"]))
        self.lbl_k_desp_sub.setText(
            f"Pago: {format_currency(tx_sum['despesas_pagas'])}"
        )

        # 3. Gráfico de Rosca de Despesas por Categoria + Legenda Tabular Alinhada (%)
        exp_cats = self.analytics.category_breakdown(
            year, month, kind=KIND_DESPESA, profile_id=profile_id, mode=mode
        )
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setBackgroundBrush(QColor(pal.surface_card))
        chart.setBackgroundRoundness(0.0)
        chart.setMargins(QMargins(0, 0, 0, 0))
        chart.legend().setVisible(False)
        series = QPieSeries()
        series.setHoleSize(0.56)
        series.setPieSize(0.84)
        if not exp_cats:
            sl = series.append("Sem despesas", 1.0)
            sl.setColor(QColor(pal.border_subtle))
            sl.setBorderColor(QColor(pal.surface_card))
        else:
            for r in exp_cats[:6]:
                sl = series.append(r.categoria_nome, max(0.01, abs(r.total)))
                sl.setColor(QColor(r.cor_hex))
                sl.setBorderColor(QColor(pal.surface_card))
                sl.setBorderWidth(2)
        chart.addSeries(series)
        self.chart_view.setChart(chart)

        self._clear_layout(self.cat_legend_layout)
        if not exp_cats:
            lbl_no_cat = QLabel("Sem despesas categorizadas no mês.")
            lbl_no_cat.setObjectName("MutedText")
            lbl_no_cat.setWordWrap(True)
            self.cat_legend_layout.addWidget(lbl_no_cat)
            self.cat_legend_layout.addStretch()
        else:
            for r in exp_cats[:6]:
                row_l = QHBoxLayout()
                row_l.setSpacing(8)
                dot = QLabel()
                dot.setFixedSize(10, 10)
                dot.setStyleSheet(f"background-color: {r.cor_hex}; border-radius: 5px;")
                row_l.addWidget(dot)

                lbl_cn = QLabel(r.categoria_nome)
                lbl_cn.setStyleSheet("font-size: 12px; font-weight: 500;")
                row_l.addWidget(lbl_cn, 1)

                lbl_cv = QLabel(format_currency(abs(r.total)))
                lbl_cv.setObjectName("MutedText")
                lbl_cv.setStyleSheet("font-size: 11px;")
                row_l.addWidget(lbl_cv)

                lbl_cp = QLabel(f"{r.percentual:.0f}%")
                lbl_cp.setMinimumWidth(34)
                lbl_cp.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                lbl_cp.setStyleSheet("font-size: 12px; font-weight: 700;")
                row_l.addWidget(lbl_cp)

                self.cat_legend_layout.addLayout(row_l)
            self.cat_legend_layout.addStretch()

        # 3.1 Gráfico de Barras Vertical: Resumo Mensal (6 meses)
        evo = self.analytics.monthly_evolution(
            year, month, months_count=6, profile_id=profile_id, mode=mode
        )
        m_chart = QChart()
        m_chart.setBackgroundVisible(False)
        m_chart.setPlotAreaBackgroundVisible(False)
        m_chart.setBackgroundBrush(QColor(pal.surface_card))
        m_chart.setBackgroundRoundness(12.0)
        m_chart.setMargins(QMargins(4, 4, 4, 4))

        set_rec = QBarSet("Receitas")
        set_rec.setColor(QColor(INCOME_GREEN))
        set_desp = QBarSet("Despesas")
        set_desp.setColor(QColor(EXPENSE_RED))
        m_cats = []
        max_mv = 100.0
        for p in evo:
            m_cats.append(p.label)
            set_rec.append(max(0.0, p.receitas))
            set_desp.append(max(0.0, p.despesas))
            max_mv = max(max_mv, p.receitas, p.despesas)

        b_series = QBarSeries()
        b_series.append(set_rec)
        b_series.append(set_desp)
        m_chart.addSeries(b_series)

        ax_x = QBarCategoryAxis()
        ax_x.append(m_cats)
        ax_x.setLabelsColor(QColor(pal.text_secondary))
        ax_x.setGridLineVisible(False)
        m_chart.addAxis(ax_x, Qt.AlignmentFlag.AlignBottom)
        b_series.attachAxis(ax_x)

        ax_y = QValueAxis()
        ax_y.setRange(0.0, max_mv * 1.15)
        ax_y.setLabelsColor(QColor(pal.text_secondary))
        ax_y.setGridLineColor(QColor(pal.border_subtle))
        m_chart.addAxis(ax_y, Qt.AlignmentFlag.AlignLeft)
        b_series.attachAxis(ax_y)

        m_chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        m_chart.legend().setLabelColor(QColor(pal.text_secondary))
        self.monthly_chart_view.setChart(m_chart)

        # 3.2 Banners de Itens Sem Categoria & Insight Rápido
        uncat = [
            o
            for o in occs
            if o.kind != KIND_TRANSFERENCIA
            and (
                not o.id_categoria
                or str(o.id_categoria).strip() in ("", "-1")
                or (o.categoria_nome or "").strip().lower() == "sem categoria"
            )
        ]
        if uncat:
            uncat_sum = sum(o.total for o in uncat)
            self.lbl_uncat_text.setText(
                f"Sem categoria: {format_currency(uncat_sum)} em {len(uncat)} lançamento(s), já nos totais acima."
            )
            self.uncat_banner.setVisible(True)
        else:
            self.uncat_banner.setVisible(False)

        res_val = tx_sum["resultado"]
        res_msg = (
            f"Resultado positivo de {format_currency(res_val)} no período."
            if res_val >= 0
            else f"Déficit atual de {format_currency(abs(res_val))} no período."
        )
        if exp_cats:
            top_cat = exp_cats[0]
            self.lbl_insight_text.setText(
                f"Categoria que mais consome: {top_cat.categoria_nome} ({top_cat.percentual:.0f}%) · {res_msg}"
            )
        else:
            self.lbl_insight_text.setText(f"Sem despesas categorizadas ainda · {res_msg}")

        # 4. Cartões de Crédito em lista limpa (sem tabela)
        invoices = self.card_service.list_cards_with_invoices(
            year, month, profile_id=profile_id
        )
        tot_faturas = sum(inv.total for inv in invoices)
        disp_total = sum(inv.disponivel for inv in invoices)
        self.lbl_k_cc.setText(format_currency(tot_faturas))
        self.lbl_k_cc_sub.setText(f"Disponível: {format_currency(disp_total)}")

        self._clear_layout(self.cards_list_layout)
        if not invoices:
            lbl_empty_cc = QLabel("Nenhum cartão de crédito cadastrado.")
            lbl_empty_cc.setObjectName("MutedText")
            lbl_empty_cc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_list_layout.addWidget(lbl_empty_cc)
        else:
            for idx, inv in enumerate(invoices):
                row_f = QFrame()
                row_f.setObjectName("DashListRow")
                row_f.setMinimumHeight(52)
                row_f.setStyleSheet(
                    f"QFrame#DashListRow {{ background: transparent; border: none; "
                    f"{f'border-bottom: 1px solid {pal.border_subtle};' if idx < len(invoices) - 1 else ''} }}"
                )
                rh = QHBoxLayout(row_f)
                rh.setContentsMargins(2, 4, 2, 4)
                rh.setSpacing(10)

                ico_lbl = QLabel()
                ico_lbl.setFixedSize(22, 22)
                icon = get_card_brand_icon(brand_icon_filename(inv.card.brand_key), size=20)
                ico_lbl.setPixmap(icon.pixmap(20, 20))
                rh.addWidget(ico_lbl)

                name_col = QVBoxLayout()
                name_col.setContentsMargins(0, 0, 0, 0)
                name_col.setSpacing(1)
                c_name = QLabel(inv.card.nome)
                c_name.setStyleSheet("font-size: 13px; font-weight: 600;")
                c_due = QLabel(f"Vence {format_date_br(inv.data_vencimento.isoformat())}")
                c_due.setObjectName("MutedText")
                c_due.setStyleSheet("font-size: 11px;")
                name_col.addWidget(c_name)
                name_col.addWidget(c_due)
                rh.addLayout(name_col, 1)

                variant = "success" if inv.paga else ("danger" if inv.status == "Vencida" else "warning")
                rh.addWidget(Badge(inv.status, variant=variant))

                v_lbl = QLabel(format_currency(inv.total))
                v_lbl.setMinimumWidth(90)
                v_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                v_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
                rh.addWidget(v_lbl)

                self.cards_list_layout.addWidget(row_f)
            self.cards_list_layout.addStretch()

        # 5. Orçamentos do Mês em cards limpos com progresso
        budgets = [
            b
            for b in self.budget_service.list_budgets_progress(
                year, month, profile_id=profile_id, mode=mode
            )
            if b.exibir_resumo
        ]
        self._clear_layout(self.budgets_list_layout)
        if not budgets:
            lbl_empty_b = QLabel("Nenhum orçamento marcado para exibir na Visão Geral.")
            lbl_empty_b.setObjectName("MutedText")
            lbl_empty_b.setStyleSheet("font-size: 12px; padding: 8px 0;")
            self.budgets_list_layout.addWidget(lbl_empty_b)
        else:
            for b in budgets[:6]:
                row_b = QFrame()
                row_b.setObjectName("DashBudgetRow")
                row_b.setStyleSheet(
                    f"QFrame#DashBudgetRow {{ background-color: {pal.app_background}; border: 1px solid {pal.border_subtle}; border-radius: 10px; }}"
                )
                rb = QHBoxLayout(row_b)
                rb.setContentsMargins(12, 10, 12, 10)
                rb.setSpacing(12)

                b_name = QLabel(b.nome_alvo)
                b_name.setStyleSheet("border: none; background: transparent; font-size: 13px; font-weight: 600;")
                b_name.setMinimumWidth(140)
                rb.addWidget(b_name)

                bar = QProgressBar()
                bar.setRange(0, 100)
                pct = min(100, max(0, int((b.utilizado / b.meta_mes) * 100))) if b.meta_mes > 0 else 0
                bar.setValue(pct)
                bar.setTextVisible(False)
                rb.addWidget(bar, 1)

                val_lbl = QLabel(f"{format_currency(b.utilizado)} / {format_currency(b.meta_mes)}")
                val_lbl.setObjectName("MutedText")
                val_lbl.setStyleSheet("border: none; background: transparent; font-size: 12px;")
                rb.addWidget(val_lbl)

                b_var = "success" if b.status_label == "Dentro da Meta" else ("danger" if b.status_label == "Estourado" else "warning")
                rb.addWidget(Badge(b.status_label, variant=b_var))

                self.budgets_list_layout.addWidget(row_b)
