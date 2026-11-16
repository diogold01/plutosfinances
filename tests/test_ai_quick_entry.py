"""Testes do Lançamento Rápido por IA (catálogo, persistência e diálogo)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA, REC_FIXA_DESPESA, REC_PARCELADA
from app.domain.services.ai_entry_service import load_catalog, persist_entry
from app.domain.services.ai_service import AIService, TransactionDraft
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.transaction_service import TransactionService
from app.ui.dialogs.ai_quick_entry_dialog import AIQuickEntryDialog
from tests.test_transactions_and_cards import _make_env


def test_catalog_resolve_persist_and_dialog(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    conn = _make_env(tmp_path)
    try:
        tx = TransactionService(conn)
        cat = load_catalog(conn, tx, "1")
        assert cat.contas, "ambiente de teste deve ter ao menos uma conta"
        conta_nome = cat.contas[0][1]

        d1 = TransactionDraft(KIND_DESPESA, "Almoço", 45.9, date(2026, 10, 31), conta=conta_nome)
        d2 = TransactionDraft(KIND_RECEITA, "Salário", 3500.0, date(2026, 10, 30))
        e1, e2 = cat.resolve(d1), cat.resolve(d2)
        assert e1.id_conta == cat.contas[0][0] and e2.id_conta == cat.default_conta_id

        persist_entry(tx, e1, "1")
        persist_entry(tx, e2, "1")
        occs = tx.list_occurrences(2026, 10, profile_id="1")
        assert {o.descricao for o in occs} >= {"Almoço", "Salário"}

        saved: list[int] = []
        dlg = AIQuickEntryDialog(
            conn, "1", lambda: saved.append(1), service=AIService("k", transport=lambda *a: "")
        )
        dlg.apply_drafts([d1, d2])
        assert len(dlg._rows) == 2 and dlg.btn_confirm.isEnabled()
        dlg._rows[1].chk.setChecked(False)
        assert dlg.save_entries() == 1 and saved == [1]
    finally:
        conn.close()


def test_learned_rules_installments_fixed_and_transfer_persistence(tmp_path: Path) -> None:
    conn = _make_env(tmp_path)
    try:
        tx = TransactionService(conn)
        cat = load_catalog(conn, tx, "1")
        assert cat.cat_despesa, "ambiente deve ter categorias de despesa"
        conta_nome = cat.contas[0][1]
        cat_id, cat_nome = cat.cat_despesa[0]

        # Garante uma segunda conta para transferência e um cartão para teste de aprendizado
        from app.database.repositories.account_repository import AccountRepository

        acc_repo = AccountRepository(conn)
        acc2_id = acc_repo.create_account(
            descricao="Reserva Poupança", saldo_inicial=0.0, profile_id="1"
        )
        card = CreditCardService(conn, tx).create_card(
            profile_id="1",
            nome="Cartão XP",
            limite=5000.0,
            dia_fecha=10,
            dia_venc=20,
            id_conta=cat.contas[0][0],
        )

        # 1. Salvar lançamento para gravar aprendizado em regras_categorizacao_ia
        draft_learn = TransactionDraft(
            KIND_DESPESA,
            "Uber Trip",
            28.5,
            date(2026, 10, 15),
            cartao=card.nome,
            categoria=cat_nome,
        )
        cat = load_catalog(conn, tx, "1")
        resolved_learn = cat.resolve(draft_learn)
        persist_entry(tx, resolved_learn, "1")

        # Novo rascunho sem categoria e sem conta/cartão herda da regra aprendida
        cat_reloaded = load_catalog(conn, tx, "1")
        draft_repeat = TransactionDraft(
            KIND_DESPESA,
            "Uber Trip",
            32.0,
            date(2026, 10, 20),
            conta=None,
            cartao=None,
            categoria=None,
        )
        resolved_repeat = cat_reloaded.resolve(draft_repeat)
        assert resolved_repeat.id_categoria == cat_id
        assert resolved_repeat.id_cartao == card.id
        assert "categoria" not in resolved_repeat.campos_fallback
        assert "conta" not in resolved_repeat.campos_fallback

        # 2. Persistência de parcelamento (3x)
        draft_parc = TransactionDraft(
            KIND_DESPESA,
            "Fone Bluetooth",
            300.0,
            date(2026, 10, 5),
            conta=conta_nome,
            categoria=cat_nome,
            num_parcelas=3,
            valor_por_parcela=False,
        )
        persist_entry(tx, cat_reloaded.resolve(draft_parc), "1")
        rows_parc = conn.execute_query(
            "SELECT num_parcela, num_parcelas, recorrencia, valor FROM despesas WHERE descricao = ?",
            ("Fone Bluetooth",),
        )
        assert len(rows_parc) == 3
        assert {int(r["num_parcela"]) for r in rows_parc} == {1, 2, 3}
        assert all(r["recorrencia"] == REC_PARCELADA for r in rows_parc)
        assert all(float(r["valor"]) == 100.0 for r in rows_parc)

        # 3. Persistência de despesa fixa mensal
        draft_fixed = TransactionDraft(
            KIND_DESPESA,
            "Internet Fibra",
            120.0,
            date(2026, 10, 10),
            conta=conta_nome,
            categoria=cat_nome,
            recorrente_mensal=True,
        )
        persist_entry(tx, cat_reloaded.resolve(draft_fixed), "1")
        row_fixed = conn.fetch_one(
            "SELECT recorrencia, valor FROM despesas WHERE descricao = ?",
            ("Internet Fibra",),
        )
        assert row_fixed is not None
        assert row_fixed["recorrencia"] == REC_FIXA_DESPESA

        # 4. Persistência de transferência
        draft_transf = TransactionDraft(
            KIND_TRANSFERENCIA,
            "Aporte Reserva",
            500.0,
            date(2026, 10, 25),
            conta=conta_nome,
            conta_destino="Reserva Poupança",
            efetivada=True,
        )
        resolved_transf = cat_reloaded.resolve(draft_transf)
        assert resolved_transf.id_conta == cat.contas[0][0]
        assert resolved_transf.id_conta_destino == acc2_id
        persist_entry(tx, resolved_transf, "1")
        row_transf = conn.fetch_one(
            "SELECT id_conta_origem, id_conta_destino, valor FROM transferencias WHERE descricao = ?",
            ("Aporte Reserva",),
        )
        assert row_transf is not None
        assert row_transf["id_conta_origem"] == cat.contas[0][0]
        assert row_transf["id_conta_destino"] == acc2_id
        assert float(row_transf["valor"]) == 500.0
    finally:
        conn.close()


def test_learned_rule_overrides_ai_guess_and_cleans_redundant_amount(tmp_path: Path) -> None:
    from app.database.repositories.category_repository import CategoryRepository

    conn = _make_env(tmp_path)
    try:
        tx = TransactionService(conn)
        cat_repo = CategoryRepository(conn)
        custom_cat = cat_repo.create_category(KIND_DESPESA, "Eletrônicos", color_hex="#3F51B5")
        cat = load_catalog(conn, tx, "1")
        conta_nome = cat.contas[0][1]

        # Grava regra aprendida para "Notebook" -> Eletrônicos
        first_draft = TransactionDraft(
            KIND_DESPESA,
            "Notebook",
            3600.0,
            date(2026, 11, 15),
            conta=conta_nome,
            categoria="Eletrônicos",
        )
        persist_entry(tx, cat.resolve(first_draft), "1")

        # Novo rascunho em que a IA devolveu "Outros" e manteve o valor "3600" na descrição
        cat_reloaded = load_catalog(conn, tx, "1")
        outros_name = next(
            (name for _, name in cat_reloaded.cat_despesa if name.casefold() == "outros"),
            None,
        )
        assert outros_name is not None
        second_draft = TransactionDraft(
            KIND_DESPESA,
            "Notebook 3600",
            3600.0,
            date(2026, 11, 16),
            conta=conta_nome.lower(),
            categoria=outros_name,
        )
        resolved = cat_reloaded.resolve(second_draft)
        assert resolved.descricao == "Notebook"
        assert resolved.id_categoria == custom_cat.id
        assert resolved.id_conta == cat.contas[0][0]
    finally:
        conn.close()
