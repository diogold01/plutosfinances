"""Testes do Lançamento Rápido por IA (catálogo, persistência e diálogo)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.ai_entry_service import load_catalog, persist_entry
from app.domain.services.ai_service import AIService, TransactionDraft
from app.domain.services.transaction_service import TransactionService
from app.ui.dialogs.ai_quick_entry_dialog import AIQuickEntryDialog
from tests.test_etapa4_transactions_and_cards import _make_env


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
