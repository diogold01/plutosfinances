"""Tela Nativa de Ferramentas Complementares (`FerramentasView`: Importar/Exportar CSV & Excel, Empréstimos, Notas e Calculadora)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
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
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.domain.services.analytics_service import (
    AnalyticsService,
    LoanDTO,
    NoteDTO,
)
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService
from app.io_module.contracts import CSVColumnMapping, ExportReport, ImportReport
from app.io_module.io_orchestrator import DataIOOrchestrator
from app.ui.components import Badge
from app.ui.icons import get_line_icon
from app.ui.style_manager import format_currency, format_date_br


class LoanAmortizationDialog(QDialog):
    """Diálogo limpo para amortização parcial ou total de empréstimo com opção de movimentar conta bancária."""

    def __init__(
        self,
        loan: LoanDTO,
        account_repo: AccountRepository,
        profile_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.loan = loan
        self.setWindowTitle("Registrar Amortização de Empréstimo")
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_head = QLabel("Amortização / Pagamento")
        lbl_head.setObjectName("SectionTitle")
        lbl_sub = QLabel(
            f"<b>{loan.descricao}</b> ({loan.pessoa}) · "
            f"Principal: <b>{format_currency(loan.principal)}</b> · "
            f"Em Aberto: <b>{format_currency(loan.saldo_aberto)}</b>"
        )
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_head)
        title_box.addWidget(lbl_sub)
        lay.addLayout(title_box)

        form = QFormLayout()
        form.setSpacing(12)

        self.sp_valor = QDoubleSpinBox()
        self.sp_valor.setRange(0.01, max(0.01, float(loan.saldo_aberto) * 2.0))
        self.sp_valor.setDecimals(2)
        self.sp_valor.setPrefix("R$ ")
        self.sp_valor.setValue(float(loan.saldo_aberto))
        form.addRow("Valor Pago / Recebido:", self.sp_valor)

        self.dt_pagamento = QDateEdit()
        self.dt_pagamento.setCalendarPopup(True)
        self.dt_pagamento.setDisplayFormat("dd/MM/yyyy")
        self.dt_pagamento.setDate(QDate.currentDate())
        form.addRow("Data do Pagamento:", self.dt_pagamento)

        acao_str = "Creditar recebimento" if loan.concedido else "Debitar pagamento"
        self.chk_movimentar_conta = QCheckBox(
            f"{acao_str} no saldo de uma conta bancária"
        )
        self.chk_movimentar_conta.setChecked(True)
        form.addRow("", self.chk_movimentar_conta)

        self.cb_conta = QComboBox()
        for acc in account_repo.list_accounts(profile_id):
            self.cb_conta.addItem(f"Conta: {acc.descricao}", acc.id)
        form.addRow("Conta Bancária:", self.cb_conta)

        self.chk_movimentar_conta.toggled.connect(self.cb_conta.setEnabled)
        lay.addLayout(form)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("Confirmar Amortização")
        btn_ok.setObjectName("PrimaryButton")
        btn_cancel = bb.button(QDialogButtonBox.StandardButton.Cancel)
        btn_cancel.setText("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")

        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class FerramentasView(QWidget):
    """
    Módulo de Ferramentas Complementares:
    1. Importação e Exportação Modular CSV & Excel (`DataIOOrchestrator` / `modelos_csv`)
    2. Controle de Empréstimos (`emprestimos` e `emprestimos_vinculos`)
    3. Bloco de Notas Financeiras (`notas`)
    4. Calculadora Financeira de Juros Compostos
    """

    def __init__(
        self,
        db: ConnectionManager,
        get_context: Callable[[], Tuple[str, int, int, str]],
        on_data_mutated: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.get_context = get_context
        self.on_data_mutated = on_data_mutated
        self.tx_service = TransactionService(db)
        self.analytics = AnalyticsService(db, self.tx_service)
        self.account_repo = AccountRepository(db)
        self.cat_repo = CategoryRepository(db)
        self.card_service = CreditCardService(db, self.tx_service)
        self.io_orchestrator = DataIOOrchestrator(db, self.tx_service)
        self._loans: List[LoanDTO] = []
        self._notes: List[NoteDTO] = []
        self._csv_mappings: List[CSVColumnMapping] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_t = QLabel("Ferramentas")
        lbl_t.setObjectName("SectionTitle")
        lbl_s = QLabel(
            "Importação e exportação de planilhas, controle de empréstimos, notas e simulador de juros"
        )
        lbl_s.setObjectName("MutedText")
        title_box.addWidget(lbl_t)
        title_box.addWidget(lbl_s)
        root.addLayout(title_box)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_io_tab(), "Importar e Exportar")
        self.tabs.addTab(self._build_loans_tab(), "Empréstimos")
        self.tabs.addTab(self._build_notes_tab(), "Notas e Lembretes")
        self.tabs.addTab(self._build_calc_tab(), "Simulador de Juros")
        root.addWidget(self.tabs, stretch=1)

    # ------------------------------------------------------------------ #
    # ABA 1: IMPORTAR / EXPORTAR (CSV & EXCEL)
    # ------------------------------------------------------------------ #
    def _build_io_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(16)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        # Card Esquerdo: Importação
        imp_card = QFrame()
        imp_card.setObjectName("CardSurface")
        imp_lay = QVBoxLayout(imp_card)
        imp_lay.setContentsMargins(20, 18, 20, 18)
        imp_lay.setSpacing(12)

        lbl_imp = QLabel("Importar Extrato ou Fatura (.csv / .xlsx)")
        f_bold = QFont()
        f_bold.setPointSize(11)
        f_bold.setBold(True)
        lbl_imp.setFont(f_bold)
        imp_lay.addWidget(lbl_imp)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.ed_import_path = QLineEdit()
        self.ed_import_path.setPlaceholderText(
            "Selecione um arquivo .csv ou .xlsx para importar..."
        )
        btn_browse_imp = QPushButton("Procurar...")
        btn_browse_imp.setObjectName("SecondaryButton")
        btn_browse_imp.clicked.connect(self._browse_import_file)
        file_row.addWidget(self.ed_import_path, stretch=1)
        file_row.addWidget(btn_browse_imp)
        imp_lay.addLayout(file_row)

        imp_form = QFormLayout()
        imp_form.setSpacing(10)

        self.cb_imp_target = QComboBox()
        imp_form.addRow("Conta / Cartão Alvo:", self.cb_imp_target)

        self.cb_imp_kind = QComboBox()
        self.cb_imp_kind.addItem("Despesas (Padrão)", "despesa")
        self.cb_imp_kind.addItem("Receitas", "receita")
        self.cb_imp_kind.addItem("Transferências", "transferencia")
        imp_form.addRow("Natureza Padrão:", self.cb_imp_kind)

        self.cb_imp_mapping = QComboBox()
        imp_form.addRow("Modelo de Mapeamento:", self.cb_imp_mapping)

        self.chk_skip_dup = QCheckBox(
            "Prevenir duplicidade automaticamente (assinatura SHA-256)"
        )
        self.chk_skip_dup.setChecked(True)
        imp_form.addRow("", self.chk_skip_dup)

        imp_lay.addLayout(imp_form)

        imp_btn_row = QHBoxLayout()
        imp_btn_row.setSpacing(8)
        self.btn_run_import = QPushButton("Executar Importação")
        self.btn_run_import.setObjectName("PrimaryButton")
        self.btn_run_import.setIcon(get_line_icon("download", size=14, color="#FFFFFF"))
        self.btn_run_import.clicked.connect(self._on_run_import_clicked)

        self.btn_save_mapping = QPushButton("Salvar Modelo CSV")
        self.btn_save_mapping.setObjectName("SecondaryButton")
        self.btn_save_mapping.clicked.connect(self._on_save_default_mapping)

        self.btn_copy_ai_prompt = QPushButton("Copiar Prompt p/ IA")
        self.btn_copy_ai_prompt.setObjectName("SecondaryButton")
        self.btn_copy_ai_prompt.setIcon(get_line_icon("copy", size=14))
        self.btn_copy_ai_prompt.setToolTip(
            "Copia um prompt estruturado com suas categorias e contas para colar no ChatGPT, "
            "Claude ou Gemini e fazer a IA gerar o arquivo .csv pronto para importação no Plutos."
        )
        self.btn_copy_ai_prompt.clicked.connect(self._copy_ai_prompt_to_clipboard)

        imp_btn_row.addWidget(self.btn_run_import)
        imp_btn_row.addWidget(self.btn_save_mapping)
        imp_btn_row.addWidget(self.btn_copy_ai_prompt)
        imp_btn_row.addStretch()
        imp_lay.addLayout(imp_btn_row)

        self.lbl_import_status = QLabel("Nenhuma importação executada nesta sessão.")
        self.lbl_import_status.setObjectName("MutedText")
        self.lbl_import_status.setWordWrap(True)
        imp_lay.addWidget(self.lbl_import_status)
        imp_lay.addStretch()

        # Card Direito: Exportação
        exp_card = QFrame()
        exp_card.setObjectName("CardSurface")
        exp_lay = QVBoxLayout(exp_card)
        exp_lay.setContentsMargins(20, 18, 20, 18)
        exp_lay.setSpacing(12)

        lbl_exp = QLabel("Exportar Dados Financeiros (.xlsx / .csv)")
        lbl_exp.setFont(f_bold)
        exp_lay.addWidget(lbl_exp)

        exp_form = QFormLayout()
        exp_form.setSpacing(10)

        self.cb_exp_mode = QComboBox()
        self.cb_exp_mode.addItem(
            "Extrato Consolidado do Mês (Template Extrato)", "extrato"
        )
        self.cb_exp_mode.addItem(
            "Despesas Detalhadas (Template Oficial Despesas)", "despesas"
        )
        self.cb_exp_mode.addItem(
            "Receitas Detalhadas (Template Oficial Receitas)", "receitas"
        )
        self.cb_exp_mode.addItem(
            "Transferências (Template Oficial Transferências)", "transferencias"
        )
        self.cb_exp_mode.addItem(
            "Resumo por Categoria (Template Oficial Categorias)", "categorias"
        )
        self.cb_exp_mode.addItem(
            "Pasta de Trabalho Completa Multi-Abas (.xlsx)", "completo"
        )
        exp_form.addRow("Escopo / Template:", self.cb_exp_mode)

        self.cb_exp_format = QComboBox()
        self.cb_exp_format.addItem("Planilha Excel (.xlsx)", "xlsx")
        self.cb_exp_format.addItem("Arquivo CSV UTF-8 (.csv)", "csv")
        exp_form.addRow("Formato de Arquivo:", self.cb_exp_format)

        exp_file_row = QHBoxLayout()
        exp_file_row.setSpacing(8)
        self.ed_export_path = QLineEdit()
        self.ed_export_path.setPlaceholderText(
            "Caminho de destino (ou clique em Exportar)..."
        )
        btn_browse_exp = QPushButton("Procurar...")
        btn_browse_exp.setObjectName("SecondaryButton")
        btn_browse_exp.clicked.connect(self._browse_export_file)
        exp_file_row.addWidget(self.ed_export_path, stretch=1)
        exp_file_row.addWidget(btn_browse_exp)
        exp_form.addRow("Arquivo Destino:", exp_file_row)

        exp_lay.addLayout(exp_form)

        self.btn_run_export = QPushButton("Executar Exportação")
        self.btn_run_export.setObjectName("PrimaryButton")
        self.btn_run_export.setIcon(get_line_icon("upload", size=14, color="#FFFFFF"))
        self.btn_run_export.clicked.connect(self._on_run_export_clicked)
        exp_lay.addWidget(self.btn_run_export, alignment=Qt.AlignmentFlag.AlignLeft)

        self.lbl_export_status = QLabel("Pronto para exportar dados do período selecionado.")
        self.lbl_export_status.setObjectName("MutedText")
        self.lbl_export_status.setWordWrap(True)
        exp_lay.addWidget(self.lbl_export_status)
        exp_lay.addStretch()

        cards_row.addWidget(imp_card, 1)
        cards_row.addWidget(exp_card, 1)
        lay.addLayout(cards_row, stretch=1)
        return page

    def _reload_io_Selectors(self, profile_id: str) -> None:
        self.cb_imp_target.clear()
        self.cb_imp_target.addItem("Automático (Pela coluna Conta/Cartão da planilha)", "")
        for acc in self.account_repo.list_accounts(profile_id):
            self.cb_imp_target.addItem(f"Conta: {acc.name}", f"ACC:{acc.id}")
        for card in self.card_service.list_cards(profile_id):
            self.cb_imp_target.addItem(f"Cartão: {card.nome}", f"CARD:{card.id}")

        self._csv_mappings = self.io_orchestrator.list_csv_mappings()
        self.cb_imp_mapping.clear()
        self.cb_imp_mapping.addItem(
            "Detecção Automática de Cabeçalhos (Padrão)", None
        )
        for m in self._csv_mappings:
            self.cb_imp_mapping.addItem(
                f"{m.descricao_modelo} (sep '{m.separador}', {m.formato_data})",
                m.id,
            )

    def _browse_import_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Planilha CSV ou Excel para Importar",
            "",
            "Planilhas (*.csv *.xlsx);;Arquivos CSV (*.csv);;Planilhas Excel (*.xlsx)",
        )
        if file_path:
            self.ed_import_path.setText(file_path)

    def _browse_export_file(self) -> None:
        fmt = str(self.cb_exp_format.currentData() or "xlsx")
        mode = str(self.cb_exp_mode.currentData() or "extrato")
        _, month, year, _ = self.get_context()
        default_name = f"plutos_{mode}_{year}_{month:02d}.{fmt}"
        filter_str = (
            "Planilha Excel (*.xlsx)"
            if fmt == "xlsx"
            else "Arquivo CSV (*.csv)"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Exportação", default_name, filter_str
        )
        if file_path:
            self.ed_export_path.setText(file_path)

    def _on_save_default_mapping(self) -> None:
        mapping = CSVColumnMapping(
            descricao_modelo="Extrato Bancário PT-BR (;)",
            separador=";",
            possui_cabecalho=True,
            formato_data="dd/MM/yyyy",
            valor_negativo_despesas=True,
            col_data=0,
            col_descricao=1,
            col_valor=2,
            col_categoria=3,
            col_subcategoria=4,
        )
        self.io_orchestrator.save_csv_mapping(mapping)
        profile_id, _, _, _ = self.get_context()
        self._reload_io_Selectors(profile_id)
        self.lbl_import_status.setText(
            f"Modelo '{mapping.descricao_modelo}' salvo em `modelos_csv`."
        )

    def build_ai_import_prompt(self, profile_id: Optional[str] = None) -> str:
        """Gera um prompt completo e estruturado para LLMs converterem faturas/extratos para CSV do Plutos."""
        pid = profile_id or self.get_context()[0]
        exp_categories = self.cat_repo.list_categories("DESPESA", profile_id=pid)
        inc_categories = self.cat_repo.list_categories("RECEITA", profile_id=pid)

        cat_exp_lines: List[str] = []
        for c in exp_categories:
            if c.archived:
                continue
            subs = [s.nome for s in c.subcategories if not s.archived]
            sub_str = f" ({', '.join(subs)})" if subs else ""
            cat_exp_lines.append(f"- {c.nome}{sub_str}")

        cat_inc_lines: List[str] = []
        for c in inc_categories:
            if c.archived:
                continue
            subs = [s.nome for s in c.subcategories if not s.archived]
            sub_str = f" ({', '.join(subs)})" if subs else ""
            cat_inc_lines.append(f"- {c.nome}{sub_str}")

        cat_exp_block = (
            "\n".join(cat_exp_lines)
            if cat_exp_lines
            else "- Alimentação (Supermercado, Restaurante)\n- Transporte (Combustível, Uber)\n- Moradia (Aluguel, Luz, Internet)"
        )
        cat_inc_block = (
            "\n".join(cat_inc_lines)
            if cat_inc_lines
            else "- Salário (Salário, Adiantamento)\n- Rendimentos (Investimentos)\n- Outras Receitas"
        )

        accounts = self.account_repo.list_accounts(pid)
        acc_names = [a.descricao for a in accounts]
        cards = self.card_service.list_cards(pid)
        card_names = [c.nome for c in cards]
        acc_str = ", ".join(acc_names) if acc_names else "Minha Conta Corrente"
        card_str = ", ".join(card_names) if card_names else "Nubank, Mercado Livre"

        return (
            "Você é um assistente especialista em organização financeira pessoal para o aplicativo Plutos.\n"
            "Converta o texto bruto de fatura de cartão, extrato bancário ou lista de despesas colado abaixo "
            "em uma tabela CSV com separador ponto e vírgula (;), pronta para importação direta no Plutos.\n\n"
            "REGRAS DE FORMATAÇÃO OBRIGATÓRIAS:\n"
            "1. A primeira linha DEVE ser exatamente este cabeçalho:\n"
            "data;descricao;valor;tipo;categoria;subcategoria;conta_cartao;parcela;observacao\n"
            "(Nota: compatível também com o cabeçalho clássico: data;descricao;valor;categoria;subcategoria;conta_cartao;parcela;observacao)\n\n"
            "2. Formato de data: dd/MM/yyyy (Ex.: 02/10/2026)\n"
            "3. Formato de valor: número positivo com vírgula como separador decimal (Ex.: 45,90 ou 1250,00)\n"
            "4. Coluna 'tipo': deve ser estritamente 'Despesa' para saídas/gastos e 'Receita' para entradas "
            "(salários, pix recebidos, transferências recebidas, reembolsos, rendimentos).\n\n"
            "5. HIGIENIZAÇÃO E LIMPEZA DAS DESCRIÇÕES (MUITO IMPORTANTE):\n"
            "   - Remova prefixos de adquirentes, maquininhas e gateways de pagamento:\n"
            "     * 'Pag*Steam' ou 'Wl *Steam Purchase' -> 'Steam'\n"
            "     * 'Mp *Pichau' -> 'Pichau'\n"
            "     * 'Dl *Aliexpress Br Alip' -> 'AliExpress'\n"
            "     * 'Mercadolivre*Maxcostor' -> 'Mercado Livre - Maxcostor'\n"
            "     * 'Google Youtube' -> 'YouTube'\n"
            "     * 'Boleto no Crédito - SOCIEDADE EDUCACIONAL...' -> 'Faculdade Leonardo da Vinci'\n"
            "     * 'IOF de compra internacional' -> 'IOF Compra Internacional'\n"
            "   - Não inclua o número da parcela na coluna 'descricao' quando preencher a coluna 'parcela'.\n"
            "   - Escreva nomes próprios em formato legível (Title Case), nunca tudo em CAIXA ALTA.\n\n"
            "6. REGRA DE PARCELAS E PROJEÇÃO FUTURA (COLUNA 'parcela'):\n"
            "   - Se for compra à vista / lançamento único: preencha a coluna 'parcela' com '1/1'.\n"
            "   - Se for compra parcelada ('Parcela X/N', 'X/N' ou 'Parcela X de N'):\n"
            "     a) Preencha a coluna 'parcela' com 'X/N' (ex: 2/6, 8/12).\n"
            "     b) Se X for menor que N (ainda restam parcelas futuras), VOCÊ DEVE GERAR E PROJETAR TODAS AS PARCELAS RESTANTES (X+1/N, ..., N/N):\n"
            "        - Avance a data em +1 mês para cada parcela subsequente (ex: 02/10/2026 -> 02/11/2026 -> 02/12/2026...).\n"
            "        - Mantenha exatamente o mesmo valor por parcela, mesma categoria, mesma subcategoria e mesma conta_cartao.\n"
            "        - Ajuste a coluna 'parcela' para '3/6', '4/6', etc.\n"
            "     c) Se X for igual a N (ex: 3/3), é a última parcela — gere apenas a linha atual sem projeções futuras.\n\n"
            "7. Classifique cada item com a melhor categoria e subcategoria existente no meu Plutos:\n"
            "   [CATEGORIAS DE DESPESA]:\n"
            f"{cat_exp_block}\n\n"
            "   [CATEGORIAS DE RECEITA]:\n"
            f"{cat_inc_block}\n\n"
            "8. REGRA OBRIGATÓRIA PARA A COLUNA 'conta_cartao' (DISTINÇÃO CARTÃO VS CONTA):\n"
            f"   - Se o texto colado for FATURA DE CARTÃO DE CRÉDITO:\n"
            f"     * Preencha a coluna 'conta_cartao' OBRIGATORIAMENTE com o nome do respectivo cartão: [{card_str}].\n"
            f"     * NUNCA preencha com o nome da conta corrente quando o lançamento for de cartão de crédito!\n"
            f"   - Se o texto colado for EXTRATO BANCÁRIO (conta corrente, poupança, etc.):\n"
            f"     * Preencha a coluna 'conta_cartao' com o nome da respectiva conta bancária: [{acc_str}].\n\n"
            "9. Se for uma compra de terceiro / para outra pessoa, preencha na coluna 'observacao' no formato '[Terceiro: NomeDaPessoa]'.\n\n"
            "10. INSTRUÇÃO OBRIGATÓRIA DE GERAÇÃO DO ARQUIVO (.CSV PARA DOWNLOAD):\n"
            "   - IMPORTANTE: CRIE E DISPONIBILIZE O ARQUIVO 'fatura_plutos.csv' (ou 'extrato_plutos.csv') DIRETAMENTE PARA DOWNLOAD!\n"
            "   - Se você estiver no ChatGPT (com Python/Code Interpreter), Claude (com Artifacts) ou Gemini, execute o código ou crie o artefato para gerar o arquivo `.csv` (codificação UTF-8 com separador ';') e entregue o link/botão para eu baixar com um clique.\n"
            "   - Além de disponibilizar o arquivo para download, exiba também o conteúdo no bloco de código ```csv ... ``` para conferência imediata.\n"
            "   - Não inclua introduções longas, apenas o arquivo e o bloco CSV formatado.\n\n"
            "--- COLE SUA FATURA OU EXTRATO BRUTO ABAIXO DESTA LINHA ---"
        )

    def _copy_ai_prompt_to_clipboard(self) -> None:
        prompt_text = self.build_ai_import_prompt()
        app = QApplication.instance()
        if app is not None:
            clipboard = app.clipboard()
            clipboard.setText(prompt_text)
            self.lbl_import_status.setText(
                "✓ Prompt para IA copiado para a área de transferência! Cole no ChatGPT, Claude ou Gemini."
            )
            if self.isVisible():
                QMessageBox.information(
                    self,
                    "Prompt Copiado com Sucesso!",
                    "O Prompt customizado com suas categorias e contas foi copiado para a área de transferência!\n\n"
                    "Basta colar no ChatGPT, Claude ou Gemini junto com o texto da sua fatura.\n"
                    "A IA agora está instruída a gerar diretamente o arquivo .csv para você baixar e importar!",
                )

    def execute_import_from_path(self, file_path: str | Path) -> ImportReport:
        """Executa a importação programaticamente ou via botão da UI."""
        profile_id, _, _, _ = self.get_context()
        target_data = str(self.cb_imp_target.currentData() or "")
        acc_id: Optional[str] = None
        card_id: Optional[str] = None
        if target_data.startswith("ACC:"):
            acc_id = target_data.split(":", 1)[1]
        elif target_data.startswith("CARD:"):
            card_id = target_data.split(":", 1)[1]

        default_kind = str(self.cb_imp_kind.currentData() or "despesa")
        map_id = self.cb_imp_mapping.currentData()
        selected_map = next(
            (m for m in self._csv_mappings if m.id == map_id), None
        )

        report = self.io_orchestrator.import_file(
            file_path,
            profile_id=profile_id,
            target_account_id=acc_id,
            target_card_id=card_id,
            default_kind=default_kind,
            mapping=selected_map,
            skip_duplicates=self.chk_skip_dup.isChecked(),
        )
        extra_skip = (
            f" | {report.skipped_invoice_payments} pgto(s) fatura ignorado(s)"
            if getattr(report, "skipped_invoice_payments", 0) > 0
            else ""
        )
        self.lbl_import_status.setText(
            f"Importação concluída ({report.format_type.upper()}): "
            f"{report.imported_count} importados | "
            f"{report.skipped_duplicates} duplicados ignorados"
            f"{extra_skip} | "
            f"{report.error_count} erros (de {report.total_rows_read} lidos)."
        )
        if report.imported_count > 0:
            self.on_data_mutated()
        return report

    def _on_run_import_clicked(self) -> None:
        path_str = self.ed_import_path.text().strip()
        if not path_str:
            self._browse_import_file()
            path_str = self.ed_import_path.text().strip()
        if not path_str or not Path(path_str).exists():
            return
        self.execute_import_from_path(path_str)

    def execute_export_to_path(self, file_path: str | Path) -> ExportReport:
        """Executa a exportação programaticamente ou via botão da UI."""
        profile_id, month, year, _ = self.get_context()
        mode = str(self.cb_exp_mode.currentData() or "extrato")
        date_mode = self.db.settings.date_reference_mode
        report = self.io_orchestrator.export_month_data(
            file_path,
            year=year,
            month=month,
            profile_id=profile_id,
            date_mode=date_mode,
            export_mode=mode,
        )
        self.lbl_export_status.setText(
            f"Exportação concluída ({report.format_type.upper()}): "
            f"{report.exported_rows} registros gravados em '{Path(report.target_path).name}'."
        )
        return report

    def _on_run_export_clicked(self) -> None:
        path_str = self.ed_export_path.text().strip()
        if not path_str:
            self._browse_export_file()
            path_str = self.ed_export_path.text().strip()
        if not path_str:
            return
        self.execute_export_to_path(path_str)

    # ------------------------------------------------------------------ #
    # ABA 2: CONTROLE DE EMPRÉSTIMOS
    # ------------------------------------------------------------------ #
    def _build_loans_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(14)

        form_card = QFrame()
        form_card.setObjectName("CardSurface")
        f_lay = QVBoxLayout(form_card)
        f_lay.setContentsMargins(16, 14, 16, 14)
        f_lay.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        self.ed_loan_desc = QLineEdit()
        self.ed_loan_desc.setPlaceholderText("Descrição (Ex.: Empréstimo familiar)")
        self.ed_loan_person = QLineEdit()
        self.ed_loan_person.setPlaceholderText("Pessoa / Instituição")
        self.cb_loan_type = QComboBox()
        self.cb_loan_type.addItem("Emprestei (A Receber)", True)
        self.cb_loan_type.addItem("Tomei Emprestado (A Pagar)", False)
        self.sp_loan_val = QDoubleSpinBox()
        self.sp_loan_val.setRange(0.01, 999_999_999.99)
        self.sp_loan_val.setPrefix("R$ ")
        self.sp_loan_val.setValue(500.00)

        self.cb_loan_account = QComboBox()
        self.cb_loan_account.setToolTip(
            "Opcional: selecione uma conta bancária caso queira debitar/creditar o valor principal no saldo da conta"
        )
        self.cb_loan_account.addItem("Sem movimentar conta", None)

        btn_add = QPushButton("+ Registrar Empréstimo")
        btn_add.setObjectName("PrimaryButton")
        btn_add.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        btn_add.clicked.connect(self._add_loan)

        top_row.addWidget(self.ed_loan_desc, 2)
        top_row.addWidget(self.ed_loan_person, 1)
        top_row.addWidget(self.cb_loan_type, 1)
        top_row.addWidget(self.sp_loan_val, 1)
        top_row.addWidget(self.cb_loan_account, 1)
        top_row.addWidget(btn_add)
        f_lay.addLayout(top_row)
        lay.addWidget(form_card)

        table_card = QFrame()
        table_card.setObjectName("CardSurface")
        t_lay = QVBoxLayout(table_card)
        t_lay.setContentsMargins(16, 16, 16, 16)
        t_lay.setSpacing(12)

        self.tbl_loans = QTableWidget(0, 6)
        self.tbl_loans.setHorizontalHeaderLabels(
            [
                "Data",
                "Descrição",
                "Pessoa",
                "Natureza",
                "Valor Principal",
                "Saldo em Aberto",
            ]
        )
        self.tbl_loans.setShowGrid(False)
        self.tbl_loans.verticalHeader().setVisible(False)
        self.tbl_loans.verticalHeader().setDefaultSectionSize(38)
        hdr = self.tbl_loans.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.tbl_loans.setColumnWidth(3, 110)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_loans.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_loans.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t_lay.addWidget(self.tbl_loans, stretch=1)

        act_row = QHBoxLayout()
        act_row.setSpacing(8)
        btn_amort = QPushButton("Registrar Amortização")
        btn_amort.setObjectName("SecondaryButton")
        btn_amort.setIcon(get_line_icon("check_circle", size=14))
        btn_amort.clicked.connect(lambda _=False: self._amortize_selected_loan())

        btn_del = QPushButton("Excluir")
        btn_del.setObjectName("SecondaryButton")
        btn_del.setIcon(get_line_icon("trash", size=14))
        btn_del.clicked.connect(self._delete_selected_loan)

        act_row.addWidget(btn_amort)
        act_row.addWidget(btn_del)
        act_row.addStretch()
        t_lay.addLayout(act_row)

        lay.addWidget(table_card, stretch=1)
        return page

    # ------------------------------------------------------------------ #
    # ABA 3: NOTAS & LEMBRETES
    # ------------------------------------------------------------------ #
    def _build_notes_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(14)

        form_card = QFrame()
        form_card.setObjectName("CardSurface")
        f_lay = QVBoxLayout(form_card)
        f_lay.setContentsMargins(16, 14, 16, 14)
        f_lay.setSpacing(10)

        form_row = QHBoxLayout()
        form_row.setSpacing(8)
        self.ed_note_title = QLineEdit()
        self.ed_note_title.setPlaceholderText("Título da anotação financeira...")
        self.ed_note_body = QLineEdit()
        self.ed_note_body.setPlaceholderText("Conteúdo ou lembrete...")
        btn_add_note = QPushButton("+ Salvar Nota")
        btn_add_note.setObjectName("PrimaryButton")
        btn_add_note.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        btn_add_note.clicked.connect(self._add_note)
        form_row.addWidget(self.ed_note_title, 1)
        form_row.addWidget(self.ed_note_body, 2)
        form_row.addWidget(btn_add_note)
        f_lay.addLayout(form_row)
        lay.addWidget(form_card)

        table_card = QFrame()
        table_card.setObjectName("CardSurface")
        t_lay = QVBoxLayout(table_card)
        t_lay.setContentsMargins(16, 16, 16, 16)
        t_lay.setSpacing(12)

        self.tbl_notes = QTableWidget(0, 3)
        self.tbl_notes.setHorizontalHeaderLabels(
            ["Título", "Conteúdo", "Última Atualização"]
        )
        self.tbl_notes.setShowGrid(False)
        self.tbl_notes.verticalHeader().setVisible(False)
        self.tbl_notes.verticalHeader().setDefaultSectionSize(38)
        hdr = self.tbl_notes.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_notes.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tbl_notes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t_lay.addWidget(self.tbl_notes, stretch=1)

        btn_del_note = QPushButton("Excluir")
        btn_del_note.setObjectName("SecondaryButton")
        btn_del_note.setIcon(get_line_icon("trash", size=14))
        btn_del_note.clicked.connect(self._delete_selected_note)
        t_lay.addWidget(btn_del_note, alignment=Qt.AlignmentFlag.AlignLeft)

        lay.addWidget(table_card, stretch=1)
        return page

    # ------------------------------------------------------------------ #
    # ABA 4: SIMULADOR DE JUROS COMPOSTOS
    # ------------------------------------------------------------------ #
    def _build_calc_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(16)

        calc_card = QFrame()
        calc_card.setObjectName("CardSurface")
        c_lay = QVBoxLayout(calc_card)
        c_lay.setContentsMargins(20, 20, 20, 20)
        c_lay.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)

        self.sp_c_ini = QDoubleSpinBox()
        self.sp_c_ini.setRange(0.0, 999_999_999.99)
        self.sp_c_ini.setPrefix("R$ ")
        self.sp_c_ini.setValue(5000.00)
        form.addRow("Capital Inicial:", self.sp_c_ini)

        self.sp_c_mensal = QDoubleSpinBox()
        self.sp_c_mensal.setRange(0.0, 999_999_999.99)
        self.sp_c_mensal.setPrefix("R$ ")
        self.sp_c_mensal.setValue(800.00)
        form.addRow("Aporte Mensal:", self.sp_c_mensal)

        self.sp_c_taxa = QDoubleSpinBox()
        self.sp_c_taxa.setRange(0.01, 100.0)
        self.sp_c_taxa.setDecimals(2)
        self.sp_c_taxa.setSuffix(" % ao mês")
        self.sp_c_taxa.setValue(0.85)
        form.addRow("Taxa de Juros Mensal:", self.sp_c_taxa)

        self.sp_c_meses = QSpinBox()
        self.sp_c_meses.setRange(1, 600)
        self.sp_c_meses.setSuffix(" meses")
        self.sp_c_meses.setValue(36)
        form.addRow("Prazo em Meses:", self.sp_c_meses)

        c_lay.addLayout(form)

        btn_calc = QPushButton("Simular Evolução Patrimonial")
        btn_calc.setObjectName("PrimaryButton")
        btn_calc.clicked.connect(self._run_simulation)
        c_lay.addWidget(btn_calc, alignment=Qt.AlignmentFlag.AlignLeft)

        self.lbl_calc_result = QLabel()
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        self.lbl_calc_result.setFont(f)
        c_lay.addWidget(self.lbl_calc_result)

        lay.addWidget(calc_card)
        lay.addStretch()
        self._run_simulation()
        return page

    def _run_simulation(self) -> None:
        pv = float(self.sp_c_ini.value())
        pmt = float(self.sp_c_mensal.value())
        r = float(self.sp_c_taxa.value()) / 100.0
        n = int(self.sp_c_meses.value())

        saldo = pv
        for _ in range(n):
            saldo = saldo * (1.0 + r) + pmt
        investido = pv + pmt * n
        juros = saldo - investido
        self.lbl_calc_result.setText(
            f"Total Investido: {format_currency(investido)}   ·   "
            f"Rendimento em Juros: {format_currency(juros)}   ·   "
            f"Montante Final: {format_currency(saldo)}"
        )

    def refresh_data(self) -> None:
        profile_id, _, _, _ = self.get_context()
        self._reload_io_Selectors(profile_id)

        prev_loan_acc = self.cb_loan_account.currentData()
        self.cb_loan_account.blockSignals(True)
        self.cb_loan_account.clear()
        self.cb_loan_account.addItem("Sem movimentar conta", None)
        for acc in self.account_repo.list_accounts(profile_id):
            self.cb_loan_account.addItem(f"Conta: {acc.descricao}", acc.id)
        idx_acc = self.cb_loan_account.findData(prev_loan_acc)
        if idx_acc >= 0:
            self.cb_loan_account.setCurrentIndex(idx_acc)
        self.cb_loan_account.blockSignals(False)

        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        f_bold = QFont()
        f_bold.setBold(True)

        self._loans = self.analytics.list_loans(profile_id)
        self.tbl_loans.setRowCount(0)
        for idx, l in enumerate(self._loans):
            self.tbl_loans.insertRow(idx)

            it_dt = QTableWidgetItem(format_date_br(l.data_inicio.isoformat()))
            it_dt.setForeground(QColor(pal.text_secondary))
            self.tbl_loans.setItem(idx, 0, it_dt)

            it_desc = QTableWidgetItem(l.descricao)
            it_desc.setFont(f_bold)
            self.tbl_loans.setItem(idx, 1, it_desc)

            it_pes = QTableWidgetItem(l.pessoa)
            it_pes.setForeground(QColor(pal.text_secondary))
            self.tbl_loans.setItem(idx, 2, it_pes)

            st_lbl = "A Receber" if l.concedido else "A Pagar"
            st_var = "success" if l.concedido else "danger"
            badge = Badge(st_lbl, variant=st_var)
            c_w = QWidget()
            c_lay = QHBoxLayout(c_w)
            c_lay.setContentsMargins(0, 0, 0, 0)
            c_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lay.addWidget(badge)
            self.tbl_loans.setCellWidget(idx, 3, c_w)

            it_pri = QTableWidgetItem(format_currency(l.principal))
            it_pri.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.tbl_loans.setItem(idx, 4, it_pri)

            it_abe = QTableWidgetItem(format_currency(l.saldo_aberto))
            it_abe.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            it_abe.setFont(f_bold)
            it_abe.setForeground(
                QColor(INCOME_GREEN if l.concedido else EXPENSE_RED)
            )
            self.tbl_loans.setItem(idx, 5, it_abe)

        self._notes = self.analytics.list_notes(profile_id)
        self.tbl_notes.setRowCount(0)
        for idx, n in enumerate(self._notes):
            self.tbl_notes.insertRow(idx)

            it_t = QTableWidgetItem(n.titulo)
            it_t.setFont(f_bold)
            self.tbl_notes.setItem(idx, 0, it_t)

            self.tbl_notes.setItem(idx, 1, QTableWidgetItem(n.conteudo))

            it_up = QTableWidgetItem(n.atualizado_em)
            it_up.setForeground(QColor(pal.text_secondary))
            self.tbl_notes.setItem(idx, 2, it_up)

    def _add_loan(self) -> None:
        desc = self.ed_loan_desc.text().strip()
        if not desc:
            return
        profile_id, _, _, _ = self.get_context()
        selected_acc = self.cb_loan_account.currentData()
        self.analytics.create_loan(
            descricao=desc,
            pessoa=self.ed_loan_person.text().strip() or "Terceiro",
            principal=float(self.sp_loan_val.value()),
            concedido=bool(self.cb_loan_type.currentData()),
            profile_id=profile_id,
            id_conta=selected_acc,
            movimentar_conta=bool(selected_acc),
        )
        self.ed_loan_desc.clear()
        self.ed_loan_person.clear()
        self.on_data_mutated()
        self.refresh_data()

    def _amortize_selected_loan(
        self,
        valor: Optional[float] = None,
        id_conta: Optional[str] = None,
        movimentar_conta: bool = False,
        data_pagamento: Optional[date] = None,
    ) -> None:
        row = self.tbl_loans.currentRow()
        if not (0 <= row < len(self._loans)):
            return
        l = self._loans[row]
        if l.saldo_aberto <= 0:
            return
        profile_id, _, _, _ = self.get_context()

        if valor is None:
            if self.isVisible():
                dlg = LoanAmortizationDialog(
                    loan=l,
                    account_repo=self.account_repo,
                    profile_id=profile_id,
                    parent=self,
                )
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return
                valor = float(dlg.sp_valor.value())
                movimentar_conta = dlg.chk_movimentar_conta.isChecked()
                id_conta = dlg.cb_conta.currentData() if movimentar_conta else None
                qd = dlg.dt_pagamento.date()
                data_pagamento = date(qd.year(), qd.month(), qd.day())
            else:
                valor = l.saldo_aberto

        self.analytics.register_loan_payment(
            l.id,
            valor=float(valor),
            profile_id=profile_id,
            id_conta=id_conta,
            movimentar_conta=movimentar_conta,
            data_pagamento=data_pagamento,
        )
        self.on_data_mutated()
        self.refresh_data()

    def _delete_selected_loan(self) -> None:
        row = self.tbl_loans.currentRow()
        if not (0 <= row < len(self._loans)):
            return
        self.analytics.delete_loan(self._loans[row].id)
        self.on_data_mutated()
        self.refresh_data()

    def _add_note(self) -> None:
        title = self.ed_note_title.text().strip()
        if not title:
            return
        profile_id, _, _, _ = self.get_context()
        self.analytics.create_note(
            titulo=title,
            conteudo=self.ed_note_body.text().strip(),
            profile_id=profile_id,
        )
        self.ed_note_title.clear()
        self.ed_note_body.clear()
        self.on_data_mutated()
        self.refresh_data()

    def _delete_selected_note(self) -> None:
        row = self.tbl_notes.currentRow()
        if not (0 <= row < len(self._notes)):
            return
        self.analytics.delete_note(self._notes[row].id)
        self.on_data_mutated()
        self.refresh_data()
