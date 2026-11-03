"""Modal de Sincronização e Conciliação Open Finance (Pluggy) com QThread Assíncrona."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import EXPENSE_RED, INCOME_GREEN, PRIMARY_BLUE, ThemePalette
from app.database.connection_manager import ConnectionManager
from app.services.pluggy_client import (
    PluggyClient,
    PluggyConfigManager,
    PluggyConnectedItem,
)
from app.services.pluggy_sync_service import (
    PluggySyncService,
    SyncApplySummary,
    SyncBatchResult,
)
from app.ui.components import Badge
from app.ui.icons import get_line_icon
from app.ui.style_manager import format_currency


class OpenFinanceSyncWorker(QThread):
    """Worker em segundo plano para buscar contas, investimentos e transações na Pluggy."""

    progress_changed = Signal(int, str)
    sync_ready = Signal(list)  # List[SyncBatchResult]
    sync_failed = Signal(str)

    def __init__(
        self,
        client: PluggyClient,
        config_mgr: PluggyConfigManager,
        sync_service: PluggySyncService,
        profile_id: str = "1",
        days_back: int = 90,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.config_mgr = config_mgr
        self.sync_service = sync_service
        self.profile_id = profile_id
        self.days_back = days_back

    def run(self) -> None:
        try:
            self.progress_changed.emit(5, "Autenticando credenciais na Pluggy...")
            self.client.authenticate()

            cfg = self.config_mgr.load_config()
            items: List[PluggyConnectedItem] = list(cfg.items)
            if not items:
                self.progress_changed.emit(12, "Verificando instituições conectadas...")
                items = self.client.fetch_items(local_items=items)
                if items:
                    cfg.items = items
                    self.config_mgr.save_config(cfg)

            if not items:
                self.sync_failed.emit(
                    "Nenhuma instituição bancária cadastrada no Plutos.\n\n"
                    "Para sincronizar:\n"
                    "1. Vá em Configurações -> Open Finance (Pluggy).\n"
                    "2. Clique em 'Conectar Novo Banco' para autorizar seu banco no navegador.\n"
                    "3. Clique em 'Adicionar Conexão por ID' para vincular o ID gerado."
                )
                return

            from_date = (date.today() - timedelta(days=self.days_back)).isoformat()
            batches = self.sync_service.fetch_full_preview(
                items,
                profile_id=self.profile_id,
                from_date=from_date,
                progress_callback=lambda pct, msg: self.progress_changed.emit(pct, msg),
            )
            self.sync_ready.emit(batches)
        except Exception as exc:
            self.sync_failed.emit(str(exc))


class OpenFinanceSyncDialog(QDialog):
    """
    Modal de revisão e homologação da sincronização Open Finance (Pluggy).
    Executa a coleta em background (`QThread`) e exibe prévia detalhada antes de gravar no SQLite.
    """

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str = "1",
        mes: Optional[int] = None,
        ano: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.profile_id = profile_id
        self.mes = mes or date.today().month
        self.ano = ano or date.today().year

        self.config_mgr = PluggyConfigManager(self.db.settings.user_data_dir)
        cfg = self.config_mgr.load_config()
        self.client = PluggyClient(
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
        )
        self.sync_service = PluggySyncService(self.client, self.db)
        self._batches: List[SyncBatchResult] = []
        self.apply_summary: Optional[SyncApplySummary] = None
        self._worker: Optional[OpenFinanceSyncWorker] = None

        self.setWindowTitle("Sincronização Open Finance (Pluggy)")
        self.setMinimumSize(860, 620)
        self._build_ui()
        self._start_sync_worker()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Cabeçalho
        head = QHBoxLayout()
        t_col = QVBoxLayout()
        t_col.setSpacing(2)
        lbl_title = QLabel("Revisão de Sincronização Open Finance")
        lbl_title.setObjectName("SectionTitle")
        lbl_sub = QLabel(
            "Confira as contas, investimentos e lançamentos encontrados antes de efetivar no banco local"
        )
        lbl_sub.setObjectName("MutedText")
        t_col.addWidget(lbl_title)
        t_col.addWidget(lbl_sub)
        head.addLayout(t_col)
        head.addStretch()

        self.badge_state = Badge("Sincronizando...", variant="warning")
        head.addWidget(self.badge_state)
        root.addLayout(head)

        # Stack: Página 0 (Loading) / Página 1 (Revisão de Dados)
        self.stack = QStackedWidget()

        # --- Página 0: Progresso em Background ---
        page_loading = QFrame()
        page_loading.setObjectName("CardSurface")
        load_lay = QVBoxLayout(page_loading)
        load_lay.setContentsMargins(32, 48, 32, 48)
        load_lay.setSpacing(16)
        load_lay.addStretch()

        self.lbl_progress_status = QLabel("Iniciando comunicação segura com a Pluggy...")
        self.lbl_progress_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f_prog = QFont()
        f_prog.setBold(True)
        f_prog.setPointSize(11)
        self.lbl_progress_status.setFont(f_prog)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(5)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(12)

        lbl_load_hint = QLabel(
            "A sincronização roda em segundo plano sem travar o aplicativo. Aguarde alguns instantes..."
        )
        lbl_load_hint.setObjectName("MutedText")
        lbl_load_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        load_lay.addWidget(self.lbl_progress_status)
        load_lay.addWidget(self.progress_bar)
        load_lay.addWidget(lbl_load_hint)
        load_lay.addStretch()
        self.stack.addWidget(page_loading)

        # --- Página 1: Tabelas de Revisão ---
        page_review = QWidget()
        rev_lay = QVBoxLayout(page_review)
        rev_lay.setContentsMargins(0, 0, 0, 0)
        rev_lay.setSpacing(14)

        # Cards KPI de Resumo da Sincronização
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.card_contas, self.lbl_kpi_contas = self._create_mini_kpi(
            "Contas & Cartões", "0", PRIMARY_BLUE
        )
        self.card_inv, self.lbl_kpi_inv = self._create_mini_kpi(
            "Investimentos (Abordagem 1)", "0", PRIMARY_BLUE
        )
        self.card_novas, self.lbl_kpi_novas = self._create_mini_kpi(
            "Novos Lançamentos", "0", INCOME_GREEN
        )
        self.card_dup, self.lbl_kpi_dup = self._create_mini_kpi(
            "Duplicados Ignorados", "0", "#7B8190"
        )
        kpi_row.addWidget(self.card_contas)
        kpi_row.addWidget(self.card_inv)
        kpi_row.addWidget(self.card_novas)
        kpi_row.addWidget(self.card_dup)
        rev_lay.addLayout(kpi_row)

        # Tabela 1: Contas, Cartões e Investimentos
        lbl_acc_sec = QLabel("1. Contas Bancárias, Cartões e Investimentos Encontrados")
        f_sec = QFont()
        f_sec.setBold(True)
        lbl_acc_sec.setFont(f_sec)
        rev_lay.addWidget(lbl_acc_sec)

        self.table_accounts = QTableWidget(0, 5)
        self.table_accounts.setHorizontalHeaderLabels(
            ["Nome no Plutos", "Tipo", "Saldo / Posição Atual", "Novos Lanç.", "Ignorados (Dup.)"]
        )
        self.table_accounts.setShowGrid(False)
        self.table_accounts.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_accounts.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_accounts.verticalHeader().setVisible(False)
        self.table_accounts.verticalHeader().setDefaultSectionSize(36)
        self.table_accounts.setMaximumHeight(165)
        ah = self.table_accounts.horizontalHeader()
        ah.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ah.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table_accounts.setColumnWidth(1, 130)
        ah.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        rev_lay.addWidget(self.table_accounts)

        # Tabela 2: Novos Lançamentos para Efetivar
        lbl_tx_sec = QLabel("2. Novos Lançamentos Prontos para Importação")
        lbl_tx_sec.setFont(f_sec)
        rev_lay.addWidget(lbl_tx_sec)

        self.table_txs = QTableWidget(0, 6)
        self.table_txs.setHorizontalHeaderLabels(
            ["Data", "Descrição", "Conta / Cartão", "Categoria", "Tipo", "Valor"]
        )
        self.table_txs.setShowGrid(False)
        self.table_txs.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_txs.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_txs.verticalHeader().setVisible(False)
        self.table_txs.verticalHeader().setDefaultSectionSize(36)
        th = self.table_txs.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table_txs.setColumnWidth(4, 120)
        th.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        rev_lay.addWidget(self.table_txs, stretch=1)

        self.chk_reconcile = QCheckBox(
            "Reconciliar automaticamente o saldo atual das contas e investimentos com o saldo oficial do banco"
        )
        self.chk_reconcile.setChecked(True)
        rev_lay.addWidget(self.chk_reconcile)

        self.stack.addWidget(page_review)
        root.addWidget(self.stack, stretch=1)

        # Rodapé de botões
        footer = QHBoxLayout()
        footer.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_apply = QPushButton("Confirmar e Efetivar no Plutos")
        self.btn_apply.setObjectName("PrimaryButton")
        self.btn_apply.setIcon(get_line_icon("check", size=15, color="#FFFFFF"))
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_confirm_apply)

        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_apply)
        root.addLayout(footer)

    def _create_mini_kpi(self, title: str, value: str, accent_hex: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("CardSurface")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)
        lbl_t = QLabel(title)
        lbl_t.setObjectName("MutedText")
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {accent_hex};")
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        return card, lbl_v

    def _start_sync_worker(self) -> None:
        cfg = self.config_mgr.load_config()
        if not cfg.client_id or not cfg.client_secret:
            self.lbl_progress_status.setText(
                "Credenciais Pluggy não configuradas. Configure seu Client ID e Client Secret na aba Configurações."
            )
            self.badge_state.setText("Não configurado")
            return

        self._worker = OpenFinanceSyncWorker(
            client=self.client,
            config_mgr=self.config_mgr,
            sync_service=self.sync_service,
            profile_id=self.profile_id,
            parent=self,
        )
        self._worker.progress_changed.connect(self._on_worker_progress)
        self._worker.sync_ready.connect(self._on_worker_ready)
        self._worker.sync_failed.connect(self._on_worker_failed)
        self._worker.start()

    def _on_worker_progress(self, pct: int, message: str) -> None:
        self.progress_bar.setValue(pct)
        self.lbl_progress_status.setText(message)

    def _on_worker_failed(self, error_msg: str) -> None:
        self.badge_state.setText("Falha na Sincronização")
        self.lbl_progress_status.setText(f"Não foi possível concluir a sincronização:\n{error_msg}")
        QMessageBox.warning(self, "Aviso Open Finance", error_msg)

    def _on_worker_ready(self, batches: list) -> None:
        self._batches = batches
        self.badge_state.setText("Pronto para Revisão")
        self.populate_review_tables(batches)
        self.stack.setCurrentIndex(1)
        self.btn_apply.setEnabled(len(batches) > 0)

    def populate_review_tables(self, batches: List[SyncBatchResult]) -> None:
        """Popula as tabelas de revisão com o resultado da prévia (também usável diretamente em testes)."""
        self._batches = batches
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        total_contas = sum(1 for b in batches if b.account.tipo_plutos in ("CONTA", "CARTAO"))
        total_inv = sum(1 for b in batches if b.account.tipo_plutos == "INVESTIMENTO")
        total_novas = sum(b.total_novas for b in batches)
        total_dup = sum(b.total_duplicadas for b in batches)

        self.lbl_kpi_contas.setText(str(total_contas))
        self.lbl_kpi_inv.setText(str(total_inv))
        self.lbl_kpi_novas.setText(str(total_novas))
        self.lbl_kpi_dup.setText(str(total_dup))

        # 1. Tabela de Contas / Investimentos
        self.table_accounts.setRowCount(len(batches))
        all_new_txs = []
        for idx, b in enumerate(batches):
            acc = b.account
            it_name = QTableWidgetItem(acc.nome)
            f_bold = it_name.font()
            f_bold.setBold(True)
            it_name.setFont(f_bold)
            self.table_accounts.setItem(idx, 0, it_name)

            # Badge de tipo
            if acc.tipo_plutos == "INVESTIMENTO":
                t_badge = Badge("Investimento", variant="success")
            elif acc.tipo_plutos == "CARTAO":
                t_badge = Badge("Cartão Crédito", variant="warning")
            else:
                t_badge = Badge("Conta Bancária", variant="neutral")
            cw = QWidget()
            clay = QHBoxLayout(cw)
            clay.setContentsMargins(0, 0, 0, 0)
            clay.addWidget(t_badge)
            self.table_accounts.setCellWidget(idx, 1, cw)

            it_bal = QTableWidgetItem(format_currency(acc.saldo_atual))
            it_bal.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_bal.setFont(f_bold)
            self.table_accounts.setItem(idx, 2, it_bal)

            it_new = QTableWidgetItem(str(b.total_novas))
            it_new.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_accounts.setItem(idx, 3, it_new)

            it_dup = QTableWidgetItem(str(b.total_duplicadas))
            it_dup.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_dup.setForeground(QColor(pal.text_secondary))
            self.table_accounts.setItem(idx, 4, it_dup)

            for tx in b.novas_transacoes:
                all_new_txs.append((acc, tx))

        # 2. Tabela de Novos Lançamentos
        self.table_txs.setRowCount(len(all_new_txs))
        for idx, (acc, tx) in enumerate(all_new_txs):
            it_dt = QTableWidgetItem(tx.data_vencimento.strftime("%d/%m/%Y"))
            self.table_txs.setItem(idx, 0, it_dt)

            it_desc = QTableWidgetItem(tx.descricao)
            self.table_txs.setItem(idx, 1, it_desc)

            it_acc = QTableWidgetItem(acc.nome)
            it_acc.setForeground(QColor(pal.text_secondary))
            self.table_txs.setItem(idx, 2, it_acc)

            it_cat = QTableWidgetItem(tx.categoria or "Outros")
            self.table_txs.setItem(idx, 3, it_cat)

            is_rec = tx.kind.lower() == "receita"
            k_badge = Badge(
                "Receita" if is_rec else "Despesa",
                variant="success" if is_rec else "danger",
            )
            kw = QWidget()
            klay = QHBoxLayout(kw)
            klay.setContentsMargins(0, 0, 0, 0)
            klay.addWidget(k_badge)
            self.table_txs.setCellWidget(idx, 4, kw)

            it_val = QTableWidgetItem(format_currency(tx.valor))
            it_val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            f_v = it_val.font()
            f_v.setBold(True)
            it_val.setFont(f_v)
            it_val.setForeground(QColor(INCOME_GREEN if is_rec else EXPENSE_RED))
            self.table_txs.setItem(idx, 5, it_val)

        self.stack.setCurrentIndex(1)
        self.btn_apply.setEnabled(len(batches) > 0)

    def _on_confirm_apply(self) -> None:
        if not self._batches:
            return
        self.btn_apply.setEnabled(False)
        try:
            self.apply_summary = self.sync_service.apply_sync_results(
                self._batches,
                profile_id=self.profile_id,
                mes=self.mes,
                ano=self.ano,
                reconcile_balances=self.chk_reconcile.isChecked(),
            )
            s = self.apply_summary
            QMessageBox.information(
                self,
                "Sincronização Concluída",
                f"Dados do Open Finance efetivados com sucesso!\n\n"
                f"• Contas criadas/atualizadas: {s.contas_criadas + s.contas_atualizadas}\n"
                f"• Investimentos sincronizados: {s.investimentos_atualizados}\n"
                f"• Cartões sincronizados: {s.cartoes_sincronizados}\n"
                f"• Novos lançamentos importados: {s.transacoes_importadas}\n"
                f"• Duplicados ignorados: {s.duplicadas_ignoradas}",
            )
            self.accept()
        except Exception as exc:
            self.btn_apply.setEnabled(True)
            QMessageBox.critical(
                self,
                "Erro ao Aplicar Sincronização",
                f"Ocorreu um erro ao gravar os lançamentos no banco local:\n\n{exc}",
            )
