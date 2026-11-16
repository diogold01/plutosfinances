"""Testes unitários e de integração para o serviço de sincronização, mapeamento, deduplicação e UI (Fases 3 e 4)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from app.config.app_settings import AppSettings
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.services.pluggy_client import PluggyClient, PluggyConnectedItem
from app.services.pluggy_sync_service import (
    MappedAccountDTO,
    PluggySyncService,
    SyncBatchResult,
)
from app.ui.views.open_finance_dialog import OpenFinanceSyncDialog

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sync_service():
    client = MagicMock(spec=PluggyClient)
    return PluggySyncService(client=client, db=None)


def test_map_bank_accounts(sync_service):
    raw_accounts = [
        {
            "id": "acc_1",
            "type": "BANK",
            "name": "Conta Corrente",
            "balance": 2500.50,
            "currencyCode": "BRL",
        },
        {
            "id": "acc_2",
            "type": "CREDIT",
            "name": "Cartão Black",
            "balance": 450.00,
            "currencyCode": "BRL",
        },
    ]

    mapped = sync_service.map_bank_accounts(raw_accounts, institution_name="Nubank")
    assert len(mapped) == 2

    # Conta corrente
    assert mapped[0].external_id == "acc_1"
    assert mapped[0].nome == "Nubank - Conta Corrente"
    assert mapped[0].tipo_plutos == "CONTA"
    assert mapped[0].saldo_atual == 2500.50

    # Cartão de crédito
    assert mapped[1].external_id == "acc_2"
    assert mapped[1].nome == "Nubank - Cartão Black"
    assert mapped[1].tipo_plutos == "CARTAO"


def test_map_multiple_investments_to_independent_accounts(sync_service):
    """Valida a Abordagem 1: múltiplos investimentos mapeados como contas independentes."""
    raw_investments = [
        {
            "id": "inv_cdb",
            "type": "FIXED_INCOME",
            "subtype": "CDB",
            "name": "CDB 100% CDI",
            "balance": 5000.00,
        },
        {
            "id": "inv_caixinha",
            "type": "FIXED_INCOME",
            "name": "Caixinha Reserva",
            "balance": 3200.75,
        },
        {
            "id": "inv_lci",
            "type": "FIXED_INCOME",
            "subtype": "LCI",
            "name": "LCI 95% CDI",
            "balance": 10000.00,
        },
    ]

    mapped = sync_service.map_investments_to_accounts(raw_investments, institution_name="Nubank")
    assert len(mapped) == 3

    assert mapped[0].external_id == "inv_cdb"
    assert mapped[0].nome == "Nubank - CDB 100% CDI"
    assert mapped[0].tipo_plutos == "INVESTIMENTO"
    assert mapped[0].saldo_atual == 5000.00

    assert mapped[1].external_id == "inv_caixinha"
    assert mapped[1].nome == "Nubank - Caixinha Reserva"
    assert mapped[1].tipo_plutos == "INVESTIMENTO"
    assert mapped[1].saldo_atual == 3200.75

    assert mapped[2].external_id == "inv_lci"
    assert mapped[2].nome == "Nubank - LCI 95% CDI"
    assert mapped[2].tipo_plutos == "INVESTIMENTO"
    assert mapped[2].saldo_atual == 10000.00


def test_normalize_transaction(sync_service):
    raw_tx_expense = {
        "id": "tx_01",
        "date": "2026-05-10T14:00:00.000Z",
        "description": "Supermercado Extra",
        "amount": -150.80,
        "type": "DEBIT",
        "status": "POSTED",
        "category": "Alimentação",
    }

    row = sync_service.normalize_transaction(raw_tx_expense, account_name="Nubank")
    assert row is not None
    assert row.kind == "despesa"
    assert row.valor == 150.80
    assert row.data_vencimento == date(2026, 5, 10)
    assert row.efetivada is True
    assert row.categoria == "Alimentação"
    assert "tx_01" in row.observacoes


def test_deduplication_engine_in_batch(sync_service):
    """Garante que compras repetidas no mesmo lote ou subsequentes sejam identificadas."""
    acc = MappedAccountDTO(
        external_id="acc_nubank",
        nome="Nubank",
        tipo_plutos="CONTA",
        saldo_atual=1000.0,
    )

    batch_with_duplicates = [
        {
            "id": "tx_a1",
            "date": "2026-05-10T10:00:00Z",
            "description": "Almoço Restaurante",
            "amount": -45.00,
            "type": "DEBIT",
            "status": "POSTED",
        },
        # Transação duplicada (mesmo dia, mesmo valor, mesma descrição)
        {
            "id": "tx_a2",
            "date": "2026-05-10T10:00:00Z",
            "description": "Almoço Restaurante",
            "amount": -45.00,
            "type": "DEBIT",
            "status": "POSTED",
        },
        # Transação nova diferente
        {
            "id": "tx_b1",
            "date": "2026-05-10T12:00:00Z",
            "description": "Farmácia São Paulo",
            "amount": -28.90,
            "type": "DEBIT",
            "status": "POSTED",
        },
    ]

    res = sync_service.process_transactions_batch(acc, batch_with_duplicates)

    assert res.total_novas == 2
    assert res.total_duplicadas == 1
    assert res.novas_transacoes[0].descricao == "Almoço Restaurante"
    assert res.novas_transacoes[1].descricao == "Farmácia São Paulo"
    assert res.duplicadas_ignoradas[0].descricao == "Almoço Restaurante"


def test_full_preview_and_apply_sync_to_sqlite_and_ui_dialog(tmp_path: Path):
    """
    Valida a Fase 4 completa:
    - Coleta de prévia (contas, cartões, 3 investimentos e transações)
    - Efetivação no SQLite (criação de contas, investimentos independentes, cartões e transações)
    - 0% de duplicação em re-sincronização subsequente
    - Renderização da prévia no OpenFinanceSyncDialog (PySide6)
    """
    _get_qapp()
    db_path = tmp_path / "pluggy_sync_test.sqlite"
    settings = AppSettings.load(tmp_path / "settings_pluggy.json")
    settings.active_db_path = str(db_path)
    settings.save()

    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_path, overwrite=True)

    mock_client = MagicMock(spec=PluggyClient)
    mock_client.fetch_accounts.return_value = [
        {
            "id": "acc_nu_1",
            "type": "BANK",
            "name": "Conta Corrente",
            "balance": 1850.00,
            "currencyCode": "BRL",
        },
        {
            "id": "card_nu_1",
            "type": "CREDIT",
            "name": "Ultravioleta",
            "balance": 320.00,
            "currencyCode": "BRL",
            "creditData": {
                "creditLimit": 12000.00,
                "balanceCloseDate": "2026-10-05",
                "balanceDueDate": "2026-10-12",
            },
        },
    ]
    mock_client.fetch_investments.return_value = [
        {"id": "inv_1", "name": "CDB Liquidez Diária", "balance": 5000.00},
        {"id": "inv_2", "name": "Caixinha Reserva", "balance": 3000.00},
        {"id": "inv_3", "name": "LCI 95% CDI", "balance": 2000.00},
    ]

    def _side_effect_txs(account_id: str, from_date=None):
        if account_id == "acc_nu_1":
            return [
                {
                    "id": "tx_100",
                    "date": "2026-10-15T10:00:00Z",
                    "description": "Salário Empresa",
                    "amount": 4500.00,
                    "type": "CREDIT",
                    "status": "POSTED",
                    "category": "Salário",
                },
                {
                    "id": "tx_101",
                    "date": "2026-10-16T12:00:00Z",
                    "description": "Padaria Central",
                    "amount": -35.50,
                    "type": "DEBIT",
                    "status": "POSTED",
                    "category": "Alimentação",
                },
            ]
        return [
            {
                "id": "tx_200",
                "date": "2026-10-18T19:00:00Z",
                "description": "iFood Restaurante",
                "amount": 89.90,
                "type": "DEBIT",
                "status": "POSTED",
                "category": "Alimentação",
            },
            {
                "id": "tx_201",
                "date": "2026-10-10T10:00:00Z",
                "description": "Pagamento recebido",
                "amount": -500.00,
                "type": "CREDIT",
                "status": "POSTED",
            },
        ]

    mock_client.fetch_transactions.side_effect = _side_effect_txs

    service = PluggySyncService(client=mock_client, db=db)
    items = [PluggyConnectedItem(item_id="item_nu", connector_name="Nubank")]

    # 1. Coleta a prévia
    batches = service.fetch_full_preview(items, profile_id="1", from_date="2026-10-01")
    assert len(batches) == 5  # 1 Conta + 1 Cartão + 3 Investimentos

    # 2. Testa população do modal PySide6
    dlg = OpenFinanceSyncDialog(db, profile_id="1", mes=10, ano=2026)
    dlg.populate_review_tables(batches)
    assert dlg.table_accounts.rowCount() == 5
    assert dlg.table_txs.rowCount() == 3  # 2 da conta + 1 do cartão ('Pagamento recebido' foi filtrado)

    # 3. Aplica resultados no SQLite
    summary1 = service.apply_sync_results(batches, profile_id="1", mes=10, ano=2026)
    assert summary1.contas_criadas == 1
    assert summary1.investimentos_atualizados == 3
    assert summary1.cartoes_sincronizados == 1
    assert summary1.transacoes_importadas == 3
    assert summary1.duplicadas_ignoradas == 0

    # Verifica saldos reconciliados das contas e dos 3 investimentos no SQLite
    acc_repo = AccountRepository(db)
    all_summaries = acc_repo.list_accounts_with_balances(mes=10, ano=2026, profile_id="1")
    by_name = {s.descricao: s for s in all_summaries}
    assert by_name["Nubank - Conta Corrente"].saldo_atual == 1850.00
    assert by_name["Nubank - CDB Liquidez Diária"].saldo_atual == 5000.00
    assert by_name["Nubank - CDB Liquidez Diária"].investimento == "S"
    assert by_name["Nubank - Caixinha Reserva"].saldo_atual == 3000.00
    assert by_name["Nubank - LCI 95% CDI"].saldo_atual == 2000.00

    # 4. Re-executa sincronização com os mesmos dados -> 0 novas transações, 3 ignoradas!
    batches_second = service.fetch_full_preview(items, profile_id="1", from_date="2026-10-01")
    assert sum(b.total_novas for b in batches_second) == 0
    assert sum(b.total_duplicadas for b in batches_second) == 3

    db.close()


def test_pluggy_sync_ai_batch_enrichment_and_transfer_reconciliation(tmp_path) -> None:
    """Valida enriquecimento híbrido (regra local + lote IA) e conciliação de transferência entre bancos no Open Finance."""
    import json
    from datetime import date

    from app.config.app_settings import AppSettings
    from app.database.connection_manager import ConnectionManager
    from app.database.repositories.account_repository import AccountRepository
    from app.database.repositories.category_repository import CategoryRepository
    from app.domain.models import KIND_DESPESA
    from app.domain.services.ai_entry_service import ResolvedEntry, save_learned_rule
    from app.domain.services.ai_service import AIService
    from app.io_module.contracts import CanonicalTransactionRow
    from app.services.pluggy_sync_service import (
        MappedAccountDTO,
        PluggySyncService,
        SyncBatchResult,
    )

    db_path = tmp_path / "pluggy_ai_sync.sqlite"
    settings = AppSettings.load(tmp_path / "pluggy_ai_settings.json")
    settings.active_db_path = str(db_path)
    settings.save()

    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_path, overwrite=True)

    acc_repo = AccountRepository(db)
    cat_repo = CategoryRepository(db)
    acc_a_id = acc_repo.create_account(descricao="Nubank", saldo_inicial=2000.0)
    acc_b_id = acc_repo.create_account(descricao="Inter", saldo_inicial=1000.0)

    exp_cats = cat_repo.list_categories("DESPESA", "1")
    uber_cat = next((c for c in exp_cats if "transporte" in c.nome.lower()), exp_cats[0])
    food_cat = next(
        (c for c in exp_cats if "aliment" in c.nome.lower() and c.id != uber_cat.id),
        exp_cats[1] if len(exp_cats) > 1 else exp_cats[0],
    )

    save_learned_rule(
        db,
        "1",
        ResolvedEntry(
            tipo=KIND_DESPESA,
            descricao="Uber",
            valor=20.0,
            data=date(2026, 10, 10),
            id_categoria=uber_cat.id,
        ),
        pattern_override="uber",
    )

    captured_bodies = []

    def _fake_transport(url, headers, body, timeout):
        text_body = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
        captured_bodies.append(text_body)
        payload = {
            "itens": [
                {
                    "descricao_original": "PAG*Mercadinho Bom",
                    "descricao_limpa": "Mercadinho Bom",
                    "categoria": food_cat.nome,
                    "eh_transferencia_propria": False,
                }
            ]
        }
        inner = json.dumps(payload)
        return json.dumps({"candidates": [{"content": {"parts": [{"text": inner}]}}]})

    fake_ai = AIService("test-key", transport=_fake_transport)

    batch_a = SyncBatchResult(
        account=MappedAccountDTO(
            external_id="ext-acc-a",
            nome="Nubank",
            tipo_plutos="CONTA",
            saldo_atual=2000.0,
        ),
        novas_transacoes=[
            CanonicalTransactionRow(
                kind="despesa",
                descricao="UBER *TRIP 123",
                valor=28.90,
                data_vencimento=date(2026, 10, 15),
                data_lancamento=date(2026, 10, 15),
                data_efetivacao=date(2026, 10, 15),
                efetivada=True,
                categoria="Outros",
                subcategoria="Outros",
                conta="Nubank",
                fingerprint="pluggy-tx-1",
            ),
            CanonicalTransactionRow(
                kind="despesa",
                descricao="PAG*Mercadinho Bom",
                valor=95.00,
                data_vencimento=date(2026, 10, 16),
                data_lancamento=date(2026, 10, 16),
                data_efetivacao=date(2026, 10, 16),
                efetivada=True,
                categoria="Outros",
                subcategoria="Outros",
                conta="Nubank",
                fingerprint="pluggy-tx-2",
            ),
            CanonicalTransactionRow(
                kind="despesa",
                descricao="PIX ENVIADO RESERVA",
                valor=400.00,
                data_vencimento=date(2026, 10, 17),
                data_lancamento=date(2026, 10, 17),
                data_efetivacao=date(2026, 10, 17),
                efetivada=True,
                categoria="Outros",
                subcategoria="Outros",
                conta="Nubank",
                fingerprint="pluggy-tx-3",
            ),
        ],
    )
    batch_b = SyncBatchResult(
        account=MappedAccountDTO(
            external_id="ext-acc-b",
            nome="Inter",
            tipo_plutos="CONTA",
            saldo_atual=1000.0,
        ),
        novas_transacoes=[
            CanonicalTransactionRow(
                kind="receita",
                descricao="PIX RECEBIDO CONTA",
                valor=400.00,
                data_vencimento=date(2026, 10, 17),
                data_lancamento=date(2026, 10, 17),
                data_efetivacao=date(2026, 10, 17),
                efetivada=True,
                categoria="Outros",
                subcategoria="Outros",
                conta="Inter",
                fingerprint="pluggy-tx-4",
            ),
        ],
    )

    svc = PluggySyncService(client=None, db=db)  # type: ignore[arg-type]
    summary = svc.apply_sync_results(
        [batch_a, batch_b],
        profile_id="1",
        enrich_with_ai=True,
        ai_service=fake_ai,
    )

    assert summary.categorizadas_regras_locais == 1
    assert summary.categorizadas_ia == 1
    assert summary.transferencias_conciliadas == 1
    assert summary.transacoes_importadas == 3

    assert len(captured_bodies) == 1
    assert "PAG*Mercadinho Bom" in captured_bodies[0]
    assert "UBER *TRIP 123" not in captured_bodies[0]

    despesas = db.execute_query("SELECT descricao, id_categoria FROM despesas WHERE data_exclusao IS NULL")
    receitas = db.execute_query("SELECT id FROM receitas WHERE data_exclusao IS NULL")
    transfers = db.execute_query(
        "SELECT id_conta_origem, id_conta_destino, valor FROM transferencias WHERE data_exclusao IS NULL"
    )

    assert len(receitas) == 0
    assert len(transfers) == 1
    assert transfers[0]["id_conta_origem"] == acc_a_id
    assert transfers[0]["id_conta_destino"] == acc_b_id
    assert float(transfers[0]["valor"]) == 400.0

    by_desc = {r["descricao"]: r for r in despesas}
    assert "Mercadinho Bom" in by_desc
    assert by_desc["Mercadinho Bom"]["id_categoria"] == food_cat.id
    uber_rows = [r for r in despesas if "uber" in str(r["descricao"]).lower()]
    assert len(uber_rows) == 1
    assert uber_rows[0]["id_categoria"] == uber_cat.id

    db.close()
