"""Testes unitários dos novos widgets de Lançamento Inteligente (ai_entry_widgets)."""

from __future__ import annotations

from datetime import date
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.config.theme_palette import ThemePalette
from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA
from app.ui.dialogs.ai_entry_widgets import (
    AIQuickEntryDialogView,
    EntryCard,
    EntryOptions,
    EntryViewModel,
    parse_brl,
)


def _sample_options() -> EntryOptions:
    return EntryOptions(
        accounts=[("acc1", "Minha Conta Corrente"), ("acc2", "Poupança")],
        cards=[("c1", "Cartão Nubank"), ("c2", "Cartão Itaú")],
        categories={
            KIND_DESPESA: [("cat1", "Alimentação"), ("cat2", "Transporte"), ("cat3", "Outros")],
            KIND_RECEITA: [("catR1", "Salário"), ("catR2", "Investimentos")],
        },
    )


def test_parse_brl() -> None:
    assert parse_brl("R$ 12,50") == 12.50
    assert parse_brl("− R$ 3.500,00") == 3500.00
    assert parse_brl("+ R$ 45,90") == 45.90
    assert parse_brl("23.90") == 23.90
    assert parse_brl("0") is None
    assert parse_brl("") is None
    assert parse_brl("abc") is None


def test_ai_quick_entry_dialog_view_states_and_transitions() -> None:
    app = QApplication.instance() or QApplication([])
    pal = ThemePalette.for_mode("light")
    opts = _sample_options()

    dlg = AIQuickEntryDialogView(palette=pal, model_name="gemini-3.5-flash-lite")
    dlg.show()

    # 1. Estado Inicial (Input)
    assert dlg._state == "input"
    assert not dlg.suggestions.isHidden()
    assert dlg.status_row.isHidden()
    assert dlg.scroll.isHidden()
    assert dlg.btn_confirm.isEnabled() is False
    assert dlg.btn_interpret.text() == "Interpretar"

    # 2. Clicar em sugestão dispara emissão de interpretação
    emitted_texts: List[str] = []
    dlg.interpret_requested.connect(emitted_texts.append)
    dlg._use_suggestion("pão 10 cartão")
    assert dlg.txt_input.toPlainText() == "pão 10 cartão"
    assert len(emitted_texts) == 1

    # 3. Transição para Estado de Prévia com 3 lançamentos (Despesa, Receita, Transferência)
    entries = [
        EntryViewModel(
            kind=KIND_DESPESA,
            description="Pão integral",
            amount=12.00,
            when=date(2026, 10, 31),
            effective=True,
            account_id="acc1",
            category_id="cat1",
        ),
        EntryViewModel(
            kind=KIND_RECEITA,
            description="Salário",
            amount=3500.00,
            when=date(2026, 10, 31),
            effective=True,
            account_id="acc1",
            category_id="catR1",
        ),
        EntryViewModel(
            kind=KIND_TRANSFERENCIA,
            description="Reserva de emergência",
            amount=500.00,
            when=date(2026, 10, 31),
            effective=False,
            account_id="acc1",
            destination_account_id="acc2",
        ),
    ]

    dlg.show_preview(entries, opts)
    assert dlg._state == "preview"
    assert dlg.suggestions.isHidden()
    assert not dlg.status_row.isHidden()
    assert not dlg.scroll.isHidden()
    assert len(dlg._cards) == 3
    assert dlg.btn_confirm.isEnabled() is True
    assert "3 lançamentos" in dlg.btn_confirm.text()
    assert dlg.btn_interpret.text() == "Reinterpretar"

    # 4. Edição de valores nos cards
    card_exp = dlg._cards[0]
    assert card_exp.lbl_kind.text() == "DESPESA"
    assert "12,00" in card_exp.ed_amount.text()

    card_exp.ed_title.setText("Pão de queijo")
    card_exp._on_title()
    assert card_exp.vm.description == "Pão de queijo"

    card_exp.ed_amount.setText("15,50")
    card_exp._on_amount()
    assert card_exp.vm.amount == 15.50

    # 5. Status toggle em despesa de conta (Pago <-> Pendente)
    assert card_exp.vm.effective is True
    card_exp._toggle_status()
    assert card_exp.vm.effective is False
    assert card_exp.pill_status.text() == "Pendente"

    # 6. Card de Transferência possui pílula de destino
    card_transf = dlg._cards[2]
    assert card_transf.lbl_kind.text() == "TRANSFERÊNCIA"
    assert hasattr(card_transf, "pill_dest")
    assert card_transf.pill_dest.text() == "Poupança"

    # 7. Remoção de card atualiza rodapé e volta ao estado inicial se vazio
    dlg._remove_card(card_transf)
    assert len(dlg._cards) == 2
    assert "2 lançamentos" in dlg.btn_confirm.text()

    dlg._remove_card(dlg._cards[1])
    dlg._remove_card(dlg._cards[0])
    assert len(dlg._cards) == 0
    assert dlg._state == "input"
    assert dlg.suggestions.isVisible() is True

    dlg.close()


def test_attachment_and_recurrence_pill_controls() -> None:
    app = QApplication.instance() or QApplication([])
    pal = ThemePalette.for_mode("dark")
    opts = _sample_options()

    dlg = AIQuickEntryDialogView(palette=pal, model_name="gemini-3.5-flash-lite")
    dlg.show()

    # Anexo permite disparar interpretação mesmo com texto vazio
    emitted: List[str] = []
    dlg.interpret_requested.connect(emitted.append)
    dlg.set_attachment(b"png-bytes", "image/png", "comprovante.png")
    assert not dlg.attachment_row.isHidden()
    assert "comprovante.png" in dlg.pill_attachment.text()
    dlg._emit_interpret()
    assert emitted == [""]

    dlg.clear_attachment()
    assert dlg.attachment_row.isHidden()
    assert dlg._attachment_bytes is None

    # Pílula de recorrência / parcelamento no EntryCard
    vm = EntryViewModel(
        kind=KIND_DESPESA,
        description="Curso Online",
        amount=600.0,
        when=date(2026, 10, 31),
        effective=False,
        card_id="c1",
        category_id="cat1",
        num_parcelas=1,
        recorrente_mensal=False,
    )
    dlg.show_preview([vm], opts)
    card = dlg._cards[0]
    assert hasattr(card, "pill_rec")
    assert card.pill_rec.text() == "1x (À vista)"

    card._set_recurrence(fixed=False, installments=6)
    assert card.pill_rec.text() == "6x"
    assert card.to_entry().num_parcelas == 6
    assert card.to_entry().recorrente_mensal is False

    card._set_recurrence(fixed=True, installments=1)
    assert card.pill_rec.text() == "Fixa mensal"
    assert card.to_entry().recorrente_mensal is True
    assert card.to_entry().num_parcelas == 1

    dlg.close()


def test_entry_card_no_horizontal_clipping_with_long_labels() -> None:
    app = QApplication.instance() or QApplication([])
    pal = ThemePalette.for_mode("dark")
    opts = EntryOptions(
        accounts=[
            ("acc1", "Minha Conta Corrente"),
            ("acc2", "Pluggy Bank - GOLD Conta Corrente"),
        ],
        cards=[("c1", "Cartão Nubank")],
        categories={
            KIND_DESPESA: [
                ("cat_tel", "Telecommunications"),
                ("cat_long", "Transferência Bancária Internacional Longa"),
            ],
            KIND_RECEITA: [],
        },
    )
    dlg = AIQuickEntryDialogView(palette=pal, model_name="gemini-3.5-flash-lite")
    dlg.show()

    # 1. Despesa fixa mensal com nomes longos: pill_rec e pill_status em line4 sem estourar 600px
    vm_fixed = EntryViewModel(
        kind=KIND_DESPESA,
        description="Internet",
        amount=120.0,
        when=date(2026, 11, 15),
        effective=True,
        account_id="acc1",
        category_id="cat_tel",
        recorrente_mensal=True,
    )
    # 2. Despesa no cartão com nome longo de conta/categoria > 26 chars (testa elisão e line4)
    vm_long = EntryViewModel(
        kind=KIND_DESPESA,
        description="Software",
        amount=3600.0,
        when=date(2026, 11, 15),
        effective=False,
        account_id="acc2",
        category_id="cat_long",
        num_parcelas=10,
    )
    vm_card = EntryViewModel(
        kind=KIND_DESPESA,
        description="Notebook",
        amount=3600.0,
        when=date(2026, 11, 15),
        effective=False,
        card_id="c1",
        category_id="cat_tel",
        num_parcelas=10,
    )
    dlg.show_preview([vm_fixed, vm_long, vm_card], opts)
    card_fixed, card_long, card_card = dlg._cards

    assert card_fixed._line3.indexOf(card_fixed.pill_rec) == -1
    assert card_fixed._line4.indexOf(card_fixed.pill_rec) >= 0
    assert card_fixed._line4.indexOf(card_fixed.pill_status) >= 0
    assert card_fixed.minimumSizeHint().width() <= 600

    assert card_card._line3.indexOf(card_card.pill_status) == -1
    assert card_card._line4.indexOf(card_card.pill_status) >= 0

    assert card_long.pill_source.text().endswith("…")
    assert len(card_long.pill_source.text()) <= 26
    assert card_long.pill_source.toolTip() == "Pluggy Bank - GOLD Conta Corrente"
    assert card_long.pill_cat.text().endswith("…")
    assert card_long.pill_cat.toolTip() == "Transferência Bancária Internacional Longa"
    assert card_long.minimumSizeHint().width() <= 600

    dlg.close()
