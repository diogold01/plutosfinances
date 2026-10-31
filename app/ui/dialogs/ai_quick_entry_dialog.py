"""Modal de Lançamento Inteligente por IA (BYOK Gemini) — Design System Plutos."""

from __future__ import annotations

from typing import Callable, List, Optional, Set

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from app.config import gemini_key_store as key_store
from app.config.theme_palette import ThemePalette
from app.database.connection_manager import ConnectionManager
from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA
from app.domain.services.ai_entry_service import (
    QuickEntryCatalog,
    ResolvedEntry,
    load_catalog,
    persist_entry,
)
from app.domain.services.ai_service import AIService, TransactionDraft
from app.domain.services.transaction_service import TransactionService
from app.ui.ai_worker import AIParseWorker
from app.ui.dialogs.ai_entry_widgets import (
    AIQuickEntryDialogView,
    EntryCard,
    EntryOptions,
    EntryViewModel,
)


def to_view_model(entry: ResolvedEntry) -> EntryViewModel:
    fb = set(entry.campos_fallback or [])
    return EntryViewModel(
        kind=entry.tipo,
        description=entry.descricao,
        amount=entry.valor,
        when=entry.data,
        effective=entry.efetivada,
        account_id=entry.id_conta,
        destination_account_id=entry.id_conta_destino,
        card_id=entry.id_cartao,
        category_id=entry.id_categoria,
        fallback_fields={
            "account" if ("id_conta" in fb or "conta" in fb) else None,
            "category" if ("id_categoria" in fb or "categoria" in fb) else None,
        }
        - {None},
    )


def to_resolved_entry(vm: EntryViewModel) -> ResolvedEntry:
    return ResolvedEntry(
        tipo=vm.kind,
        descricao=vm.description,
        valor=vm.amount,
        data=vm.when,
        id_conta=vm.account_id,
        id_cartao=vm.card_id,
        id_categoria=vm.category_id,
        efetivada=vm.effective,
        id_conta_destino=vm.destination_account_id,
        campos_fallback=set(vm.fallback_fields),
    )


class AIQuickEntryDialog(AIQuickEntryDialogView):
    """Diálogo modal inteligente conectado à persistência e aos workers do Plutos."""

    def __init__(
        self,
        db: ConnectionManager,
        profile_id: str,
        on_saved: Callable[[], None],
        service: Optional[AIService] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        pal = ThemePalette.for_mode(db.settings.theme_mode)
        super().__init__(palette=pal, model_name=db.settings.gemini_model, parent=parent)
        self.db = db
        self.profile_id = profile_id
        self.on_saved = on_saved
        self.tx = TransactionService(db)
        self.catalog = load_catalog(db, self.tx, profile_id)
        self._service = service or self._build_service()
        self._worker: Optional[AIParseWorker] = None

        # Aliases para compatibilidade
        self.ed_text = self.txt_input
        self.btn_parse = self.btn_interpret

        # Conecta os sinais da casca visual aos manipuladores
        self.interpret_requested.connect(self.interpret)
        self.confirmed.connect(lambda _vms: self.save_entries())

        if not self._service.is_configured:
            self.show_error(
                "Chave do Gemini não configurada. Vá em Configurações → Inteligência Artificial."
            )

    @property
    def _rows(self) -> List[EntryCard]:
        """Propriedade mantida para retrocompatibilidade de testes."""
        return self._cards

    def _build_entry_options(self) -> EntryOptions:
        return EntryOptions(
            accounts=list(self.catalog.contas),
            cards=list(self.catalog.cartoes),
            categories={
                KIND_DESPESA: list(self.catalog.cat_despesa),
                KIND_RECEITA: list(self.catalog.cat_receita),
            },
        )

    def _build_service(self) -> AIService:
        key, _src = key_store.resolve_gemini_key(self.db.settings.user_data_dir)
        return AIService(key, model=self.db.settings.gemini_model)

    def interpret(self, text: Optional[str] = None) -> None:
        raw_text = (
            text if text is not None else self.txt_input.toPlainText()
        ).strip()
        if not raw_text:
            self.show_error("Digite o lançamento na barra acima.")
            return
        if not self._service.is_configured:
            self.show_error(
                "Chave do Gemini não configurada. Configure em Configurações → Inteligência Artificial."
            )
            return

        self.set_loading(True)
        self.error_row.setVisible(False)
        self._worker = AIParseWorker(
            self._service, raw_text, self.catalog.to_context(), self
        )
        self._worker.succeeded.connect(self.apply_drafts)
        self._worker.failed.connect(self.show_error)
        self._worker.start()

    def apply_drafts(self, drafts: List[TransactionDraft]) -> None:
        self.set_loading(False)
        resolved = [self.catalog.resolve(d) for d in drafts]
        vms = [to_view_model(r) for r in resolved]
        opts = self._build_entry_options()
        self.show_preview(vms, opts)

    def save_entries(self) -> int:
        """Persiste todos os lançamentos marcados e notifica a aplicação."""
        saved = 0
        try:
            for card in list(self._cards):
                if card.chk.isChecked():
                    entry = card.to_entry()
                    persist_entry(self.tx, entry, self.profile_id)
                    card.chk.setChecked(False)
                    saved += 1
        except ValueError as exc:
            self.show_error(str(exc))
            if saved:
                self.on_saved()
            return saved

        if saved:
            self.on_saved()
        self.done_ok()
        return saved
