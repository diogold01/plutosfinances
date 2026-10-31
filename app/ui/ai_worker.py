"""Worker assíncrono (QThread) para chamadas de IA sem travar a interface."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from app.domain.services.ai_service import (
    AIContext,
    AIService,
    AIServiceError,
    TransactionDraft,
)


class AITestWorker(QThread):
    """Testa a chave em background. Emite `succeeded(list)` (vazia) ou `failed(str)`."""

    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, service: AIService, parent: Optional[object] = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._service = service

    def run(self) -> None:
        try:
            self._service.test_connection()
            self.succeeded.emit([])
        except AIServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Erro inesperado: {exc}")


class AIParseWorker(QThread):
    """Interpreta um texto em background. Emite `succeeded(list)` ou `failed(str)`."""

    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(
        self, service: AIService, text: str, context: AIContext, parent: Optional[object] = None
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._service = service
        self._text = text
        self._context = context

    def run(self) -> None:
        try:
            drafts: List[TransactionDraft] = self._service.parse_transactions(
                self._text, self._context
            )
            self.succeeded.emit(drafts)
        except AIServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - nunca deixar a thread morrer silenciosa
            self.failed.emit(f"Erro inesperado: {exc}")
