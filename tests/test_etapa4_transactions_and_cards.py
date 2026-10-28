"""
Testes automatizados da Etapa 4/6:
- Motor de Transações (`TransactionService`): despesas, receitas e transferências
  (únicas, parceladas, fixas mensais com exceções em `*_fixas`, rateio multi-categoria
  em `despesas_cat_valor`, tags e exclusão/edição por escopo `'this'`, `'future'`, `'all'`).
- Os 4 Modos de Data de Referência (`vencimento`, `lancamento`, `lancamento_distribuir`, `efetivacao`).
- Cartões de Crédito e Faturas Mensais (`CreditCardService`): cálculo de fechamento/vencimento,
  limite comprometido/disponível, pagamento/reabertura de fatura, adiantamento e estorno.
- Integração na `MainWindow` nativa PySide6 (`TransacoesView` e `CartoesView`).
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
from app.domain.models import (
    KIND_DESPESA,
    KIND_RECEITA,
    KIND_TRANSFERENCIA,
    REC_FIXA_DESPESA,
    REC_FIXA_MENSAL,
    REC_PARCELADA,
    REC_UNICA,
    SplitDTO,
)
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService
from app.ui.main_window import MainWindow


def _make_env(tmp_path: Path) -> ConnectionManager:
    db_file = tmp_path / "etapa4_test.sqlite"
    bkp_dir = tmp_path / "backups"
    cfg_file = tmp_path / "settings.json"
    settings = AppSettings.load(cfg_file)
    settings.active_db_path = str(db_file)
    settings.backup_dir = str(bkp_dir)
    settings.save()
    conn = ConnectionManager(settings=settings, auto_connect=False)
    conn.create_new_database(db_file, overwrite=True)
    return conn


def test_installments_splits_and_date_reference_modes(tmp_path: Path) -> None:
    """Valida parcelamento com rateio multi-categoria (`despesas_cat_valor`) e os 4 modos de data."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tag_repo = TagRepository(conn)
        tx = TransactionService(conn)

        acc_id = acc_repo.create_account(descricao="Conta Principal", saldo_inicial=5000.0)
        cats = cat_repo.list_categories("DESPESA", "1")
        assert len(cats) >= 2
        cat_a, cat_b = cats[0], cats[1]
        sub_a = cat_a.subcategories[0].id if cat_a.subcategories else ""
        sub_b = cat_b.subcategories[0].id if cat_b.subcategories else ""

        tag = tag_repo.create_tag("Viagem", "#FF7043", "1")

        # Cria despesa parcelada em 3x de R$ 300,00 total (R$ 100,00 cada) com rateio 60%/40%
        # Compra realizada em 25/09/2026, 1º vencimento em 10/10/2026, paga em 12/10/2026
        ids = tx.create_expense(
            descricao="Compra Parcelada Rateada",
            valor=300.00,
            data_vencimento=date(2026, 10, 10),
            data_evento=date(2026, 9, 25),
            id_conta=acc_id,
            splits=[
                SplitDTO(cat_a.id, sub_a, 180.00),
                SplitDTO(cat_b.id, sub_b, 120.00),
            ],
            recorrencia=REC_PARCELADA,
            num_parcelas=3,
            valor_por_parcela=False,
            pago=True,
            data_efetivacao=date(2026, 11, 2),
            tag_ids=[tag.id],
        )
        assert len(ids) == 3

        # Modo Vencimento: parcela 1/3 aparece em Outubro/2026
        occs_oct_venc = tx.list_occurrences(2026, 10, mode="vencimento")
        assert len(occs_oct_venc) == 1
        occ1 = occs_oct_venc[0]
        assert occ1.total == 100.00
        assert occ1.parcela_label == "1/3"
        assert len(occ1.splits) == 2
        assert round(sum(s.valor for s in occ1.splits), 2) == 100.00
        assert occ1.tags and occ1.tags[0][1] == "Viagem"

        # Modo Lançamento (sem distribuir): todas as 3 parcelas têm data_evento = 25/09/2026
        occs_sep_lanc = tx.list_occurrences(2026, 9, mode="lancamento")
        assert len(occs_sep_lanc) == 3

        # Modo Lançamento Distribuir: distribui a partir de Setembro (Set, Out, Nov)
        occs_sep_dist = tx.list_occurrences(2026, 9, mode="lancamento_distribuir")
        occs_oct_dist = tx.list_occurrences(2026, 10, mode="lancamento_distribuir")
        occs_nov_dist = tx.list_occurrences(2026, 11, mode="lancamento_distribuir")
        assert len(occs_sep_dist) == 1
        assert len(occs_oct_dist) == 1
        assert len(occs_nov_dist) == 1

        # Modo Efetivação: como a 1ª parcela foi paga em 02/11/2026, ela aparece em Novembro/2026
        # junto com a 2ª parcela (que vence em 10/11/2026 e ainda está pendente)
        occs_nov_efet = tx.list_occurrences(2026, 11, mode="efetivacao")
        assert len(occs_nov_efet) == 2
    finally:
        conn.close()


def test_fixed_recurrence_overrides_and_scoped_deletion(tmp_path: Path) -> None:
    """Valida recorrências fixas, exceções mensais (`*_fixas`) e exclusão por escopo."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        tx = TransactionService(conn)
        acc1_id = acc_repo.create_account(descricao="Conta A", saldo_inicial=1000.0)
        acc2_id = acc_repo.create_account(descricao="Conta B", saldo_inicial=500.0)

        # Receita fixa mensal iniciando em Jan/2026
        tx.create_income(
            descricao="Salário Mensal",
            valor=5000.00,
            data=date(2026, 1, 5),
            id_conta=acc1_id,
            recorrencia=REC_FIXA_MENSAL,
            recebido=False,
        )
        # Transferência fixa mensal iniciando em Jan/2026
        tx.create_transfer(
            descricao="Aporte Poupança",
            valor=800.00,
            data=date(2026, 1, 15),
            id_conta_origem=acc1_id,
            id_conta_destino=acc2_id,
            recorrencia=REC_FIXA_MENSAL,
            efetivada=False,
        )

        # Verifica Março/2026
        mar_occs = tx.list_occurrences(2026, 3)
        assert len(mar_occs) == 2
        sal_mar = next(o for o in mar_occs if o.kind == KIND_RECEITA)

        # Altera valor e confirma somente Março/2026 (scope='this')
        tx.update_occurrence(
            sal_mar, scope="this", valor=5500.00, efetivada=True
        )
        mar_after = tx.get_occurrence(KIND_RECEITA, sal_mar.id, 2026, 3)
        apr_after = tx.get_occurrence(KIND_RECEITA, sal_mar.id, 2026, 4)
        assert mar_after is not None and mar_after.total == 5500.00 and mar_after.efetivada
        assert apr_after is not None and apr_after.total == 5000.00 and not apr_after.efetivada

        # Exclui somente Abril/2026 (scope='this')
        tx.delete_occurrence(apr_after, scope="this")
        assert tx.get_occurrence(KIND_RECEITA, sal_mar.id, 2026, 4) is None
        may_occ = tx.get_occurrence(KIND_RECEITA, sal_mar.id, 2026, 5)
        assert may_occ is not None

        # Encerra a série a partir de Maio/2026 (scope='future')
        tx.delete_occurrence(may_occ, scope="future")
        assert tx.get_occurrence(KIND_RECEITA, sal_mar.id, 2026, 3) is not None
        assert tx.get_occurrence(KIND_RECEITA, sal_mar.id, 2026, 5) is None
        assert tx.get_occurrence(KIND_RECEITA, sal_mar.id, 2026, 6) is None
    finally:
        conn.close()


def test_credit_card_invoices_limits_advances_and_refunds(tmp_path: Path) -> None:
    """Valida ciclo de fatura, compras antes/após fechamento, pagamento, adiantamento e estorno."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        tx = TransactionService(conn)
        cc_service = CreditCardService(conn, tx)

        acc_id = acc_repo.create_account(descricao="Nubank Conta", saldo_inicial=10000.0)
        card = cc_service.create_card(
            nome="Nubank Ultravioleta",
            limite=8000.00,
            dia_fecha=3,
            dia_venc=10,
            id_conta=acc_id,
            brand_key="master",
            padrao=True,
        )

        # Compra 1: 01/10/2026 (antes do fechamento 03/10) -> vence em 10/10/2026
        tx.create_expense(
            descricao="Restaurante",
            valor=200.00,
            data_vencimento=date(2026, 10, 1),
            data_evento=date(2026, 10, 1),
            id_cartao=card.id,
        )

        # Compra 2: 05/10/2026 (após o fechamento 03/10) parcelada em 2x de R$ 500 -> vence em 10/11 e 10/12
        tx.create_expense(
            descricao="Notebook Acessório",
            valor=1000.00,
            data_vencimento=date(2026, 10, 5),
            data_evento=date(2026, 10, 5),
            id_cartao=card.id,
            recorrencia=REC_PARCELADA,
            num_parcelas=2,
        )

        inv_oct = cc_service.get_invoice(card.id, 2026, 10)
        inv_nov = cc_service.get_invoice(card.id, 2026, 11)
        inv_dec = cc_service.get_invoice(card.id, 2026, 12)

        assert inv_oct.total == 200.00
        assert inv_nov.total == 500.00
        assert inv_dec.total == 500.00
        assert inv_oct.usado == 1200.00
        assert inv_oct.disponivel == 6800.00

        # Paga fatura de Outubro/2026
        paid_cnt = cc_service.pay_invoice(card.id, 2026, 10)
        assert paid_cnt == 1
        inv_oct_paid = cc_service.get_invoice(card.id, 2026, 10)
        assert inv_oct_paid.paga is True
        assert inv_oct_paid.status == "Paga"
        assert inv_oct_paid.usado == 1000.00  # libera R$ 200 de limite

        # Verifica que o pagamento da fatura gerou lançamento em Transações e debitou a conta corrente
        acc_summary_paid = acc_repo.get_account_summary(acc_id, 10, 2026)
        assert acc_summary_paid.saldo_atual == 9800.00
        oct_occs = tx.list_occurrences(2026, 10)
        pay_occ = next(
            (o for o in oct_occs if not o.is_card and "Pagamento Fatura Nubank Ultravioleta - 10/2026" in o.descricao),
            None,
        )
        assert pay_occ is not None
        assert pay_occ.total == 200.00
        assert pay_occ.efetivada is True

        # Reabre e paga novamente para validar estorno do débito em conta ao reabrir
        cc_service.reopen_invoice(card.id, 2026, 10)
        acc_summary_reopened = acc_repo.get_account_summary(acc_id, 10, 2026)
        assert acc_summary_reopened.saldo_atual == 10000.00
        cc_service.pay_invoice(card.id, 2026, 10)
        assert acc_repo.get_account_summary(acc_id, 10, 2026).saldo_atual == 9800.00

        # Adiantamento de R$ 150 na fatura de Novembro/2026
        cc_service.add_invoice_advance(
            card.id, 2026, 11, valor=150.00, id_conta=acc_id
        )
        inv_nov_after_adv = cc_service.get_invoice(card.id, 2026, 11)
        assert inv_nov_after_adv.total == 350.00

        # Estorno da compra de R$ 500 em Dezembro/2026
        occ_dec = inv_dec.items[0]
        cc_service.refund_card_expense(occ_dec)
        inv_dec_after_ref = cc_service.get_invoice(card.id, 2026, 12)
        assert inv_dec_after_ref.total == 0.00

        # Ajuste pontual da fatura do mês (cartoes_credito_mes)
        inv_nov_custom = cc_service.update_invoice_month(
            card.id, 2026, 11, dia_fecha=20, dia_venc=28, limite=10000.00
        )
        assert inv_nov_custom.card.dia_fecha == 20
        assert inv_nov_custom.card.dia_venc == 28
        assert inv_nov_custom.limite == 10000.00

        # Restauração do ciclo padrão
        inv_nov_reset = cc_service.reset_invoice_month(card.id, 2026, 11)
        assert inv_nov_reset.card.dia_fecha == card.dia_fecha
        assert inv_nov_reset.card.dia_venc == card.dia_venc
        assert inv_nov_reset.limite == card.limite
    finally:
        conn.close()


def test_main_window_transacoes_and_cartoes_views(tmp_path: Path) -> None:
    """Valida a renderização nativa e navegação para `TransacoesView` e `CartoesView`."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    bkp = BackupSchedulerService(connection_manager=conn, settings=conn.settings)
    try:
        win = MainWindow(conn, bkp)
        win.navigate_to("transacoes")
        assert win.current_nav_key == "transacoes"
        win.navigate_to("cartoes")
        assert win.current_nav_key == "cartoes"
        win.close()
    finally:
        conn.close()


def test_open_invoice_and_realign_card_expenses(tmp_path: Path) -> None:
    """Fatura vigente (aberta) por mês de competência e realinhamento das compras ao ciclo correto."""
    conn = _make_env(tmp_path)
    try:
        tx = TransactionService(conn)
        cc = CreditCardService(conn, tx)
        # Cartão configurado com fechamento dia 30 e vencimento dia 10 (mês seguinte).
        card = cc.create_card(
            nome="Nubank", limite=1750.0, dia_fecha=30, dia_venc=10, brand_key="master"
        )
        hoje = date(2026, 10, 18)

        # Compras feitas em Outubro caem na Fatura de Outubro (10/2026), que vence em 10/11/2026.
        tx.create_expense(
            descricao="Compra no início do mês",
            valor=100.0,
            data_vencimento=date(2026, 11, 10),
            data_evento=date(2026, 10, 2),
            id_cartao=card.id,
        )
        tx.create_expense(
            descricao="Compra de 05/10",
            valor=50.0,
            data_vencimento=date(2026, 11, 10),
            data_evento=date(2026, 10, 5),
            id_cartao=card.id,
        )

        aberta = cc.get_open_invoice(card.id, hoje)
        assert (aberta.ano, aberta.mes) == (2026, 10)
        assert aberta.status == "Aberta"
        assert aberta.total == 150.0
        assert aberta.data_fechamento == date(2026, 10, 30)
        assert aberta.data_vencimento == date(2026, 11, 10)
        assert cc.preview_realign_card_expenses(card.id) == []

        # Alteração de vencimento: de dia 10 para dia 15 -> realinha despesas pendentes.
        cc.update_card(
            card.id, nome="Nubank", limite=1750.0, dia_fecha=30, dia_venc=15,
            id_conta=None, color_hex=card.color_hex, brand_key="master",
        )
        aberta2 = cc.get_invoice(card.id, 2026, 10)
        assert aberta2.data_vencimento == date(2026, 11, 15)
        assert aberta2.total == 150.0
    finally:
        conn.close()


def test_cartoes_view_open_invoice_navigation_and_realign(tmp_path: Path) -> None:
    """Valida a navegação entre faturas (estilo Nubank) e exibição do mês de competência na CartoesView."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    bkp = BackupSchedulerService(connection_manager=conn, settings=conn.settings)
    try:
        tx = TransactionService(conn)
        cc = CreditCardService(conn, tx)
        card = cc.create_card(
            nome="Nubank Roxo", limite=2000.0, dia_fecha=30, dia_venc=10, brand_key="master"
        )
        tx.create_expense(
            descricao="Compra aberta",
            valor=120.0,
            data_vencimento=date(2026, 11, 10),
            data_evento=date(2026, 10, 15),
            id_cartao=card.id,
        )

        win = MainWindow(conn, bkp)
        win.navigate_to("cartoes")
        cview = win.cartoes_view
        cview.refresh_data()

        # Em Outubro/2026, deve focar na fatura aberta de Outubro (2026/10)
        assert cview._selected_invoice is not None
        assert cview._selected_invoice.card.id == card.id
        assert cview._selected_invoice.ano == 2026
        assert cview._selected_invoice.mes == 10
        assert cview._selected_invoice.total == 120.0

        # Navegador de faturas presente e com itens
        assert cview.cb_invoice_month.count() > 0
        cur_text = cview.cb_invoice_month.currentText()
        assert "10/2026" in cur_text
        assert "Aberta" in cur_text

        # Navegação para fatura anterior
        cview._on_prev_invoice()
        assert cview._selected_invoice.mes == 9

        # Botão de retorno direto à fatura aberta
        cview._on_jump_open_invoice()
        assert cview._selected_invoice.mes == 10

        # Realinhamento de lançamentos sem pendências
        assert cc.preview_realign_card_expenses(card.id) == []
        win.close()
    finally:
        conn.close()


def test_convert_expense_to_income_and_back_single(tmp_path: Path) -> None:
    """Valida conversão atômica de Despesa Única -> Receita Única e retorno -> Despesa com rateio e tags."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tag_repo = TagRepository(conn)
        tx = TransactionService(conn)

        acc_id = acc_repo.create_account(descricao="Banco Digital", saldo_inicial=2000.0)
        desp_cats = cat_repo.list_categories("DESPESA", "1")
        rec_cats = cat_repo.list_categories("RECEITA", "1")
        assert desp_cats and rec_cats

        tag = tag_repo.create_tag("Importante", "#2196F3", "1")

        # 1. Cria despesa inicial
        ids = tx.create_expense(
            descricao="Compra no mercado",
            valor=85.50,
            data_vencimento=date(2026, 10, 15),
            id_conta=acc_id,
            id_categoria=desp_cats[0].id,
            id_subcategoria=desp_cats[0].subcategories[0].id if desp_cats[0].subcategories else None,
            pago=True,
            tag_ids=[tag.id],
        )
        assert len(ids) == 1
        desp_id = ids[0]

        # Verifica despesa na lista
        occs = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_DESPESA])
        assert len(occs) == 1
        occ = occs[0]
        assert occ.kind == KIND_DESPESA
        assert occ.total == 85.50

        # 2. Converte DESPESA -> RECEITA
        tx.update_occurrence(
            occ,
            new_kind=KIND_RECEITA,
            descricao="Reembolso de mercado",
            valor=90.00,
            id_conta=acc_id,
            id_categoria=rec_cats[0].id,
            id_subcategoria=rec_cats[0].subcategories[0].id if rec_cats[0].subcategories else None,
            efetivada=True,
        )

        # Não deve haver mais despesas em Outubro
        occs_desp = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_DESPESA])
        assert len(occs_desp) == 0

        # Deve haver a receita convertida em Outubro
        occs_rec = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_RECEITA])
        assert len(occs_rec) == 1
        rec_occ = occs_rec[0]
        assert rec_occ.kind == KIND_RECEITA
        assert rec_occ.descricao == "Reembolso de mercado"
        assert rec_occ.total == 90.00
        assert rec_occ.efetivada is True

        # Verifica tag migrada para RECEITA
        tag_types = [
            r[0]
            for r in conn.execute_query(
                "SELECT tipo_transacao FROM tags_transacoes WHERE id_transacao = ?",
                (desp_id,),
            )
        ]
        assert "RECEITA" in tag_types

        # 3. Converte RECEITA -> DESPESA de volta
        tx.update_occurrence(
            rec_occ,
            new_kind=KIND_DESPESA,
            descricao="Compra estornada restaurada",
            valor=88.00,
            id_conta=acc_id,
            id_categoria=desp_cats[0].id,
            id_subcategoria=desp_cats[0].subcategories[0].id if desp_cats[0].subcategories else None,
            efetivada=False,
        )

        # Não há mais receitas
        assert len(tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_RECEITA])) == 0

        # Voltou a ser despesa
        occs_desp_final = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_DESPESA])
        assert len(occs_desp_final) == 1
        final_occ = occs_desp_final[0]
        assert final_occ.kind == KIND_DESPESA
        assert final_occ.descricao == "Compra estornada restaurada"
        assert final_occ.total == 88.00
        assert final_occ.efetivada is False

        # Verifica rateio em despesas_cat_valor presente
        splits = conn.execute_query(
            "SELECT valor FROM despesas_cat_valor WHERE id_despesa = ?", (desp_id,)
        )
        assert len(splits) == 1
        assert float(splits[0]["valor"]) == 88.00

        # Tag de volta para DESPESA
        tag_types_final = [
            r[0]
            for r in conn.execute_query(
                "SELECT tipo_transacao FROM tags_transacoes WHERE id_transacao = ?",
                (desp_id,),
            )
        ]
        assert "DESPESA" in tag_types_final
    finally:
        conn.close()


def test_convert_fixed_expense_scope_this_and_all(tmp_path: Path) -> None:
    """Valida conversão de despesa fixa por escopo: 'this' (exceção do mês) e 'all' (toda a série)."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tx = TransactionService(conn)

        acc_id = acc_repo.create_account(descricao="Conta Teste", saldo_inicial=3000.0)
        desp_cats = cat_repo.list_categories("DESPESA", "1")
        rec_cats = cat_repo.list_categories("RECEITA", "1")

        # Cria despesa fixa mensal de R$ 200,00 iniciando em Setembro/2026
        ids = tx.create_expense(
            descricao="Assinatura Recorrente",
            valor=200.0,
            data_vencimento=date(2026, 9, 10),
            id_conta=acc_id,
            id_categoria=desp_cats[0].id,
            recorrencia=REC_FIXA_DESPESA,
            pago=False,
        )
        fix_id = ids[0]

        # Em Outubro/2026: converte apenas ESTE mês ('this') para Receita
        occ_oct = tx.get_occurrence(KIND_DESPESA, fix_id, 2026, 10)
        assert occ_oct is not None

        tx.update_occurrence(
            occ_oct,
            new_kind=KIND_RECEITA,
            scope="this",
            descricao="Reembolso de Assinatura (Mês Específico)",
            valor=200.0,
            id_conta=acc_id,
            id_categoria=rec_cats[0].id,
            efetivada=True,
        )

        # Em Outubro/2026: despesa fixa não deve aparecer (foi excluída no mês), mas receita avulsa sim
        assert len(tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_DESPESA])) == 0
        recs_oct = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_RECEITA])
        assert len(recs_oct) == 1
        assert recs_oct[0].descricao == "Reembolso de Assinatura (Mês Específico)"

        # Em Novembro/2026: a despesa fixa continua existindo normalmente!
        occ_nov = tx.get_occurrence(KIND_DESPESA, fix_id, 2026, 11)
        assert occ_nov is not None
        assert occ_nov.total == 200.0

        # Agora, em Novembro/2026: converte TODA a série ('all') para Receita
        tx.update_occurrence(
            occ_nov,
            new_kind=KIND_RECEITA,
            scope="all",
            descricao="Renda Fixa Mensal Convertida",
            valor=250.0,
            id_conta=acc_id,
            id_categoria=rec_cats[0].id,
        )

        # Em Novembro e Dezembro, a despesa fixa desapareceu e agora é uma receita fixa
        assert len(tx.list_occurrences(2026, 11, mode="vencimento", kinds=[KIND_DESPESA])) == 0
        assert len(tx.list_occurrences(2026, 12, mode="vencimento", kinds=[KIND_DESPESA])) == 0

        recs_nov = tx.list_occurrences(2026, 11, mode="vencimento", kinds=[KIND_RECEITA])
        assert len(recs_nov) == 1
        assert recs_nov[0].is_fixed is True
        assert recs_nov[0].total == 250.0
        assert recs_nov[0].descricao == "Renda Fixa Mensal Convertida"
    finally:
        conn.close()


def test_convert_installments_expense_to_income_all(tmp_path: Path) -> None:
    """Valida conversão de série parcelada de Despesa para Receita (scope='all')."""
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tx = TransactionService(conn)

        acc_id = acc_repo.create_account(descricao="Banco Parcelas", saldo_inicial=4000.0)
        desp_cats = cat_repo.list_categories("DESPESA", "1")
        rec_cats = cat_repo.list_categories("RECEITA", "1")

        # Cria despesa parcelada em 3x de R$ 100,00 (Out, Nov, Dez de 2026)
        ids = tx.create_expense(
            descricao="Curso Parcelado",
            valor=300.0,
            data_vencimento=date(2026, 10, 10),
            id_conta=acc_id,
            id_categoria=desp_cats[0].id,
            recorrencia=REC_PARCELADA,
            num_parcelas=3,
        )
        assert len(ids) == 3

        occ_oct = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_DESPESA])[0]

        # Converte toda a série (scope='all') para Receita
        tx.update_occurrence(
            occ_oct,
            new_kind=KIND_RECEITA,
            scope="all",
            descricao="Bolsa de Estudos",
            id_conta=acc_id,
            id_categoria=rec_cats[0].id,
        )

        # Não deve haver despesas nos 3 meses
        for m in (10, 11, 12):
            assert len(tx.list_occurrences(2026, m, mode="vencimento", kinds=[KIND_DESPESA])) == 0

        # Deve haver 3 receitas parceladas correspondentes
        rec_occs_oct = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_RECEITA])
        assert len(rec_occs_oct) == 1
        assert rec_occs_oct[0].parcela_label == "1/3"
        assert rec_occs_oct[0].total == 100.0
        assert rec_occs_oct[0].descricao == "Bolsa de Estudos"

        rec_occs_nov = tx.list_occurrences(2026, 11, mode="vencimento", kinds=[KIND_RECEITA])
        assert len(rec_occs_nov) == 1
        assert rec_occs_nov[0].parcela_label == "2/3"

        rec_occs_dec = tx.list_occurrences(2026, 12, mode="vencimento", kinds=[KIND_RECEITA])
        assert len(rec_occs_dec) == 1
        assert rec_occs_dec[0].parcela_label == "3/3"
    finally:
        conn.close()


def test_dialog_kind_toggling_behavior(tmp_path: Path) -> None:
    """Valida a alternância dinâmica de Tipo (Despesa <-> Receita) nas caixas de diálogo."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    try:
        from app.ui.views.transacoes_view import ExpenseDialog, IncomeDialog

        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tx = TransactionService(conn)

        acc_id = acc_repo.create_account(descricao="Banco UI", saldo_inicial=1000.0)
        desp_cats = cat_repo.list_categories("DESPESA", "1")
        rec_cats = cat_repo.list_categories("RECEITA", "1")

        ids = tx.create_expense(
            descricao="Supermercado",
            valor=50.0,
            data_vencimento=date(2026, 10, 10),
            id_conta=acc_id,
            id_categoria=desp_cats[0].id,
        )
        occ = tx.list_occurrences(2026, 10, mode="vencimento")[0]

        # 1. Dialog de Despesa com ocorrência
        dlg = ExpenseDialog(
            conn,
            profile_id="1",
            default_date=occ.data_vencimento,
            occurrence=occ,
        )
        assert dlg.selected_kind() == KIND_DESPESA
        assert "Editar Despesa" in dlg.windowTitle()
        assert dlg.btn_save.text() == "Salvar Despesa"

        # Alterna para Receita
        dlg.cb_kind.setCurrentIndex(1)
        assert dlg.selected_kind() == KIND_RECEITA
        assert "Editar Receita" in dlg.windowTitle()
        assert dlg.btn_save.text() == "Salvar Receita"
        assert dlg.chk_pago.text() == "Já foi recebida / efetivada"
        assert dlg.rb_cartao.isEnabled() is False

        # Alterna de volta para Despesa
        dlg.cb_kind.setCurrentIndex(0)
        assert dlg.selected_kind() == KIND_DESPESA
        assert "Editar Despesa" in dlg.windowTitle()
        assert dlg.btn_save.text() == "Salvar Despesa"
        assert dlg.chk_pago.text() == "Já está paga / efetivada"
        assert dlg.rb_cartao.isEnabled() is True
        dlg.close()

        # 2. Dialog de Receita
        rec_ids = tx.create_income(
            descricao="Salário",
            valor=3000.0,
            data=date(2026, 10, 5),
            id_conta=acc_id,
            id_categoria=rec_cats[0].id,
        )
        rec_occ = tx.list_occurrences(2026, 10, mode="vencimento", kinds=[KIND_RECEITA])[0]

        dlg_r = IncomeDialog(
            conn,
            profile_id="1",
            default_date=rec_occ.data_vencimento,
            occurrence=rec_occ,
        )
        assert dlg_r.selected_kind() == KIND_RECEITA
        assert "Editar Receita" in dlg_r.windowTitle()
        assert dlg_r.btn_save.text() == "Salvar Receita"

        # Alterna para Despesa
        dlg_r.cb_kind.setCurrentIndex(1)
        assert dlg_r.selected_kind() == KIND_DESPESA
        assert "Editar Despesa" in dlg_r.windowTitle()
        assert dlg_r.btn_save.text() == "Salvar Despesa"
        assert dlg_r.chk_recebido.text() == "Já está paga / efetivada"
        dlg_r.close()
    finally:
        conn.close()


def test_delete_card_expense_and_wipe_card_expenses(tmp_path: Path) -> None:
    """Valida a exclusão individual de despesas do cartão e a formatação total do cartão."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        tx = TransactionService(conn)
        cc = CreditCardService(conn, tx)

        acc_id = acc_repo.create_account(descricao="Conta Teste", saldo_inicial=5000.0)
        card = cc.create_card(
            nome="Nubank Gold",
            limite=3000.0,
            dia_fecha=2,
            dia_venc=9,
            id_conta=acc_id,
        )

        # Cria 3 despesas no cartão
        tx.create_expense(
            descricao="Compra 1",
            valor=100.0,
            data_vencimento=date(2026, 11, 9),
            data_evento=date(2026, 10, 5),
            id_cartao=card.id,
        )
        tx.create_expense(
            descricao="Compra 2",
            valor=250.0,
            data_vencimento=date(2026, 11, 9),
            data_evento=date(2026, 10, 10),
            id_cartao=card.id,
        )
        tx.create_expense(
            descricao="Compra 3",
            valor=150.0,
            data_vencimento=date(2026, 11, 9),
            data_evento=date(2026, 10, 15),
            id_cartao=card.id,
        )

        inv = cc.get_invoice(card.id, 2026, 11)
        assert len(inv.items) == 3
        assert inv.total == 500.0

        # 1. Exclui a Compra 1 individualmente via tx.delete_occurrence
        occ_1 = [o for o in inv.items if o.descricao == "Compra 1"][0]
        tx.delete_occurrence(occ_1, scope="this")

        inv_after_del = cc.get_invoice(card.id, 2026, 11)
        assert len(inv_after_del.items) == 2
        assert inv_after_del.total == 400.0

        # 2. Formata o cartão (wipe_card_expenses)
        deleted_count = cc.wipe_card_expenses(card.id)
        assert deleted_count == 2

        inv_after_wipe = cc.get_invoice(card.id, 2026, 11)
        assert len(inv_after_wipe.items) == 0
        assert inv_after_wipe.total == 0.0
        assert inv_after_wipe.usado == 0.0
    finally:
        conn.close()


def test_card_brands_and_icons(tmp_path: Path) -> None:
    """Valida o mapeamento de ícones de bandeiras de cartão de crédito e heurísticas de nome."""
    app = QApplication.instance() or QApplication([])
    from app.config.app_settings import CREDIT_CARD_ICONS_DIR
    from app.domain.services.credit_card_service import (
        CARD_BRANDS,
        CreditCardService,
        brand_icon_filename,
    )
    from app.ui.bank_icons import get_card_brand_pixmap

    # 1. Verifica se todos os arquivos referenciados em CARD_BRANDS existem no disco
    for b_key, b_label, fname in CARD_BRANDS:
        p = CREDIT_CARD_ICONS_DIR / fname
        assert p.exists(), f"Ícone da bandeira {b_label} ({fname}) não encontrado em {CREDIT_CARD_ICONS_DIR}"
        pix = get_card_brand_pixmap(fname, size=24)
        assert not pix.isNull(), f"Pixmap nulo para bandeira {b_key} ({fname})"

    # 2. Testa brand_icon_filename
    assert brand_icon_filename("master") == "ic_master_card.png"
    assert brand_icon_filename("visa") == "ic_visa.png"
    assert brand_icon_filename("elo") == "ic_card_elo.png"
    assert brand_icon_filename("amex") == "ic_credit_amex.png"
    assert brand_icon_filename("dinners") == "ic_card_diners_club.png"
    assert brand_icon_filename("other") == "ic_credit_card.png"
    assert brand_icon_filename("desconhecida") == "ic_credit_card.png"

    # 3. Testa detecção heurística pelo nome do cartão
    conn = _make_env(tmp_path)
    try:
        cc = CreditCardService(conn)
        c_nu = cc.create_card(nome="Nubank Roxinho", limite=5000.0, dia_fecha=1, dia_venc=10, brand_key="")
        assert c_nu.brand_key == "master"

        c_visa = cc.create_card(nome="Meu Cartão Visa Infinite", limite=10000.0, dia_fecha=5, dia_venc=15, brand_key="")
        assert c_visa.brand_key == "visa"

        c_elo = cc.create_card(nome="Bradesco Elo Nanquim", limite=8000.0, dia_fecha=2, dia_venc=12, brand_key="")
        assert c_elo.brand_key == "elo"

        c_amex = cc.create_card(nome="The Platinum Card Amex", limite=20000.0, dia_fecha=10, dia_venc=20, brand_key="")
        assert c_amex.brand_key == "amex"
    finally:
        conn.close()


def test_edit_card_expense_single_and_series(tmp_path: Path) -> None:
    """Valida a edição completa de compras no cartão (parceladas e à vista) na fatura e no ExpenseDialog."""
    app = QApplication.instance() or QApplication([])
    from app.ui.views.transacoes_view import ExpenseDialog

    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tag_repo = TagRepository(conn)
        tx = TransactionService(conn)
        cc = CreditCardService(conn, tx)

        acc_id = acc_repo.create_account(descricao="Conta Principal", saldo_inicial=2000.0)
        card = cc.create_card(
            nome="Mercado Livre Visa",
            limite=4000.0,
            dia_fecha=4,
            dia_venc=12,
            id_conta=acc_id,
            brand_key="visa",
        )
        cats = cat_repo.list_categories("DESPESA", "1")
        tag_id = tag_repo.create_tag(nome="Moto", color_hex="#FF5722", profile_id="1").id

        # 1. Cria compra parcelada em 4x de R$ 47,50 (data_evento 20/03/2026 -> 1ª fatura 12/04/2026)
        tx.create_expense(
            descricao="Mercado Livre",
            valor=47.50,
            data_vencimento=date(2026, 4, 12),
            data_evento=date(2026, 3, 20),
            id_cartao=card.id,
            id_categoria=cats[0].id,
            recorrencia=REC_PARCELADA,
            num_parcelas=4,
            valor_por_parcela=True,
            tag_ids=[tag_id],
        )

        inv_apr = cc.get_invoice(card.id, 2026, 4)
        assert len(inv_apr.items) == 1
        occ_p1 = inv_apr.items[0]
        assert occ_p1.descricao == "Mercado Livre"
        assert len(occ_p1.splits) == 1
        assert len(occ_p1.tags) == 1
        assert occ_p1.tags[0][0] == tag_id

        # 2. Abre ExpenseDialog sobre a parcela 1/4 e verifica escopo padrão 'all' e botão default
        dlg = ExpenseDialog(
            conn,
            profile_id="1",
            default_date=occ_p1.data_vencimento,
            card_mode=True,
            preselect_card_id=card.id,
            occurrence=occ_p1,
        )
        assert dlg.cb_scope.currentData() == "all"
        assert dlg.btn_save.isDefault() is True
        assert dlg.btn_split.autoDefault() is False
        assert dlg.selected_tag_ids() == [tag_id]

        # 3. Edita descrição e valor em toda a série (scope='all')
        tx.update_occurrence(
            occ_p1,
            scope="all",
            descricao="Capacete Moto",
            valor=50.00,
            data_vencimento=occ_p1.data_vencimento,
            data_evento=occ_p1.data_evento,
            id_cartao=card.id,
            id_categoria=cats[-1].id,
            tag_ids=[tag_id],
        )

        for m in (4, 5, 6, 7):
            inv_m = cc.get_invoice(card.id, 2026, m)
            assert len(inv_m.items) == 1
            assert inv_m.items[0].descricao == "Capacete Moto"
            assert inv_m.items[0].valor == 50.00
            assert inv_m.items[0].id_categoria == cats[-1].id
            assert len(inv_m.items[0].tags) == 1

        # 4. Cria compra à vista e altera a data_evento para depois do fechamento (deve migrar de fatura)
        tx.create_expense(
            descricao="Lanche",
            valor=32.00,
            data_vencimento=date(2026, 4, 12),
            data_evento=date(2026, 3, 25),
            id_cartao=card.id,
            id_categoria=cats[0].id,
        )
        inv_apr2 = cc.get_invoice(card.id, 2026, 4)
        occ_lanche = [o for o in inv_apr2.items if o.descricao == "Lanche"][0]

        tx.update_occurrence(
            occ_lanche,
            scope="this",
            descricao="Lanche Especial",
            valor=35.00,
            data_vencimento=occ_lanche.data_vencimento,
            data_evento=date(2026, 4, 10),  # após dia_fecha=4 -> fatura 05/2026
            id_cartao=card.id,
            id_categoria=cats[0].id,
        )
        inv_apr3 = cc.get_invoice(card.id, 2026, 4)
        assert not any(o.descricao == "Lanche Especial" for o in inv_apr3.items)
        inv_may = cc.get_invoice(card.id, 2026, 5)
        assert any(o.descricao == "Lanche Especial" and o.valor == 35.00 for o in inv_may.items)
    finally:
        conn.close()


def test_credit_card_fixed_recurring_and_conversion(tmp_path: Path) -> None:
    conn = _make_env(tmp_path)
    try:
        acc_repo = AccountRepository(conn)
        cat_repo = CategoryRepository(conn)
        tag_repo = TagRepository(conn)
        tx = TransactionService(conn)
        cc = CreditCardService(conn, tx)

        acc = acc_repo.create_account(descricao="Conta Nu", saldo_inicial=2000.0)
        card = cc.create_card(
            nome="Nubank Black", limite=5000.0, dia_fecha=4, dia_venc=12, id_conta=acc
        )
        cats = cat_repo.list_categories("DESPESA", "1")
        cat = cats[0]

        # 1. Cria despesa fixa recorrente de cartão (Netflix)
        tx.create_expense(
            descricao="Netflix Mensal",
            valor=55.90,
            data_vencimento=date(2026, 4, 12),
            data_evento=date(2026, 3, 20),
            id_cartao=card.id,
            id_categoria=cat.id,
            recorrencia=REC_FIXA_DESPESA,
        )

        # Deve aparecer na fatura de abril/2026 como Fixa
        inv_apr = cc.get_invoice(card.id, 2026, 4)
        netflix_apr = [o for o in inv_apr.items if o.descricao == "Netflix Mensal"]
        assert len(netflix_apr) == 1
        assert netflix_apr[0].is_fixed is True
        assert netflix_apr[0].parcela_label == "Fixa"
        assert netflix_apr[0].valor == 55.90

        # E nas faturas futuras (maio, junho, julho/2026) deve ser projetada automaticamente!
        for m in (5, 6, 7):
            inv_m = cc.get_invoice(card.id, 2026, m)
            netflix_m = [o for o in inv_m.items if o.descricao == "Netflix Mensal"]
            assert len(netflix_m) == 1, f"Netflix deve existir na fatura do mês {m}"
            assert netflix_m[0].is_fixed is True
            assert netflix_m[0].parcela_label == "Fixa"
            assert netflix_m[0].valor == 55.90

        # 2. Converte despesa única em fixa recorrente
        tx.create_expense(
            descricao="Spotify",
            valor=34.90,
            data_vencimento=date(2026, 4, 12),
            data_evento=date(2026, 3, 25),
            id_cartao=card.id,
            id_categoria=cat.id,
            recorrencia=REC_UNICA,
        )
        inv_apr_spot = cc.get_invoice(card.id, 2026, 4)
        spot_apr = [o for o in inv_apr_spot.items if o.descricao == "Spotify"][0]
        assert spot_apr.is_fixed is False

        # Edita para recorrente
        tx.update_occurrence(
            spot_apr,
            scope="this",
            recorrencia=REC_FIXA_DESPESA,
            descricao="Spotify Premium",
            valor=34.90,
            data_vencimento=spot_apr.data_vencimento,
            id_cartao=card.id,
            id_categoria=cat.id,
        )

        # Agora Spotify Premium deve ser Fixa e projetar para maio
        inv_apr_after = cc.get_invoice(card.id, 2026, 4)
        spot_apr_after = [o for o in inv_apr_after.items if o.descricao == "Spotify Premium"][0]
        assert spot_apr_after.is_fixed is True
        assert spot_apr_after.parcela_label == "Fixa"

        inv_may_after = cc.get_invoice(card.id, 2026, 5)
        assert any(o.descricao == "Spotify Premium" and o.is_fixed for o in inv_may_after.items)
    finally:
        conn.close()


def test_transacoes_view_redesign_components_and_empty_state(tmp_path: Path) -> None:
    """Valida a padronização visual da TransacoesView: 1 botão primário, empty state, badges e gridless."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    try:
        from app.ui.views.transacoes_view import TransacoesView
        from app.ui.components import Badge, EmptyStateWidget

        ctx = ("1", 10, 2026, "")
        view = TransacoesView(
            db=conn,
            get_context=lambda: ctx,
            on_data_mutated=lambda: None,
        )

        # 1. Botão primário único e ações secundárias discretas
        assert view.btn_new_expense.objectName() == "PrimaryButton"
        assert view.btn_new_income.objectName() == "SecondaryButton"
        assert view.btn_new_transfer.objectName() == "SecondaryButton"
        assert view.btn_new_card_exp.objectName() == "SecondaryButton"
        assert view.btn_delete.objectName() == "SecondaryButton"

        # 2. Tabela sem bordas verticais e cabeçalho vertical oculto
        assert view.table.showGrid() is False
        assert view.table.verticalHeader().isVisible() is False
        assert view.table.columnCount() == 8

        # 3. Estado vazio ativo quando não há lançamentos
        view.refresh_data()
        assert view.stack.currentWidget() == view.empty_widget
        assert isinstance(view.empty_widget, EmptyStateWidget)

        # 4. Cria lançamento e valida transição para a tabela com Badge pill
        tx = TransactionService(conn)
        tx.create_expense(
            descricao="Café",
            valor=12.50,
            data_vencimento=date(2026, 10, 15),
            profile_id="1",
        )
        view.refresh_data()
        assert view.stack.currentWidget() == view.table
        assert view.table.rowCount() == 1

        # Badge pill na coluna de Situação (coluna 6)
        cell_widget = view.table.cellWidget(0, 6)
        assert cell_widget is not None
        badge = cell_widget.findChild(Badge)
        assert badge is not None
        assert badge.text() in ("Pendente", "Efetivado")

        # Seleção ativa os botões de ação da barra inferior
        view.table.selectRow(0)
        assert view.btn_toggle_eff.isEnabled() is True
        assert view.btn_edit.isEnabled() is True
        assert view.btn_delete.isEnabled() is True

        view.close()
    finally:
        conn.close()


def test_cartoes_view_redesign_interactive_tiles_and_expandable_rows(tmp_path: Path) -> None:
    """Valida a Etapa 5 (Cartões de crédito interativos, logos 26px, filtro de categoria e linhas expansíveis)."""
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    try:
        from app.ui.views.cartoes_view import CartoesView
        from app.database.repositories.category_repository import CategoryRepository

        tx = TransactionService(conn)
        cc = CreditCardService(conn, tx)
        cat_repo = CategoryRepository(conn)
        cats = cat_repo.list_categories("DESPESA", "1")

        ctx = ("1", 10, 2026, "")
        cview = CartoesView(
            db=conn,
            get_context=lambda: ctx,
            on_data_mutated=lambda: None,
        )

        # 1. Estado vazio quando não há cartões ("Adicione seu primeiro cartão")
        cview.refresh_data()
        assert cview.main_stack.currentWidget() == cview.empty_cards_widget
        assert "Adicione seu primeiro cartão" in cview.empty_cards_widget.lbl_title.text()

        # 2. Cria 2 cartões (Nubank e Itaú) e lançamentos em categorias distintas
        c_nu = cc.create_card(nome="Nubank 4829", limite=2000.0, dia_fecha=3, dia_venc=10, brand_key="master")
        c_itau = cc.create_card(nome="Itaú Click", limite=4000.0, dia_fecha=5, dia_venc=15, brand_key="visa")

        tx.create_expense(
            descricao="Notebook Parcelado",
            valor=300.0,
            data_vencimento=date(2026, 10, 10),
            data_evento=date(2026, 9, 20),
            id_cartao=c_nu.id,
            id_categoria=cats[0].id,
            recorrencia=REC_PARCELADA,
            num_parcelas=4,
            valor_por_parcela=True,
        )
        tx.create_expense(
            descricao="Almoço Restaurante",
            valor=80.0,
            data_vencimento=date(2026, 10, 10),
            data_evento=date(2026, 9, 22),
            id_cartao=c_nu.id,
            id_categoria=cats[1].id if len(cats) > 1 else cats[0].id,
            recorrencia=REC_UNICA,
        )

        cview.refresh_data()
        assert cview.main_stack.currentWidget() != cview.empty_cards_widget
        assert len(cview.card_tiles) == 2

        # Verifica logo pequeno (26x26px), final do cartão e barra de limite
        tile_nu = cview.card_tiles[0]
        assert tile_nu.lbl_logo.width() == 26
        assert "4829" in tile_nu.lbl_last4.text()
        assert tile_nu.bar_limit.value() > 0

        # Botões "Pagar fatura" (primário) e "Novo lançamento no cartão" (secundário)
        assert cview.btn_pay_reopen.text() == "Pagar fatura"
        assert cview.btn_pay_reopen.objectName() == "PrimaryButton"
        assert cview.btn_add_purchase.text() == "Novo lançamento no cartão"
        assert cview.btn_add_purchase.objectName() == "SecondaryButton"

        # 3. Linhas expansíveis para mostrar parcelas restantes ao clicar
        assert cview.tbl_items.rowCount() == 2
        cview._on_item_cell_clicked(0, 0)
        assert cview.tbl_items.rowCount() == 3
        exp_item = cview.tbl_items.item(1, 0)
        assert exp_item is not None
        assert "Parcela 1 de 4" in exp_item.text()
        assert "restam 3" in exp_item.text()

        # Clicar novamente recolhe a linha expandida
        cview._on_item_cell_clicked(0, 0)
        assert cview.tbl_items.rowCount() == 2

        # 4. Filtro por categoria dentro da fatura
        if len(cats) > 1:
            idx_cat = cview.cb_filter_category.findData(cats[0].name)
            if idx_cat >= 0:
                cview.cb_filter_category.setCurrentIndex(idx_cat)
                assert cview.tbl_items.rowCount() == 1
            cview.cb_filter_category.setCurrentIndex(0)
            assert cview.tbl_items.rowCount() == 2

        # 5. Clicar no segundo cartão atualiza a fatura exibida abaixo
        cview._on_card_tile_clicked(c_itau.id)
        assert cview._selected_invoice is not None
        assert cview._selected_invoice.card.id == c_itau.id
        assert cview.lbl_invoice_title.text() == "Itaú Click"

        cview.close()
    finally:
        conn.close()









