"""
Testes automatizados da Etapa 5/6:
- Orçamentos Mensais (`BudgetService`): metas por categoria/subcategoria/tag, alertas,
  sobrescrita mensal (`orcamentos_mensal`) e compatibilidade com rateio multi-categoria (`SplitDTO`).
- Objetivos Financeiros (`GoalService`): criação de metas, aportes (`objetivos_dep`),
  cálculo de sugestão mensal e conclusão automática ao atingir 100%.
- Motor Analítico (`AnalyticsService`): agrupamentos por categoria/subcategoria/tag/conta/cartão,
  evolução mensal (fluxo de caixa), resumo diário de calendário, empréstimos (`emprestimos`) e notas (`notas`).
- Navegação nativa PySide6 por todas as 13 telas da `MainWindow` (incluindo gráficos `QtCharts`).
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config.app_settings import AppSettings
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.tag_repository import TagRepository
from app.domain.models import KIND_DESPESA, SplitDTO
from app.domain.services.analytics_service import AnalyticsService
from app.domain.services.budget_service import BudgetService
from app.domain.services.goal_service import GoalService
from app.domain.services.transaction_service import TransactionService
from app.ui.main_window import MainWindow


def _make_env(tmp_path: Path) -> ConnectionManager:
    db_file = tmp_path / "etapa5_test.sqlite"
    bkp_dir = tmp_path / "backups"
    cfg_file = tmp_path / "settings.json"
    settings = AppSettings.load(cfg_file)
    settings.active_db_path = str(db_file)
    settings.backup_dir = str(bkp_dir)
    settings.save()
    conn = ConnectionManager(settings=settings, auto_connect=False)
    conn.create_new_database(db_file, overwrite=True)
    return conn


def test_budgets_with_splits_alerts_and_monthly_overrides(tmp_path: Path) -> None:
    """Valida orçamentos por categoria e tag, rateio multi-categoria e sobrescrita mensal."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tag_repo = TagRepository(conn)
        tx = TransactionService(conn)
        b_srv = BudgetService(conn, tx)

        acc_id = acc_repo.create_account(descricao="Conta Corrente", saldo_inicial=5000.0)
        cats = cat_repo.list_categories("DESPESA", "1")
        cat_a, cat_b = cats[0], cats[1]
        sub_a = cat_a.subcategories[0].id if cat_a.subcategories else ""
        sub_b = cat_b.subcategories[0].id if cat_b.subcategories else ""
        tag = tag_repo.create_tag("LazerFds", "#AB47BC", "1")

        # Cria orçamento de R$ 500 para cat_a (alerta 80%) e R$ 300 para tag
        b_cat_id = b_srv.create_budget(
            meta=500.00, id_categoria=cat_a.id, perc_alerta=80.0
        )
        b_tag_id = b_srv.create_budget(
            meta=300.00, id_tag=tag.id, perc_alerta=80.0
        )

        # Despesa com rateio: R$ 420 na cat_a (84% -> Em Alerta) e R$ 180 na cat_b + tag LazerFds (R$ 600 -> Estourado)
        tx.create_expense(
            descricao="Compra Mista",
            valor=600.00,
            data_vencimento=date(2026, 10, 12),
            id_conta=acc_id,
            splits=[
                SplitDTO(cat_a.id, sub_a, 420.00),
                SplitDTO(cat_b.id, sub_b, 180.00),
            ],
            pago=True,
            tag_ids=[tag.id],
        )

        prog_oct = {
            b.id: b for b in b_srv.list_budgets_progress(2026, 10, profile_id="1")
        }
        assert prog_oct[b_cat_id].utilizado == 420.00
        assert prog_oct[b_cat_id].percentual == 84.0
        assert prog_oct[b_cat_id].status_label == "Em Alerta"

        assert prog_oct[b_tag_id].utilizado == 600.00
        assert prog_oct[b_tag_id].status_label == "Estourado"

        # Sobrescreve a meta apenas para Outubro/2026 para R$ 1000,00
        b_srv.update_budget(
            b_cat_id,
            meta=1000.00,
            year=2026,
            month=10,
            override_month_only=True,
        )
        prog_oct2 = {
            b.id: b for b in b_srv.list_budgets_progress(2026, 10, profile_id="1")
        }
        prog_nov = {
            b.id: b for b in b_srv.list_budgets_progress(2026, 11, profile_id="1")
        }
        assert prog_oct2[b_cat_id].meta_mes == 1000.00
        assert prog_oct2[b_cat_id].status_label == "Dentro da Meta"
        assert prog_nov[b_cat_id].meta_mes == 500.00
    finally:
        conn.close()


def test_goals_and_deposits_lifecycle(tmp_path: Path) -> None:
    """Valida criação de objetivos financeiros, aportes e conclusão automática."""
    conn = _make_env(tmp_path)
    try:
        g_srv = GoalService(conn)
        goal = g_srv.create_goal(
            descricao="Reserva de Emergência",
            meta=5000.00,
            saldo_inicial=1000.00,
            data_expectativa=date(2027, 10, 1),
            motivacao="Tranquilidade familiar",
        )
        assert goal.saldo_acumulado == 1000.00
        assert goal.percentual == 20.0
        assert not goal.realizado

        g_srv.add_deposit(goal.id, valor=1500.00, obs="1º Aporte")
        g_mid = g_srv.get_goal(goal.id)
        assert g_mid is not None
        assert g_mid.saldo_acumulado == 2500.00
        assert g_mid.percentual == 50.0
        assert not g_mid.realizado

        # Aporte final que atinge 100% da meta -> marca automaticamente como realizado
        g_srv.add_deposit(goal.id, valor=2500.00, obs="Quitação da meta")
        g_done = g_srv.get_goal(goal.id)
        assert g_done is not None
        assert g_done.saldo_acumulado == 5000.00
        assert g_done.percentual == 100.0
        assert g_done.realizado is True
    finally:
        conn.close()


def test_analytics_reports_calendar_loans_and_notes(tmp_path: Path) -> None:
    """Valida relatórios por categoria/fluxo mensal, calendário diário, empréstimos e notas."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        tx = TransactionService(conn)
        an = AnalyticsService(conn, tx)

        acc_id = acc_repo.create_account(descricao="Banco Inter", saldo_inicial=2000.0)
        tx.create_income(
            descricao="Consultoria",
            valor=4000.00,
            data=date(2026, 10, 5),
            id_conta=acc_id,
            recebido=True,
        )
        tx.create_expense(
            descricao="Aluguel Escritório",
            valor=1500.00,
            data_vencimento=date(2026, 10, 10),
            id_conta=acc_id,
            pago=True,
        )

        cat_rows = an.category_breakdown(2026, 10, kind=KIND_DESPESA)
        assert len(cat_rows) == 1
        assert cat_rows[0].total == 1500.00
        assert cat_rows[0].percentual == 100.0

        evo = an.monthly_evolution(2026, 10, months_count=6)
        assert len(evo) == 6
        assert evo[-1].receitas == 4000.00
        assert evo[-1].despesas == 1500.00
        assert evo[-1].resultado == 2500.00

        cal = an.daily_calendar_summary(2026, 10)
        assert 5 in cal and cal[5].receitas == 4000.00
        assert 10 in cal and cal[10].despesas == 1500.00

        # Empréstimos e amortizações
        loan = an.create_loan(
            descricao="Empréstimo João",
            pessoa="João Silva",
            principal=1200.00,
            concedido=True,
        )
        assert loan.saldo_aberto == 1200.00
        an.register_loan_payment(loan.id, valor=450.00)
        loans_after = an.list_loans()
        assert len(loans_after) == 1
        assert loans_after[0].saldo_aberto == 750.00

        # Notas financeiras
        note = an.create_note(
            titulo="Revisar investimentos CDB",
            conteudo="Verificar vencimento em dezembro",
        )
        assert note.titulo == "Revisar investimentos CDB"
        assert len(an.list_notes()) == 1
    finally:
        conn.close()


def test_all_13_main_window_views_render_cleanly(tmp_path: Path) -> None:
    """Navega por todas as 13 telas da `MainWindow` validando renderização sem erros."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    bkp = BackupSchedulerService(connection_manager=conn, settings=conn.settings)
    try:
        win = MainWindow(conn, bkp)
        for key, _label in MainWindow.NAV_ITEMS:
            win.navigate_to(key)
            assert win.current_nav_key == key
        win.close()
    finally:
        conn.close()


def test_third_party_credit_card_purchase_and_partial_loan_amortization(tmp_path: Path) -> None:
    """
    Valida Compra em Nome de Terceiro no cartão de crédito + geração automática de empréstimo
    + amortização parcial flexível creditando saldo na conta bancária sem inflar gráficos pessoais.
    """
    from app.domain.services.credit_card_service import CreditCardService

    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        tx = TransactionService(conn)
        card_srv = CreditCardService(conn, tx)
        an = AnalyticsService(conn, tx)

        acc_id = acc_repo.create_account(descricao="Nubank Conta", saldo_inicial=1000.0)
        card = card_srv.create_card(
            nome="Nubank Ultravioleta",
            limite=10000.0,
            dia_fecha=15,
            dia_venc=25,
            id_conta=acc_id,
        )
        card_id = card.id

        # 1. Despesa pessoal normal de R$ 250,00
        tx.create_expense(
            descricao="Supermercado Pessoal",
            valor=250.00,
            data_vencimento=date(2026, 10, 10),
            id_cartao=card_id,
            pago=False,
        )

        from app.domain.models import REC_PARCELADA

        # 2. Compra em nome de terceiro: Celular em 3x de R$ 200,00 (Total R$ 600,00) para "Carlos"
        tx.create_expense(
            descricao="Celular Samsung",
            valor=200.00,
            data_vencimento=date(2026, 10, 12),
            id_cartao=card_id,
            pago=False,
            recorrencia=REC_PARCELADA,
            num_parcelas=3,
            valor_por_parcela=True,
            terceiro_em_nome_de="Carlos",
            gerar_emprestimo_terceiro=True,
        )

        # A fatura do cartão de Outubro/2026 deve conter R$ 250 + R$ 200 = R$ 450,00 (bate 100% com o banco)
        inv = card_srv.get_invoice(card_id, 2026, 10)
        assert inv.total == 450.00

        # O resumo pessoal de Outubro/2026 deve considerar apenas os R$ 250,00 pessoais (e expor R$ 200,00 em terceiros_despesas)
        summary = tx.summarize(tx.list_occurrences(2026, 10))
        assert summary["despesas"] == 250.00
        assert summary["terceiros_despesas"] == 200.00

        # O relatório por categorias pessoais NÃO é inflado pelo gasto de Carlos
        personal_cats = an.category_breakdown(2026, 10, kind=KIND_DESPESA)
        assert sum(r.total for r in personal_cats) == 250.00

        # O relatório exclusivo de Terceiros exibe os R$ 200,00 do mês
        third_party_rows = an.third_party_breakdown(2026, 10)
        assert sum(r.total for r in third_party_rows) == 200.00

        # O empréstimo total de R$ 600,00 (3x R$ 200) foi criado automaticamente em Empréstimos
        loans = an.list_loans()
        assert len(loans) == 1
        assert loans[0].pessoa == "Carlos"
        assert loans[0].principal == 600.00
        assert loans[0].saldo_aberto == 600.00

        # 3. Carlos resolve adiantar/pagar R$ 300,00 neste mês via Pix para a conta Nubank Conta
        an.register_loan_payment(
            loan_id=loans[0].id,
            valor=300.00,
            id_conta=acc_id,
            movimentar_conta=True,
            data_pagamento=date(2026, 10, 15),
        )

        # O saldo devedor de Carlos cai de R$ 600,00 para R$ 300,00
        loans_after = an.list_loans()
        assert loans_after[0].amortizado == 300.00
        assert loans_after[0].saldo_aberto == 300.00

        # O saldo da conta bancária subiu de R$ 1.000,00 para R$ 1.300,00
        acc_dto = acc_repo.get_account_summary(acc_id, 10, 2026)
        assert acc_dto is not None
        assert acc_dto.saldo_atual == 1300.00

        # E o reembolso de R$ 300,00 NÃO inflou as receitas operacionais pessoais do mês
        summary_after = tx.summarize(tx.list_occurrences(2026, 10))
        assert summary_after["receitas_efetivadas"] == 0.0
    finally:
        conn.close()


def test_lote2_views_objetivos_relatorios_graficos_redesign(tmp_path: Path) -> None:
    """Valida o redesign visual e comportamento do Lote 2 (Objetivos, Relatórios e Gráficos)."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    bkp = BackupSchedulerService(connection_manager=conn, settings=conn.settings)
    try:
        win = MainWindow(conn, bkp)

        # 1. ObjetivosView
        win.navigate_to("objetivos")
        obj_v = win.objetivos_view
        assert obj_v.kpi_meta is not None
        assert obj_v.kpi_acum is not None
        assert obj_v.kpi_rest is not None
        assert obj_v.stack.currentWidget() == obj_v.empty_widget

        # 2. RelatoriosView
        win.navigate_to("relatorios")
        rel_v = win.relatorios_view
        assert rel_v.kpi_confirmed is not None
        assert rel_v.cb_report_type.count() >= 8
        # Alterna para fluxo de 6 meses
        idx_flow = rel_v.cb_report_type.findData("FLOW_6")
        rel_v.cb_report_type.setCurrentIndex(idx_flow)
        assert rel_v.table.columnCount() == 5

        # 3. GraficosView
        win.navigate_to("graficos")
        graf_v = win.graficos_view
        assert graf_v.cb_horizon.count() >= 2
        graf_v.refresh_data()
        assert graf_v.cv_exp_pie.chart() is not None
        assert graf_v.cv_bars.chart() is not None

        win.close()
    finally:
        conn.close()


def test_lote3_views_categorias_tags_calendario_ferramentas_redesign(tmp_path: Path) -> None:
    """Valida o redesign visual do Lote 3 (Categorias, Tags, Calendário e Ferramentas)."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    bkp = BackupSchedulerService(connection_manager=conn, settings=conn.settings)
    try:
        win = MainWindow(conn, bkp)

        # 1. CategoriasView
        win.navigate_to("categorias")
        cat_v = win.categorias_view
        assert cat_v.tabs.count() == 3
        assert cat_v.btn_new_cat is not None
        assert cat_v.btn_new_sub is not None

        # 2. TagsView
        win.navigate_to("tags")
        tag_v = win.tags_view
        assert tag_v.btn_new is not None
        assert tag_v.table.columnCount() == 4
        assert tag_v.stack.currentWidget() == tag_v.empty_widget

        # 3. CalendarioView
        win.navigate_to("calendario")
        cal_v = win.calendario_view
        assert cal_v.calendar is not None
        assert cal_v.table.columnCount() == 5

        # 4. FerramentasView
        win.navigate_to("ferramentas")
        ferr_v = win.ferramentas_view
        assert ferr_v.tabs.count() == 4
        assert ferr_v.btn_run_import is not None
        assert ferr_v.btn_run_export is not None
        assert ferr_v.tbl_loans.columnCount() == 6
        assert ferr_v.tbl_notes.columnCount() == 3

        win.close()
    finally:
        conn.close()



