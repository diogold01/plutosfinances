"""Tela Nativa de Visão Geral / Resumo Mensal (`DashboardView` / `OverviewGrid`)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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
from app.domain.models import KIND_DESPESA
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
from app.ui.components import Badge
from app.ui.icons import get_line_icon
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

        # 4 KPI Cards Superiores
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.k_saldo, self.lbl_k_saldo, self.lbl_k_saldo_sub = self._make_kpi(
            "Saldo em Contas", PRIMARY_BLUE
        )
        self.k_rec, self.lbl_k_rec, self.lbl_k_rec_sub = self._make_kpi(
            "Receitas do Mês", INCOME_GREEN
        )
        self.k_desp, self.lbl_k_desp, self.lbl_k_desp_sub = self._make_kpi(
            "Despesas do Mês", EXPENSE_RED
        )
        self.k_cc, self.lbl_k_cc, self.lbl_k_cc_sub = self._make_kpi(
            "Faturas de Cartão", WARNING_ORANGE
        )
        kpi_row.addWidget(self.k_saldo, 1)
        kpi_row.addWidget(self.k_rec, 1)
        kpi_row.addWidget(self.k_desp, 1)
        kpi_row.addWidget(self.k_cc, 1)
        root.addLayout(kpi_row)

        # Grid 2x2 de Cards
        grid = QGridLayout()
        grid.setSpacing(14)

        # Card 1: Minhas Contas
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

        self.tbl_acc = QTableWidget(0, 3)
        self.tbl_acc.setHorizontalHeaderLabels(
            ["Conta", "Saldo Atual", "Previsto"]
        )
        self.tbl_acc.setShowGrid(False)
        self.tbl_acc.verticalHeader().setVisible(False)
        self.tbl_acc.verticalHeader().setDefaultSectionSize(40)
        ah = self.tbl_acc.horizontalHeader()
        ah.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ah.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_acc.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_acc.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        acc_lay.addWidget(self.tbl_acc, stretch=1)
        grid.addWidget(c_acc, 0, 0)

        # Card 2: Despesas por Categoria (Rosca QtCharts)
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

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.chart_view.setStyleSheet("background: transparent;")
        pie_lay.addWidget(self.chart_view, stretch=1)
        grid.addWidget(c_pie, 0, 1)

        # Card 3: Faturas de Cartões de Crédito
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

        self.tbl_cards = QTableWidget(0, 4)
        self.tbl_cards.setHorizontalHeaderLabels(
            ["Cartão", "Vencimento", "Situação", "Valor"]
        )
        self.tbl_cards.setShowGrid(False)
        self.tbl_cards.verticalHeader().setVisible(False)
        self.tbl_cards.verticalHeader().setDefaultSectionSize(40)
        ch = self.tbl_cards.horizontalHeader()
        ch.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ch.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ch.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        ch.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_cards.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_cards.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tbl_cards.setIconSize(QSize(22, 22))
        cc_lay.addWidget(self.tbl_cards, stretch=1)
        grid.addWidget(c_cards, 1, 0)

        # Card 4: Orçamentos do Mês
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

        self.tbl_budgets = QTableWidget(0, 4)
        self.tbl_budgets.setHorizontalHeaderLabels(
            ["Alvo", "Meta", "Utilizado", "Situação"]
        )
        self.tbl_budgets.setShowGrid(False)
        self.tbl_budgets.verticalHeader().setVisible(False)
        self.tbl_budgets.verticalHeader().setDefaultSectionSize(40)
        bh = self.tbl_budgets.horizontalHeader()
        bh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        bh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        bh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        bh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_budgets.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_budgets.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        bud_lay.addWidget(self.tbl_budgets, stretch=1)
        grid.addWidget(c_bud, 1, 1)

        root.addLayout(grid, stretch=1)

    def _make_kpi(
        self, title: str, accent_hex: str
    ) -> Tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("KpiCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        lbl_t = QLabel(title.upper())
        lbl_t.setObjectName("MutedText")
        lbl_t.setStyleSheet("font-weight: 600; font-size: 11px; letter-spacing: 0.5px;")
        lbl_v = QLabel("R$ 0,00")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        lbl_v.setFont(f)
        lbl_v.setStyleSheet(f"color: {accent_hex};")
        lbl_s = QLabel("")
        lbl_s.setObjectName("MutedText")
        lbl_s.setStyleSheet("font-size: 11px;")
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        lay.addWidget(lbl_s)
        return card, lbl_v, lbl_s

    def refresh_data(self) -> None:
        profile_id, month, year, _ = self.get_context()
        mode = self.db.settings.date_reference_mode
        from app.config.theme_palette import ThemePalette
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        f_bold = QFont()
        f_bold.setBold(True)

        # 1. Contas
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

        self.tbl_acc.setRowCount(0)
        for idx, acc in enumerate(accounts):
            self.tbl_acc.insertRow(idx)
            it_n = QTableWidgetItem(get_bank_icon(acc.image_key, size=22), acc.descricao)
            self.tbl_acc.setItem(idx, 0, it_n)
            it_cur = QTableWidgetItem(format_currency(acc.saldo_atual))
            it_cur.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_cur.setFont(f_bold)
            self.tbl_acc.setItem(idx, 1, it_cur)
            it_prev = QTableWidgetItem(format_currency(acc.saldo_previsto))
            it_prev.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_prev.setForeground(QColor("#7B8190"))
            self.tbl_acc.setItem(idx, 2, it_prev)

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

        # 3. Gráfico de Rosca de Despesas por Categoria
        exp_cats = self.analytics.category_breakdown(
            year, month, kind=KIND_DESPESA, profile_id=profile_id, mode=mode
        )
        chart = QChart()
        chart.setBackgroundBrush(QColor(pal.surface_card))
        chart.setBackgroundRoundness(12.0)
        series = QPieSeries()
        series.setHoleSize(0.52)
        if not exp_cats:
            sl = series.append("Sem despesas no mês", 1.0)
            sl.setColor(QColor(pal.text_muted))
            sl.setBorderColor(QColor(pal.surface_card))
        else:
            for r in exp_cats[:6]:
                sl = series.append(
                    f"{r.categoria_nome} ({r.percentual:.0f}%)", max(0.01, abs(r.total))
                )
                sl.setColor(QColor(r.cor_hex))
                sl.setBorderColor(QColor(pal.surface_card))
                sl.setBorderWidth(2)
        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignRight)
        chart.legend().setLabelColor(QColor(pal.text_secondary))
        self.chart_view.setChart(chart)

        # 4. Cartões de Crédito
        invoices = self.card_service.list_cards_with_invoices(
            year, month, profile_id=profile_id
        )
        tot_faturas = sum(inv.total for inv in invoices)
        disp_total = sum(inv.disponivel for inv in invoices)
        self.lbl_k_cc.setText(format_currency(tot_faturas))
        self.lbl_k_cc_sub.setText(f"Disponível: {format_currency(disp_total)}")

        self.tbl_cards.setRowCount(0)
        for idx, inv in enumerate(invoices):
            self.tbl_cards.insertRow(idx)
            icon = get_card_brand_icon(
                brand_icon_filename(inv.card.brand_key), size=20
            )
            self.tbl_cards.setItem(idx, 0, QTableWidgetItem(icon, inv.card.nome))
            self.tbl_cards.setItem(
                idx,
                1,
                QTableWidgetItem(format_date_br(inv.data_vencimento.isoformat())),
            )
            variant = "success" if inv.paga else ("danger" if inv.status == "Vencida" else "warning")
            badge = Badge(inv.status, variant=variant)
            b_wrap = QWidget()
            b_lay = QHBoxLayout(b_wrap)
            b_lay.setContentsMargins(4, 2, 4, 2)
            b_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_lay.addWidget(badge)
            self.tbl_cards.setCellWidget(idx, 2, b_wrap)

            it_v = QTableWidgetItem(format_currency(inv.total))
            it_v.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_v.setFont(f_bold)
            self.tbl_cards.setItem(idx, 3, it_v)

        # 5. Orçamentos
        budgets = [
            b
            for b in self.budget_service.list_budgets_progress(
                year, month, profile_id=profile_id, mode=mode
            )
            if b.exibir_resumo
        ]
        self.tbl_budgets.setRowCount(0)
        for idx, b in enumerate(budgets):
            self.tbl_budgets.insertRow(idx)
            self.tbl_budgets.setItem(idx, 0, QTableWidgetItem(b.nome_alvo))
            self.tbl_budgets.setItem(
                idx, 1, QTableWidgetItem(format_currency(b.meta_mes))
            )
            it_u = QTableWidgetItem(format_currency(b.utilizado))
            it_u.setFont(f_bold)
            self.tbl_budgets.setItem(idx, 2, it_u)

            b_var = "success" if b.status_label == "Dentro da Meta" else ("danger" if b.status_label == "Estourado" else "warning")
            badge_b = Badge(b.status_label, variant=b_var)
            bb_wrap = QWidget()
            bb_lay = QHBoxLayout(bb_wrap)
            bb_lay.setContentsMargins(4, 2, 4, 2)
            bb_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bb_lay.addWidget(badge_b)
            self.tbl_budgets.setCellWidget(idx, 3, bb_wrap)
