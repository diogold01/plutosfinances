"""Tela Nativa de Relatórios Analíticos (`RelatoriosView`)."""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
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
from app.ui.bank_icons import create_color_badge_icon
from app.ui.components import EmptyStateWidget, KpiCard
from app.ui.style_manager import format_currency


class RelatoriosView(QWidget):
    """
    Tela nativa de Relatórios Tabulares e Analíticos:
    - Despesas por Categoria / Subcategoria (com suporte a rateio multi-categoria)
    - Receitas por Categoria / Subcategoria
    - Fluxo de Caixa e Evolução Mensal (6 ou 12 meses)
    - Relatório por Tags
    - Relatório por Contas Bancárias e Cartões de Crédito
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

        # Cabeçalho e Seletor de Tipo de Relatório
        header_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        lbl_t = QLabel("Relatórios")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Análise detalhada por categorias, subcategorias, fluxo de caixa, tags, contas e cartões"
        )
        lbl_s.setObjectName("MutedText")
        title_col.addWidget(lbl_t)
        title_col.addWidget(lbl_s)
        header_row.addLayout(title_col)
        header_row.addStretch()

        filter_box = QHBoxLayout()
        filter_box.setSpacing(8)
        lbl_tipo = QLabel("Tipo de Relatório:")
        lbl_tipo.setStyleSheet("font-weight: 500;")

        self.cb_report_type = QComboBox()
        self.cb_report_type.setMinimumWidth(300)
        self.cb_report_type.addItem("Despesas por Categoria", "DESP_CAT")
        self.cb_report_type.addItem(
            "Despesas por Categoria e Subcategoria", "DESP_SUB"
        )
        self.cb_report_type.addItem("Receitas por Categoria", "REC_CAT")
        self.cb_report_type.addItem(
            "Fluxo de Caixa Mensal (Últimos 6 Meses)", "FLOW_6"
        )
        self.cb_report_type.addItem(
            "Fluxo de Caixa Anual (Últimos 12 Meses)", "FLOW_12"
        )
        self.cb_report_type.addItem("Agrupado por Tags (#)", "TAGS")
        self.cb_report_type.addItem("Agrupado por Contas e Cartões", "SOURCES")
        self.cb_report_type.addItem(
            "Compras / Repasses de Terceiros (Não-Operacionais)", "TERCEIROS"
        )
        self.cb_report_type.currentIndexChanged.connect(lambda _: self.refresh_data())

        filter_box.addWidget(lbl_tipo)
        filter_box.addWidget(self.cb_report_type)
        header_row.addLayout(filter_box)
        root.addLayout(header_row)

        # KPIs superiores
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(16)
        self.kpi_confirmed = KpiCard(
            title="Total Efetivado",
            value="R$ 0,00",
            subtitle="Confirmado no período",
            icon_name="check_circle",
            accent_color=INCOME_GREEN,
        )
        self.kpi_pending = KpiCard(
            title="Total Pendente",
            value="R$ 0,00",
            subtitle="Pendente no período",
            icon_name="clock",
            accent_color=EXPENSE_RED,
        )
        self.kpi_total = KpiCard(
            title="Soma Geral",
            value="R$ 0,00",
            subtitle="Resultado consolidado",
            icon_name="file_text",
            accent_color=PRIMARY_BLUE,
        )
        kpi_row.addWidget(self.kpi_confirmed, 1)
        kpi_row.addWidget(self.kpi_pending, 1)
        kpi_row.addWidget(self.kpi_total, 1)
        root.addLayout(kpi_row)

        # Card de Conteúdo da Tabela
        table_card = QFrame()
        table_card.setObjectName("CardSurface")
        card_lay = QVBoxLayout(table_card)
        card_lay.setContentsMargins(16, 16, 16, 16)
        card_lay.setSpacing(12)

        self.stack = QStackedWidget()

        self.table = QTableWidget(0, 6)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.stack.addWidget(self.table)

        self.empty_widget = EmptyStateWidget(
            title="Nenhum dado encontrado",
            subtitle="Não foram localizados registros para o relatório e período selecionados.",
            icon_name="file_text",
        )
        self.stack.addWidget(self.empty_widget)

        card_lay.addWidget(self.stack, stretch=1)
        root.addWidget(table_card, stretch=1)

    def refresh_data(self) -> None:
        profile_id, month, year, _search = self.get_context()
        mode = self.db.settings.date_reference_mode
        rtype = str(self.cb_report_type.currentData() or "DESP_CAT")
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        if rtype in ("FLOW_6", "FLOW_12"):
            months_cnt = 12 if rtype == "FLOW_12" else 6
            pts = self.analytics.monthly_evolution(
                year,
                month,
                months_count=months_cnt,
                profile_id=profile_id,
                mode=mode,
            )
            tot_rec = sum(p.receitas for p in pts)
            tot_desp = sum(p.despesas for p in pts)
            net_res = tot_rec - tot_desp

            self.kpi_confirmed.set_title("Receitas Acumuladas")
            self.kpi_confirmed.set_value(format_currency(tot_rec))
            self.kpi_confirmed.set_subtitle(f"Período de {months_cnt} meses")

            self.kpi_pending.set_title("Despesas Acumuladas")
            self.kpi_pending.set_value(format_currency(tot_desp))
            self.kpi_pending.set_subtitle(f"Período de {months_cnt} meses")

            self.kpi_total.set_title("Resultado Líquido")
            self.kpi_total.set_value(format_currency(net_res))
            self.kpi_total.set_subtitle("Receitas menos despesas")

            if not pts:
                self.stack.setCurrentWidget(self.empty_widget)
                return

            self.stack.setCurrentWidget(self.table)
            self.table.setColumnCount(5)
            self.table.setHorizontalHeaderLabels(
                [
                    "Competência (Mês/Ano)",
                    "Receitas",
                    "Despesas",
                    "Resultado Mensal",
                    "Saldo Previsto Contas",
                ]
            )
            hdr = self.table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

            self.table.setRowCount(0)
            f_bold = QFont()
            f_bold.setBold(True)

            for idx, p in enumerate(pts):
                self.table.insertRow(idx)

                it_lbl = QTableWidgetItem(p.label)
                it_lbl.setFont(f_bold)
                self.table.setItem(idx, 0, it_lbl)

                it_rec = QTableWidgetItem(format_currency(p.receitas))
                it_rec.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                it_rec.setForeground(QColor(INCOME_GREEN))
                self.table.setItem(idx, 1, it_rec)

                it_des = QTableWidgetItem(format_currency(p.despesas))
                it_des.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                it_des.setForeground(QColor(EXPENSE_RED))
                self.table.setItem(idx, 2, it_des)

                it_res = QTableWidgetItem(format_currency(p.resultado))
                it_res.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                it_res.setFont(f_bold)
                it_res.setForeground(
                    QColor(INCOME_GREEN if p.resultado >= 0 else EXPENSE_RED)
                )
                self.table.setItem(idx, 3, it_res)

                it_sld = QTableWidgetItem(format_currency(p.saldo_contas))
                it_sld.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                it_sld.setForeground(QColor(pal.text_primary))
                self.table.setItem(idx, 4, it_sld)
            return

        if rtype == "DESP_CAT":
            rows = self.analytics.category_breakdown(
                year, month, kind=KIND_DESPESA, profile_id=profile_id, mode=mode
            )
        elif rtype == "DESP_SUB":
            rows = self.analytics.category_breakdown(
                year,
                month,
                kind=KIND_DESPESA,
                profile_id=profile_id,
                mode=mode,
                group_by_subcategory=True,
            )
        elif rtype == "REC_CAT":
            rows = self.analytics.category_breakdown(
                year, month, kind=KIND_RECEITA, profile_id=profile_id, mode=mode
            )
        elif rtype == "TAGS":
            rows = self.analytics.tag_breakdown(
                year, month, profile_id=profile_id, mode=mode
            )
        elif rtype == "TERCEIROS":
            rows = self.analytics.third_party_breakdown(
                year, month, profile_id=profile_id, mode=mode
            )
        else:
            rows = self.analytics.source_breakdown(
                year, month, profile_id=profile_id, mode=mode
            )

        tot_ef = sum(r.efetivado for r in rows)
        tot_pd = sum(r.pendente for r in rows)
        tot_all = sum(r.total for r in rows)

        self.kpi_confirmed.set_title("Total Confirmado")
        self.kpi_confirmed.set_value(format_currency(tot_ef))
        self.kpi_confirmed.set_subtitle("Efetivado no período")

        self.kpi_pending.set_title("Total Pendente")
        self.kpi_pending.set_value(format_currency(tot_pd))
        self.kpi_pending.set_subtitle("A liquidar no período")

        self.kpi_total.set_title("Soma Geral")
        self.kpi_total.set_value(format_currency(tot_all))
        self.kpi_total.set_subtitle(f"{len(rows)} agrupamento(s)")

        if not rows:
            self.stack.setCurrentWidget(self.empty_widget)
            return

        self.stack.setCurrentWidget(self.table)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                "Grupo / Categoria",
                "Subcategoria / Detalhe",
                "Qtd.",
                "Efetivado",
                "Pendente",
                "Total e Participação",
            ]
        )
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setRowCount(0)
        f_bold = QFont()
        f_bold.setBold(True)

        for idx, r in enumerate(rows):
            self.table.insertRow(idx)

            it_cat = QTableWidgetItem(
                create_color_badge_icon(r.cor_hex, "", size=14),
                r.categoria_nome,
            )
            it_cat.setFont(f_bold)
            self.table.setItem(idx, 0, it_cat)

            it_sub = QTableWidgetItem(r.subcategoria_nome or "—")
            it_sub.setForeground(QColor(pal.text_secondary))
            self.table.setItem(idx, 1, it_sub)

            it_q = QTableWidgetItem(str(r.quantidade))
            it_q.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_q.setForeground(QColor(pal.text_secondary))
            self.table.setItem(idx, 2, it_q)

            it_ef = QTableWidgetItem(format_currency(r.efetivado))
            it_ef.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_ef.setForeground(QColor(INCOME_GREEN if rtype == "REC_CAT" else pal.text_primary))
            self.table.setItem(idx, 3, it_ef)

            it_pd = QTableWidgetItem(format_currency(r.pendente))
            it_pd.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_pd.setForeground(QColor(EXPENSE_RED if r.pendente > 0 else pal.text_secondary))
            self.table.setItem(idx, 4, it_pd)

            it_tot = QTableWidgetItem(f"{format_currency(r.total)} ({r.percentual:.1f}%)")
            it_tot.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_tot.setFont(f_bold)
            it_tot.setForeground(QColor(pal.text_primary))
            self.table.setItem(idx, 5, it_tot)
