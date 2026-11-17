"""Tela Nativa de Relatórios Analíticos (`RelatoriosView`)."""

from __future__ import annotations

from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import ai_key_store as key_store
from app.config.theme_palette import (
    EXPENSE_RED,
    INCOME_GREEN,
    PRIMARY_BLUE,
    ThemePalette,
)
from app.database.connection_manager import ConnectionManager
from app.domain.date_utils import add_months
from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.ai_service import AIService, FinancialHealthReport
from app.domain.services.analytics_service import AnalyticsService, FinancialHealthData
from app.ui.ai_worker import AICopilotWorker, FinancialHealthWorker
from app.ui.bank_icons import create_color_badge_icon
from app.ui.components import Badge, EmptyStateWidget, KpiCard
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import PT_BR_MONTHS, format_currency


class FinancialHealthPanel(QWidget):
    """
    Painel de Diagnóstico de Saúde Financeira com Inteligência Artificial (Google Gemini BYOK).
    Apresenta Score (0-100), Regra 50-30-20 comparativa, Alertas de Anomalias (vs 2 meses anteriores),
    Projeção de Fechamento do Mês e Recomendações Práticas Acionáveis.
    """

    def __init__(
        self,
        db: ConnectionManager,
        analytics: AnalyticsService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.analytics = analytics
        self.profile_id = "1"
        self.month = 10
        self.year = 2026
        self._current_report: Optional[FinancialHealthReport] = None
        self._current_health_data: Optional[FinancialHealthData] = None
        self._worker: Optional[FinancialHealthWorker] = None
        self._copilot_worker: Optional[AICopilotWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # Scroll vertical fluido
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self.content_lay = QVBoxLayout(content)
        self.content_lay.setContentsMargins(0, 0, 0, 16)
        self.content_lay.setSpacing(10)

        # 1. Header do Diagnóstico IA
        header_card = QFrame()
        header_card.setObjectName("CardSurface")
        h_lay = QHBoxLayout(header_card)
        h_lay.setContentsMargins(18, 12, 18, 12)
        h_lay.setSpacing(14)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_head = QLabel("Diagnóstico de Saúde Financeira com IA")
        lbl_head.setStyleSheet("font-size: 15px; font-weight: 700;")
        lbl_sub = QLabel(
            "Análise preditiva por IA com Score, proporção 50-30-20, detecção de anomalias e ações práticas."
        )
        lbl_sub.setObjectName("MutedText")
        title_col.addWidget(lbl_head)
        title_col.addWidget(lbl_sub)
        h_lay.addLayout(title_col, stretch=1)

        action_col = QVBoxLayout()
        action_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        action_col.setSpacing(4)

        self.btn_generate = QPushButton("✨ Gerar Diagnóstico IA")
        self.btn_generate.setObjectName("PrimaryButton")
        self.btn_generate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_generate.setMinimumHeight(34)
        self.btn_generate.setMinimumWidth(190)
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("MutedText")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight)

        action_col.addWidget(self.btn_generate)
        action_col.addWidget(self.lbl_status)
        h_lay.addLayout(action_col)

        self.content_lay.addWidget(header_card)

        # 2. Container de Estado Vazio / Prévia Local
        self.empty_card = QFrame()
        self.empty_card.setObjectName("CardSurface")
        e_lay = QVBoxLayout(self.empty_card)
        e_lay.setContentsMargins(20, 20, 20, 20)
        e_lay.setSpacing(10)
        e_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_e_ico = QLabel()
        lbl_e_ico.setPixmap(get_line_pixmap("sparkles", color="#5B5BD6", size=28))
        lbl_e_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_lay.addWidget(lbl_e_ico)

        self.lbl_empty_title = QLabel("Pronto para diagnosticar suas finanças")
        self.lbl_empty_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_lay.addWidget(self.lbl_empty_title)

        self.lbl_empty_desc = QLabel(
            "Clique no botão 'Gerar Diagnóstico IA' para processar suas receitas, "
            "despesas e médias dos últimos 2 meses através do Google Gemini.\n"
            "Seus dados financeiros permanecem 100% anônimos e sob sua chave privada (BYOK)."
        )
        self.lbl_empty_desc.setObjectName("MutedText")
        self.lbl_empty_desc.setWordWrap(True)
        self.lbl_empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_lay.addWidget(self.lbl_empty_desc)

        # Prévia das proporções calculadas localmente
        self.preview_box = QHBoxLayout()
        self.preview_box.setSpacing(12)
        self.lbl_p_ess = QLabel("Essenciais: —")
        self.lbl_p_est = QLabel("Estilo de Vida: —")
        self.lbl_p_pou = QLabel("Poupança: —")
        for lbl in (self.lbl_p_ess, self.lbl_p_est, self.lbl_p_pou):
            lbl.setStyleSheet(
                "background-color: rgba(123, 129, 144, 0.08); border-radius: 8px; "
                "padding: 8px 14px; font-weight: 500; font-size: 13px;"
            )
            self.preview_box.addWidget(lbl)
        e_lay.addSpacing(6)
        e_lay.addLayout(self.preview_box)

        self.content_lay.addWidget(self.empty_card)

        # 3. Container de Resultados da IA (inicialmente oculto)
        self.results_widget = QWidget()
        res_lay = QVBoxLayout(self.results_widget)
        res_lay.setContentsMargins(0, 0, 0, 0)
        res_lay.setSpacing(14)

        # Linha Superior: Score de Saúde + Resumo Executivo
        top_res_row = QHBoxLayout()
        top_res_row.setSpacing(14)

        # Card do Score
        self.score_card = QFrame()
        self.score_card.setObjectName("CardSurface")
        self.score_card.setMinimumWidth(240)
        sc_lay = QVBoxLayout(self.score_card)
        sc_lay.setContentsMargins(20, 16, 20, 16)
        sc_lay.setSpacing(4)
        sc_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_sc_title = QLabel("SCORE DE SAÚDE")
        lbl_sc_title.setObjectName("MutedText")
        lbl_sc_title.setStyleSheet("font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        sc_lay.addWidget(lbl_sc_title, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_score_num = QLabel("85")
        self.lbl_score_num.setStyleSheet("font-size: 42px; font-weight: 800; color: #1F9D6A;")
        sc_lay.addWidget(self.lbl_score_num, alignment=Qt.AlignmentFlag.AlignCenter)

        self.badge_score_status = Badge("Excelente", "success")
        sc_lay.addWidget(self.badge_score_status, alignment=Qt.AlignmentFlag.AlignCenter)

        self.lbl_score_delta = QLabel("")
        self.lbl_score_delta.setObjectName("MutedText")
        self.lbl_score_delta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_score_delta.setStyleSheet("font-size: 11px; font-weight: 600; margin-top: 4px;")
        self.lbl_score_delta.setVisible(False)
        sc_lay.addWidget(self.lbl_score_delta, alignment=Qt.AlignmentFlag.AlignCenter)

        top_res_row.addWidget(self.score_card)

        # Card do Resumo Executivo
        self.summary_card = QFrame()
        self.summary_card.setObjectName("CardSurface")
        sum_lay = QVBoxLayout(self.summary_card)
        sum_lay.setContentsMargins(20, 16, 20, 16)
        sum_lay.setSpacing(6)

        lbl_sum_head = QLabel("Resumo Executivo do Período")
        lbl_sum_head.setStyleSheet("font-size: 15px; font-weight: 600;")
        sum_lay.addWidget(lbl_sum_head)

        self.lbl_summary_text = QLabel("")
        self.lbl_summary_text.setWordWrap(True)
        self.lbl_summary_text.setStyleSheet("font-size: 13px; line-height: 1.4;")
        sum_lay.addWidget(self.lbl_summary_text)
        sum_lay.addStretch()
        top_res_row.addWidget(self.summary_card, stretch=1)

        res_lay.addLayout(top_res_row)

        # Card da Regra 50-30-20
        self.rule_card = QFrame()
        self.rule_card.setObjectName("CardSurface")
        r_lay = QVBoxLayout(self.rule_card)
        r_lay.setContentsMargins(20, 16, 20, 16)
        r_lay.setSpacing(10)

        lbl_r_title = QLabel("Distribuição Orçamentária — Regra 50-30-20")
        lbl_r_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        r_lay.addWidget(lbl_r_title)

        # Barra Essenciais (Meta 50%)
        self.lbl_bar_ess = QLabel("Gastos Essenciais: 0.0% (Meta ideal: até 50%)")
        self.bar_ess = QProgressBar()
        self.bar_ess.setFixedHeight(8)
        self.bar_ess.setTextVisible(False)
        self.bar_ess.setRange(0, 100)
        self.bar_ess.setStyleSheet(
            "QProgressBar { background-color: rgba(123, 129, 144, 0.15); border: none; border-radius: 99px; }"
            "QProgressBar::chunk { background-color: #1F9D6A; border-radius: 99px; }"
        )
        r_lay.addWidget(self.lbl_bar_ess)
        r_lay.addWidget(self.bar_ess)

        # Barra Estilo de Vida (Meta 30%)
        self.lbl_bar_est = QLabel("Estilo de Vida: 0.0% (Meta ideal: até 30%)")
        self.bar_est = QProgressBar()
        self.bar_est.setFixedHeight(8)
        self.bar_est.setTextVisible(False)
        self.bar_est.setRange(0, 100)
        self.bar_est.setStyleSheet(
            "QProgressBar { background-color: rgba(123, 129, 144, 0.15); border: none; border-radius: 99px; }"
            "QProgressBar::chunk { background-color: #E68A00; border-radius: 99px; }"
        )
        r_lay.addWidget(self.lbl_bar_est)
        r_lay.addWidget(self.bar_est)

        # Barra Poupança / Investimentos (Meta 20%)
        self.lbl_bar_pou = QLabel("Poupança / Investimentos: 0.0% (Meta ideal: 20% ou mais)")
        self.bar_pou = QProgressBar()
        self.bar_pou.setFixedHeight(8)
        self.bar_pou.setTextVisible(False)
        self.bar_pou.setRange(0, 100)
        self.bar_pou.setStyleSheet(
            "QProgressBar { background-color: rgba(123, 129, 144, 0.15); border: none; border-radius: 99px; }"
            "QProgressBar::chunk { background-color: #2F80ED; border-radius: 99px; }"
        )
        r_lay.addWidget(self.lbl_bar_pou)
        r_lay.addWidget(self.bar_pou)

        # Comentário da Regra
        self.lbl_rule_comment = QLabel("")
        self.lbl_rule_comment.setObjectName("MutedText")
        self.lbl_rule_comment.setWordWrap(True)
        self.lbl_rule_comment.setStyleSheet(
            "background-color: rgba(123, 129, 144, 0.06); border-radius: 8px; padding: 10px 14px; font-size: 13px;"
        )
        r_lay.addWidget(self.lbl_rule_comment)

        res_lay.addWidget(self.rule_card)

        # Linha Dupla: Alertas e Projeção
        mid_row = QHBoxLayout()
        mid_row.setSpacing(14)

        # Alertas de Anomalias
        self.alerts_card = QFrame()
        self.alerts_card.setObjectName("CardSurface")
        self.al_lay = QVBoxLayout(self.alerts_card)
        self.al_lay.setContentsMargins(20, 16, 20, 16)
        self.al_lay.setSpacing(10)
        lbl_al_head = QLabel("Alertas de Variações Atípicas (vs. Últimos 2 Meses)")
        lbl_al_head.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.al_lay.addWidget(lbl_al_head)

        self.alerts_list_widget = QWidget()
        self.alerts_list_lay = QVBoxLayout(self.alerts_list_widget)
        self.alerts_list_lay.setContentsMargins(0, 0, 0, 0)
        self.alerts_list_lay.setSpacing(6)
        self.al_lay.addWidget(self.alerts_list_widget)
        self.al_lay.addStretch()
        mid_row.addWidget(self.alerts_card, 1)

        # Projeção de Fechamento
        self.proj_card = QFrame()
        self.proj_card.setObjectName("CardSurface")
        pr_lay = QVBoxLayout(self.proj_card)
        pr_lay.setContentsMargins(20, 16, 20, 16)
        pr_lay.setSpacing(10)
        lbl_pr_head = QLabel("Projeção e Ritmo de Gastos")
        lbl_pr_head.setStyleSheet("font-size: 15px; font-weight: 600;")
        pr_lay.addWidget(lbl_pr_head)

        self.lbl_proj_text = QLabel("")
        self.lbl_proj_text.setWordWrap(True)
        self.lbl_proj_text.setStyleSheet("font-size: 13px; line-height: 1.4;")
        pr_lay.addWidget(self.lbl_proj_text)
        pr_lay.addStretch()
        mid_row.addWidget(self.proj_card, 1)

        res_lay.addLayout(mid_row)

        # Card de Recomendações Práticas Acionáveis
        self.recs_card = QFrame()
        self.recs_card.setObjectName("CardSurface")
        self.rec_lay = QVBoxLayout(self.recs_card)
        self.rec_lay.setContentsMargins(20, 16, 20, 16)
        self.rec_lay.setSpacing(10)

        lbl_rec_head = QLabel("Plano de Ação e Recomendações Priorizadas")
        lbl_rec_head.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.rec_lay.addWidget(lbl_rec_head)

        self.recs_list_widget = QWidget()
        self.recs_list_lay = QVBoxLayout(self.recs_list_widget)
        self.recs_list_lay.setContentsMargins(0, 0, 0, 0)
        self.recs_list_lay.setSpacing(6)
        self.rec_lay.addWidget(self.recs_list_widget)

        res_lay.addWidget(self.recs_card)

        self.results_widget.setVisible(False)
        self.content_lay.addWidget(self.results_widget)

        # 4. Card de Projeção de Caixa 30/60/90d & Radares Proativos (Local)
        self.proactive_card = QFrame()
        self.proactive_card.setObjectName("CardSurface")
        pr_card_lay = QVBoxLayout(self.proactive_card)
        pr_card_lay.setContentsMargins(20, 16, 20, 16)
        pr_card_lay.setSpacing(10)

        lbl_pro_head = QLabel("Projeção de Caixa (30 / 60 / 90 dias) & Radar Proativo")
        lbl_pro_head.setStyleSheet("font-size: 15px; font-weight: 600;")
        pr_card_lay.addWidget(lbl_pro_head)

        horiz_row = QHBoxLayout()
        horiz_row.setSpacing(12)
        self.lbl_cash_30d = QLabel("30 dias: —")
        self.lbl_cash_60d = QLabel("60 dias: —")
        self.lbl_cash_90d = QLabel("90 dias: —")
        for lbl_cash in (self.lbl_cash_30d, self.lbl_cash_60d, self.lbl_cash_90d):
            lbl_cash.setWordWrap(True)
            lbl_cash.setStyleSheet(
                "background-color: rgba(123, 129, 144, 0.08); border-radius: 8px; "
                "padding: 10px 14px; font-weight: 500; font-size: 13px;"
            )
            horiz_row.addWidget(lbl_cash, 1)
        pr_card_lay.addLayout(horiz_row)

        self.lbl_proactive_alerts = QLabel("")
        self.lbl_proactive_alerts.setObjectName("MutedText")
        self.lbl_proactive_alerts.setWordWrap(True)
        self.lbl_proactive_alerts.setStyleSheet("font-size: 12px;")
        pr_card_lay.addWidget(self.lbl_proactive_alerts)
        self.content_lay.addWidget(self.proactive_card)

        # 5. Card "Pergunte ao Copiloto Plutos" (Somente Leitura)
        self.copilot_card = QFrame()
        self.copilot_card.setObjectName("CardSurface")
        cp_lay = QVBoxLayout(self.copilot_card)
        cp_lay.setContentsMargins(20, 16, 20, 16)
        cp_lay.setSpacing(10)

        lbl_cp_head = QLabel("Pergunte ao Copiloto Plutos")
        lbl_cp_head.setStyleSheet("font-size: 15px; font-weight: 600;")
        lbl_cp_sub = QLabel(
            "Faça perguntas diretas sobre seus números agregados (análise consultiva, sem alterar lançamentos)."
        )
        lbl_cp_sub.setObjectName("MutedText")
        lbl_cp_sub.setWordWrap(True)
        cp_lay.addWidget(lbl_cp_head)
        cp_lay.addWidget(lbl_cp_sub)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        self.copilot_chips: list[QPushButton] = []
        for q_text in (
            "Posso parcelar uma compra de R$ 1.500?",
            "Quais gastos mais subiram neste trimestre?",
            "Como atingir 20% de poupança neste mês?",
        ):
            chip = QPushButton(q_text)
            chip.setObjectName("SecondaryButton")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(
                lambda _checked=False, qt=q_text: self._on_ask_copilot_clicked(qt)
            )
            chips_row.addWidget(chip)
            self.copilot_chips.append(chip)
        chips_row.addStretch()
        cp_lay.addLayout(chips_row)

        ask_row = QHBoxLayout()
        ask_row.setSpacing(10)
        self.txt_copilot_question = QLineEdit()
        self.txt_copilot_question.setPlaceholderText(
            "Ex.: Quanto posso gastar por semana até fechar o mês no positivo?"
        )
        self.txt_copilot_question.setMinimumHeight(34)
        self.txt_copilot_question.returnPressed.connect(
            lambda: self._on_ask_copilot_clicked()
        )
        ask_row.addWidget(self.txt_copilot_question, 1)

        self.btn_ask_copilot = QPushButton("Perguntar ao Copiloto")
        self.btn_ask_copilot.setObjectName("PrimaryButton")
        self.btn_ask_copilot.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ask_copilot.setMinimumHeight(34)
        self.btn_ask_copilot.clicked.connect(lambda: self._on_ask_copilot_clicked())
        ask_row.addWidget(self.btn_ask_copilot)
        cp_lay.addLayout(ask_row)

        self.lbl_copilot_answer = QLabel("")
        self.lbl_copilot_answer.setWordWrap(True)
        self.lbl_copilot_answer.setVisible(False)
        self.lbl_copilot_answer.setStyleSheet(
            "background-color: rgba(123, 129, 144, 0.08); border-radius: 8px; "
            "padding: 10px 14px; font-size: 13px;"
        )
        cp_lay.addWidget(self.lbl_copilot_answer)
        self.content_lay.addWidget(self.copilot_card)

        scroll.setWidget(content)
        root_lay.addWidget(scroll)

    def load_context(self, profile_id: str, month: int, year: int) -> None:
        """Atualiza o período de referência, projeção 30/60/90d e histórico salvo no SQLite."""
        prev_ctx = getattr(self, "_loaded_context_key", None)
        new_ctx = (profile_id, month, year)
        self.profile_id = profile_id
        self.month = month
        self.year = year
        self._loaded_context_key = new_ctx

        if prev_ctx is not None and prev_ctx != new_ctx:
            self.lbl_copilot_answer.setVisible(False)
            self.lbl_copilot_answer.setText("")

        health_data = self.analytics.get_financial_health_summary(
            self.year, self.month, profile_id=self.profile_id
        )
        self._current_health_data = health_data

        self.lbl_empty_title.setText(
            f"Pronto para diagnosticar suas finanças de {self.month:02d}/{self.year}"
        )
        self.lbl_p_ess.setText(f"🟢 Essenciais: {health_data.percentual_essenciais:.1f}%")
        self.lbl_p_est.setText(f"🟡 Estilo de Vida: {health_data.percentual_estilo_vida:.1f}%")
        self.lbl_p_pou.setText(f"🔵 Poupança/Investimento: {health_data.percentual_poupanca:.1f}%")
        self._update_proactive_cards(health_data)

        saved_report = self.analytics.load_health_report(
            self.year, self.month, profile_id=self.profile_id
        )
        if saved_report is not None:
            self._render_report(saved_report, from_cache=True)
        else:
            self._current_report = None
            self.btn_generate.setText("✨ Gerar Diagnóstico IA")
            self.lbl_status.setText("")
            self.results_widget.setVisible(False)
            self.empty_card.setVisible(True)

    def _update_proactive_cards(self, health_data: FinancialHealthData) -> None:
        labels = (self.lbl_cash_30d, self.lbl_cash_60d, self.lbl_cash_90d)
        horiz_names = ("30 dias", "60 dias", "90 dias")
        for idx, lbl in enumerate(labels):
            if idx < len(health_data.projecao_caixa_30_60_90):
                item = health_data.projecao_caixa_30_60_90[idx]
                saldo_p = format_currency(float(item.get("saldo_projetado", 0.0)))
                fatura_p = format_currency(float(item.get("faturas_cartao", 0.0)))
                per_p = item.get("periodo", "")
                lbl.setText(
                    f"{horiz_names[idx]} ({per_p})\nSaldo: {saldo_p} | Fatura: {fatura_p}"
                )
            else:
                lbl.setText(f"{horiz_names[idx]}: —")

        radar_parts: list[str] = []
        n_orc = len(health_data.orcamentos_em_risco)
        if n_orc:
            radar_parts.append(
                f"{n_orc} orçamento{'s' if n_orc != 1 else ''} em alerta/estouro no mês"
            )
        fut_cards = [
            float(c.get("total_faturas", 0.0))
            for c in health_data.comprometimento_cartoes_futuro
            if float(c.get("total_faturas", 0.0)) > 0
        ]
        if fut_cards:
            total_fut = format_currency(sum(fut_cards))
            radar_parts.append(f"Faturas comprometidas (próx. 90d): {total_fut}")
        n_goals = len(health_data.objetivos_ativos)
        if n_goals:
            radar_parts.append(
                f"{n_goals} objetivo{'s' if n_goals != 1 else ''} ativo{'s' if n_goals != 1 else ''} em andamento"
            )
        self.lbl_proactive_alerts.setText(
            " • ".join(radar_parts)
            if radar_parts
            else "Nenhum alerta de orçamento ou fatura futura crítica detectado no período."
        )

    def _on_generate_clicked(self) -> None:
        key, _src = key_store.resolve_gemini_key(self.db.settings.user_data_dir)
        if not key:
            self.lbl_status.setText("Chave Gemini não configurada (Configurações → IA).")
            self.lbl_status.setStyleSheet("color: #D64545; font-weight: 500;")
            return

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("⏳ Analisando com IA...")
        self.lbl_status.setText("Enviando métricas anonimizadas ao Gemini...")
        self.lbl_status.setStyleSheet("color: #7B8190;")

        health_data = self.analytics.get_financial_health_summary(
            self.year, self.month, profile_id=self.profile_id
        )
        self._current_health_data = health_data
        payload = health_data.to_ai_payload()

        service = AIService(key, model=self.db.settings.gemini_model)
        self._worker = FinancialHealthWorker(service, payload, parent=self)
        self._worker.succeeded.connect(self._on_worker_success)
        self._worker.failed.connect(self._on_worker_error)
        self._worker.start()

    def _on_worker_success(self, report: FinancialHealthReport) -> None:
        self.analytics.save_health_report(
            self.year, self.month, report, profile_id=self.profile_id
        )
        self._render_report(report, from_cache=False)

    def _render_report(
        self, report: FinancialHealthReport, *, from_cache: bool = False
    ) -> None:
        self._current_report = report
        self._report_period = (self.month, self.year)
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("✨ Atualizar Diagnóstico IA")
        if from_cache:
            self.lbl_status.setText("Diagnóstico carregado do histórico local.")
            self.lbl_status.setStyleSheet("color: #7B8190;")
        else:
            self.lbl_status.setText("Diagnóstico concluído com sucesso!")
            self.lbl_status.setStyleSheet("color: #1F9D6A;")

        # 1. Score, Delta vs Mês Anterior e Resumo
        self.lbl_score_num.setText(str(report.score_saude))
        if report.score_saude >= 70:
            self.lbl_score_num.setStyleSheet("font-size: 42px; font-weight: 800; color: #1F9D6A;")
            self.badge_score_status.setText("Saudável")
            self.badge_score_status.set_variant("success")
        elif report.score_saude >= 50:
            self.lbl_score_num.setStyleSheet("font-size: 42px; font-weight: 800; color: #E68A00;")
            self.badge_score_status.setText("Atenção")
            self.badge_score_status.set_variant("warning")
        else:
            self.lbl_score_num.setStyleSheet("font-size: 42px; font-weight: 800; color: #D64545;")
            self.badge_score_status.setText("Crítico")
            self.badge_score_status.set_variant("danger")

        prev_score = self.analytics.get_previous_health_score(
            self.year, self.month, profile_id=self.profile_id
        )
        if prev_score is not None:
            delta = report.score_saude - prev_score
            if delta > 0:
                self.lbl_score_delta.setText(f"▲ +{delta} pts vs. mês anterior")
                self.lbl_score_delta.setStyleSheet(
                    "color: #1F9D6A; font-size: 11px; font-weight: 600; margin-top: 4px;"
                )
            elif delta < 0:
                self.lbl_score_delta.setText(f"▼ {delta} pts vs. mês anterior")
                self.lbl_score_delta.setStyleSheet(
                    "color: #D64545; font-size: 11px; font-weight: 600; margin-top: 4px;"
                )
            else:
                self.lbl_score_delta.setText("• 0 pts vs. mês anterior")
                self.lbl_score_delta.setStyleSheet(
                    "color: #7B8190; font-size: 11px; font-weight: 600; margin-top: 4px;"
                )
            self.lbl_score_delta.setVisible(True)
        else:
            self.lbl_score_delta.setVisible(False)

        self.lbl_summary_text.setText(report.resumo)

        # 2. Regra 50-30-20
        self.lbl_bar_ess.setText(
            f"Gastos Essenciais: {report.essenciais_pct:.1f}% (Meta ideal: até 50%)"
        )
        self.bar_ess.setValue(int(min(100, max(0, report.essenciais_pct))))

        self.lbl_bar_est.setText(
            f"Estilo de Vida: {report.estilo_vida_pct:.1f}% (Meta ideal: até 30%)"
        )
        self.bar_est.setValue(int(min(100, max(0, report.estilo_vida_pct))))

        self.lbl_bar_pou.setText(
            f"Poupança / Investimentos: {report.poupanca_pct:.1f}% (Meta ideal: 20% ou mais)"
        )
        self.bar_pou.setValue(int(min(100, max(0, report.poupanca_pct))))

        self.lbl_rule_comment.setText(report.comentario_regra)

        # 3. Alertas de Anomalias
        while self.alerts_list_lay.count():
            item = self.alerts_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if report.alertas_anomalias:
            for alerta in report.alertas_anomalias:
                f = QFrame()
                f.setObjectName("HealthAlertFrame")
                f.setStyleSheet(
                    "QFrame#HealthAlertFrame { background-color: rgba(230, 138, 0, 0.08); "
                    "border-left: 3px solid #E68A00; border-radius: 6px; }"
                )
                flay = QHBoxLayout(f)
                flay.setContentsMargins(12, 8, 12, 8)
                flay.setSpacing(10)
                lbl_ico = QLabel("⚠️")
                lbl_ico.setStyleSheet(
                    "background: transparent; border: none; padding: 0px; font-size: 14px;"
                )
                lbl_txt = QLabel(alerta)
                lbl_txt.setWordWrap(True)
                lbl_txt.setStyleSheet(
                    "background: transparent; border: none; padding: 0px; font-size: 13px;"
                )
                flay.addWidget(lbl_ico)
                flay.addWidget(lbl_txt, 1)
                self.alerts_list_lay.addWidget(f)
        else:
            f = QFrame()
            f.setObjectName("HealthAlertOkFrame")
            f.setStyleSheet(
                "QFrame#HealthAlertOkFrame { background-color: rgba(31, 157, 106, 0.08); "
                "border-left: 3px solid #1F9D6A; border-radius: 6px; }"
            )
            flay = QHBoxLayout(f)
            flay.setContentsMargins(12, 8, 12, 8)
            flay.setSpacing(8)
            lbl_ico = QLabel("✓")
            lbl_ico.setStyleSheet(
                "background: transparent; border: none; padding: 0px; color: #1F9D6A; font-weight: bold;"
            )
            lbl_txt = QLabel("Nenhuma anomalia de gastos detectada em relação à média recente.")
            lbl_txt.setStyleSheet(
                "background: transparent; border: none; padding: 0px; font-size: 13px; color: #1F9D6A;"
            )
            flay.addWidget(lbl_ico)
            flay.addWidget(lbl_txt, 1)
            self.alerts_list_lay.addWidget(f)

        # 4. Projeção de Fechamento
        self.lbl_proj_text.setText(report.projecao_fechamento)

        # 5. Recomendações Práticas
        while self.recs_list_lay.count():
            item = self.recs_list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, rec in enumerate(report.recomendacoes_praticas, start=1):
            rf = QFrame()
            rf.setObjectName("HealthRecFrame")
            rf.setStyleSheet(
                "QFrame#HealthRecFrame { background-color: rgba(123, 129, 144, 0.08); "
                "border-radius: 8px; }"
            )
            rflay = QHBoxLayout(rf)
            rflay.setContentsMargins(12, 10, 12, 10)
            rflay.setSpacing(12)

            lbl_num = QLabel(str(idx))
            lbl_num.setFixedSize(24, 24)
            lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_num.setStyleSheet(
                "background-color: #5B5BD6; color: #FFFFFF; font-weight: 700; "
                "border-radius: 12px; font-size: 12px; padding: 0px; border: none;"
            )
            lbl_rec_txt = QLabel(rec)
            lbl_rec_txt.setWordWrap(True)
            lbl_rec_txt.setStyleSheet(
                "background: transparent; border: none; padding: 0px; font-size: 13px;"
            )

            rflay.addWidget(lbl_num)
            rflay.addWidget(lbl_rec_txt, 1)
            self.recs_list_lay.addWidget(rf)

        self.empty_card.setVisible(False)
        self.results_widget.setVisible(True)

    def _on_worker_error(self, error_msg: str) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("✨ Tentar Novamente")
        self.lbl_status.setText(f"Erro: {error_msg}")
        self.lbl_status.setStyleSheet("color: #D64545; font-weight: 500;")

    def _on_ask_copilot_clicked(self, preset_question: Optional[str] = None) -> None:
        if preset_question:
            self.txt_copilot_question.setText(preset_question)
        question = self.txt_copilot_question.text().strip()
        if not question:
            self.lbl_copilot_answer.setText("Digite uma pergunta para consultar o Copiloto.")
            self.lbl_copilot_answer.setStyleSheet(
                "background-color: rgba(214, 69, 69, 0.08); color: #D64545; "
                "border-radius: 8px; padding: 10px 14px; font-size: 13px;"
            )
            self.lbl_copilot_answer.setVisible(True)
            return

        key, _src = key_store.resolve_gemini_key(self.db.settings.user_data_dir)
        if not key:
            self.lbl_copilot_answer.setText(
                "Chave Gemini não configurada (Configurações → IA)."
            )
            self.lbl_copilot_answer.setStyleSheet(
                "background-color: rgba(214, 69, 69, 0.08); color: #D64545; "
                "border-radius: 8px; padding: 10px 14px; font-size: 13px;"
            )
            self.lbl_copilot_answer.setVisible(True)
            return

        self.btn_ask_copilot.setEnabled(False)
        self.btn_ask_copilot.setText("Consultando...")
        self.lbl_copilot_answer.setText("Analisando seus dados agregados locais...")
        self.lbl_copilot_answer.setStyleSheet(
            "background-color: rgba(123, 129, 144, 0.08); border-radius: 8px; "
            "padding: 10px 14px; font-size: 13px;"
        )
        self.lbl_copilot_answer.setVisible(True)

        health_data = self._current_health_data or self.analytics.get_financial_health_summary(
            self.year, self.month, profile_id=self.profile_id
        )
        snapshot = health_data.to_ai_payload()
        if self._current_report is not None:
            snapshot["ultimo_diagnostico"] = self._current_report.to_dict()

        service = AIService(key, model=self.db.settings.gemini_model)
        self._copilot_worker = AICopilotWorker(service, question, snapshot, parent=self)
        self._copilot_worker.succeeded.connect(self._on_copilot_success)
        self._copilot_worker.failed.connect(self._on_copilot_error)
        self._copilot_worker.start()

    def _on_copilot_success(self, answer: str) -> None:
        self.btn_ask_copilot.setEnabled(True)
        self.btn_ask_copilot.setText("Perguntar ao Copiloto")
        self.lbl_copilot_answer.setStyleSheet(
            "background-color: rgba(31, 157, 106, 0.08); border-left: 3px solid #1F9D6A; "
            "border-radius: 8px; padding: 10px 14px; font-size: 13px;"
        )
        self.lbl_copilot_answer.setText(answer)
        self.lbl_copilot_answer.setVisible(True)

    def _on_copilot_error(self, error_msg: str) -> None:
        self.btn_ask_copilot.setEnabled(True)
        self.btn_ask_copilot.setText("Perguntar ao Copiloto")
        self.lbl_copilot_answer.setStyleSheet(
            "background-color: rgba(214, 69, 69, 0.08); color: #D64545; "
            "border-radius: 8px; padding: 10px 14px; font-size: 13px;"
        )
        self.lbl_copilot_answer.setText(f"Erro: {error_msg}")
        self.lbl_copilot_answer.setVisible(True)


class FinancialClarityPanel(QWidget):
    """Painel de Clareza Financeira: matriz mensal DRE com heatmap suave e ranking de gastos."""

    def __init__(
        self,
        db: ConnectionManager,
        analytics: AnalyticsService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.analytics = analytics
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        host = QWidget()
        host.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(2, 2, 6, 8)
        lay.setSpacing(14)

        # 1. Matriz DRE com Heatmap (3 meses + Total + Média)
        self.dre_card = QFrame()
        self.dre_card.setObjectName("CardSurface")
        dre_lay = QVBoxLayout(self.dre_card)
        dre_lay.setContentsMargins(18, 16, 18, 16)
        dre_lay.setSpacing(10)

        lbl_dre_t = QLabel("Matriz Mensal por Categoria (DRE & Heatmap)")
        lbl_dre_t.setStyleSheet("font-size: 15px; font-weight: 700;")
        lbl_dre_sub = QLabel(
            "Comparativo dos últimos 3 meses, soma acumulada e média mensal por categoria"
        )
        lbl_dre_sub.setObjectName("MutedText")
        dre_lay.addWidget(lbl_dre_t)
        dre_lay.addWidget(lbl_dre_sub)

        self.tbl_dre = QTableWidget(0, 6)
        self.tbl_dre.setShowGrid(False)
        self.tbl_dre.verticalHeader().setVisible(False)
        self.tbl_dre.verticalHeader().setDefaultSectionSize(38)
        self.tbl_dre.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_dre.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tbl_dre.setMinimumHeight(260)
        dre_lay.addWidget(self.tbl_dre)
        lay.addWidget(self.dre_card)

        # 2. Ranking Horizontal de Maiores Gastos do Período
        self.ranking_card = QFrame()
        self.ranking_card.setObjectName("CardSurface")
        rk_lay = QVBoxLayout(self.ranking_card)
        rk_lay.setContentsMargins(18, 16, 18, 16)
        rk_lay.setSpacing(10)

        lbl_rk_t = QLabel("Maiores Gastos do Período")
        lbl_rk_t.setStyleSheet("font-size: 15px; font-weight: 700;")
        rk_lay.addWidget(lbl_rk_t)

        self.ranking_list_lay = QVBoxLayout()
        self.ranking_list_lay.setSpacing(8)
        rk_lay.addLayout(self.ranking_list_lay)
        lay.addWidget(self.ranking_card)

        lay.addStretch()
        scroll.setWidget(host)
        root.addWidget(scroll)

    def load_context(self, profile_id: str, month: int, year: int, mode: str) -> None:
        base_dt = date(year, month, 1)
        periods = [add_months(base_dt, offset) for offset in (-2, -1, 0)]
        headers = ["Categoria"] + [
            f"{PT_BR_MONTHS.get(p.month, str(p.month))[:3].upper()}/{str(p.year)[-2:]}"
            for p in periods
        ] + ["Total", "Média"]
        self.tbl_dre.setColumnCount(6)
        self.tbl_dre.setHorizontalHeaderLabels(headers)

        hdr = self.tbl_dre.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        # Coleta receitas e despesas por categoria para os 3 meses
        inc_map: Dict[str, List[float]] = {}
        exp_map: Dict[str, List[float]] = {}
        exp_colors: Dict[str, str] = {}

        for p_idx, p_dt in enumerate(periods):
            for r in self.analytics.category_breakdown(
                p_dt.year, p_dt.month, kind=KIND_RECEITA, profile_id=profile_id, mode=mode
            ):
                vals = inc_map.setdefault(r.categoria_nome, [0.0, 0.0, 0.0])
                vals[p_idx] += r.total
            for r in self.analytics.category_breakdown(
                p_dt.year, p_dt.month, kind=KIND_DESPESA, profile_id=profile_id, mode=mode
            ):
                vals = exp_map.setdefault(r.categoria_nome, [0.0, 0.0, 0.0])
                vals[p_idx] += r.total
                exp_colors[r.categoria_nome] = r.cor_hex

        max_inc = max((max(v) for v in inc_map.values()), default=0.0)
        max_exp = max((max(v) for v in exp_map.values()), default=0.0)

        self.tbl_dre.setRowCount(0)
        f_bold = QFont()
        f_bold.setBold(True)

        def _append_row(
            name: str,
            vals3: List[float],
            *,
            kind_tint: str = "",
            max_ref: float = 0.0,
            is_summary: bool = False,
        ) -> None:
            r_idx = self.tbl_dre.rowCount()
            self.tbl_dre.insertRow(r_idx)
            it_n = QTableWidgetItem(name)
            if is_summary:
                it_n.setFont(f_bold)
            self.tbl_dre.setItem(r_idx, 0, it_n)

            tot = round(sum(vals3), 2)
            avg = round(tot / 3.0, 2)
            for c_idx, val in enumerate([*vals3, tot, avg], start=1):
                it = QTableWidgetItem(format_currency(val))
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if is_summary:
                    it.setFont(f_bold)
                if c_idx <= 3 and max_ref > 0 and val > 0 and kind_tint:
                    ratio = min(1.0, val / max_ref)
                    alpha = int(18 + ratio * 65)
                    bg = QColor(22, 163, 74, alpha) if kind_tint == "inc" else QColor(220, 38, 38, alpha)
                    it.setBackground(bg)
                elif is_summary and kind_tint == "res":
                    col = QColor(22, 163, 74, 42) if val >= 0 else QColor(220, 38, 38, 42)
                    it.setBackground(col)
                self.tbl_dre.setItem(r_idx, c_idx, it)

        tot_inc_3 = [0.0, 0.0, 0.0]
        for cat_name, vals in sorted(inc_map.items(), key=lambda kv: sum(kv[1]), reverse=True):
            _append_row(f"  {cat_name}", vals, kind_tint="inc", max_ref=max_inc)
            for i in range(3):
                tot_inc_3[i] += vals[i]
        _append_row("Total Receitas", tot_inc_3, kind_tint="inc", is_summary=True)

        tot_exp_3 = [0.0, 0.0, 0.0]
        for cat_name, vals in sorted(exp_map.items(), key=lambda kv: sum(kv[1]), reverse=True):
            _append_row(f"  {cat_name}", vals, kind_tint="exp", max_ref=max_exp)
            for i in range(3):
                tot_exp_3[i] += vals[i]
        _append_row("Total Despesas", tot_exp_3, kind_tint="exp", is_summary=True)

        res_3 = [round(tot_inc_3[i] - tot_exp_3[i], 2) for i in range(3)]
        _append_row("Resultado Líquido", res_3, kind_tint="res", is_summary=True)

        # Ranking Maiores Gastos do mês ativo
        while self.ranking_list_lay.count():
            it = self.ranking_list_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        cur_exp = self.analytics.category_breakdown(
            year, month, kind=KIND_DESPESA, profile_id=profile_id, mode=mode
        )
        if not cur_exp:
            lbl_empty = QLabel("Nenhuma despesa registrada neste período.")
            lbl_empty.setObjectName("MutedText")
            self.ranking_list_lay.addWidget(lbl_empty)
            return

        top_val = max(r.total for r in cur_exp[:6]) or 1.0
        for row in cur_exp[:6]:
            item_w = QWidget()
            v_lay = QVBoxLayout(item_w)
            v_lay.setContentsMargins(0, 2, 0, 2)
            v_lay.setSpacing(4)

            top_h = QHBoxLayout()
            lbl_c = QLabel(row.categoria_nome)
            lbl_c.setStyleSheet("font-size: 13px; font-weight: 600;")
            lbl_v = QLabel(f"{format_currency(row.total)} ({row.percentual:.1f}%)")
            lbl_v.setStyleSheet("font-size: 12px; font-weight: 700;")
            top_h.addWidget(lbl_c)
            top_h.addStretch()
            top_h.addWidget(lbl_v)
            v_lay.addLayout(top_h)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(max(2, int(round((row.total / top_val) * 100.0))))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar_col = row.cor_hex or EXPENSE_RED
            bar.setStyleSheet(
                f"QProgressBar {{ background-color: rgba(148, 163, 184, 0.20); border: none; border-radius: 4px; }}"
                f"QProgressBar::chunk {{ background-color: {bar_col}; border-radius: 4px; }}"
            )
            v_lay.addWidget(bar)
            self.ranking_list_lay.addWidget(item_w)


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
        filter_box.setSpacing(10)

        # Botão de Destaque Imediato da IA (Acesso Direto com 1 Clique)
        self.btn_toggle_ai_report = QPushButton("Diagnóstico IA")
        self.btn_toggle_ai_report.setObjectName("SecondaryButton")
        self.btn_toggle_ai_report.setIcon(get_line_icon("sparkle", size=14, color="#5B5BD6"))
        self.btn_toggle_ai_report.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_ai_report.setMinimumHeight(32)
        self.btn_toggle_ai_report.setStyleSheet(
            "QPushButton { font-weight: 600; padding: 0 14px; border-radius: 8px; }"
        )
        self.btn_toggle_ai_report.setToolTip("Alternar entre Diagnóstico com IA e Relatórios em Tabela")
        self.btn_toggle_ai_report.clicked.connect(self._toggle_ai_report_mode)

        lbl_tipo = QLabel("Tipo de Relatório:")
        lbl_tipo.setStyleSheet("font-weight: 500;")

        self.cb_report_type = QComboBox()
        self.cb_report_type.setMinimumWidth(280)
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
        self.cb_report_type.addItem("Clareza Financeira (DRE & Heatmap)", "CLARITY")
        self.cb_report_type.addItem("✨ Diagnóstico & Saúde Financeira (IA)", "AI_HEALTH")
        self.cb_report_type.currentIndexChanged.connect(lambda _: self.refresh_data())

        filter_box.addWidget(lbl_tipo)
        filter_box.addWidget(self.cb_report_type)
        filter_box.addWidget(self.btn_toggle_ai_report)
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
            tint="positive",
        )
        self.kpi_pending = KpiCard(
            title="Total Pendente",
            value="R$ 0,00",
            subtitle="Pendente no período",
            icon_name="clock",
            accent_color=EXPENSE_RED,
            tint="negative",
        )
        self.kpi_total = KpiCard(
            title="Soma Geral",
            value="R$ 0,00",
            subtitle="Resultado consolidado",
            icon_name="file_text",
            accent_color=PRIMARY_BLUE,
            tint="info",
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

        self.health_panel = FinancialHealthPanel(self.db, self.analytics, self)
        self.stack.addWidget(self.health_panel)

        self.clarity_panel = FinancialClarityPanel(self.db, self.analytics, self)
        self.stack.addWidget(self.clarity_panel)

        card_lay.addWidget(self.stack, stretch=1)
        root.addWidget(table_card, stretch=1)

    def _toggle_ai_report_mode(self) -> None:
        """Alterna diretamente entre o Diagnóstico IA e o relatório em tabela."""
        current_type = str(self.cb_report_type.currentData() or "DESP_CAT")
        if current_type == "AI_HEALTH":
            idx = self.cb_report_type.findData("DESP_CAT")
        else:
            idx = self.cb_report_type.findData("AI_HEALTH")
        if idx >= 0:
            self.cb_report_type.setCurrentIndex(idx)

    def refresh_data(self) -> None:
        profile_id, month, year, _search = self.get_context()
        mode = self.db.settings.date_reference_mode
        rtype = str(self.cb_report_type.currentData() or "DESP_CAT")
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        # Atualiza o botão de alternância do cabeçalho
        if rtype == "AI_HEALTH":
            self.btn_toggle_ai_report.setText("Ver Tabelas")
            self.btn_toggle_ai_report.setIcon(get_line_icon("list", size=14))
            self.btn_toggle_ai_report.setToolTip("Retornar à visualização de tabelas e categorias")
        else:
            self.btn_toggle_ai_report.setText("Diagnóstico IA")
            self.btn_toggle_ai_report.setIcon(get_line_icon("sparkle", size=14, color="#5B5BD6"))
            self.btn_toggle_ai_report.setToolTip("Visualizar Diagnóstico de Saúde Financeira com IA")

        if rtype == "CLARITY":
            pts = self.analytics.monthly_evolution(
                year, month, months_count=1, profile_id=profile_id, mode=mode
            )
            cur_rec = pts[0].receitas if pts else 0.0
            cur_desp = pts[0].despesas if pts else 0.0
            self.kpi_confirmed.set_title("Receitas do Mês")
            self.kpi_confirmed.set_value(format_currency(cur_rec))
            self.kpi_confirmed.set_subtitle(f"Competência {month:02d}/{year}")

            self.kpi_pending.set_title("Despesas do Mês")
            self.kpi_pending.set_value(format_currency(cur_desp))
            self.kpi_pending.set_subtitle(f"Competência {month:02d}/{year}")

            self.kpi_total.set_title("Resultado Líquido")
            self.kpi_total.set_value(format_currency(cur_rec - cur_desp))
            self.kpi_total.set_subtitle("DRE simplificada (3 meses)")

            self.clarity_panel.load_context(profile_id, month, year, mode)
            self.stack.setCurrentWidget(self.clarity_panel)
            return

        if rtype == "AI_HEALTH":
            health_data = self.analytics.get_financial_health_summary(
                year, month, profile_id=profile_id
            )
            self.kpi_confirmed.set_title("Receitas do Mês")
            self.kpi_confirmed.set_value(format_currency(health_data.total_receitas))
            self.kpi_confirmed.set_subtitle(f"Competência {month:02d}/{year}")

            self.kpi_pending.set_title("Despesas do Mês")
            self.kpi_pending.set_value(format_currency(health_data.total_despesas))
            self.kpi_pending.set_subtitle(f"Competência {month:02d}/{year}")

            self.kpi_total.set_title("Resultado Líquido")
            self.kpi_total.set_value(format_currency(health_data.resultado_liquido))
            self.kpi_total.set_subtitle("Superávit / Déficit do período")

            self.health_panel.load_context(profile_id, month, year)
            self.stack.setCurrentWidget(self.health_panel)
            return

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
