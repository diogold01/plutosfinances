"""Worker assíncrono (QThread) para chamadas de IA sem travar a interface."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from app.domain.services.ai_service import (
    AIContext,
    AIService,
    AIServiceError,
    FinancialHealthReport,
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
    """Interpreta um texto e/ou anexo em background. Emite `succeeded(list)` ou `failed(str)`."""

    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        service: AIService,
        text: str,
        context: AIContext,
        parent: Optional[object] = None,
        *,
        attachment_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._service = service
        self._text = text
        self._context = context
        self._attachment_bytes = attachment_bytes
        self._mime_type = mime_type

    def run(self) -> None:
        try:
            drafts: List[TransactionDraft] = self._service.parse_transactions(
                self._text,
                self._context,
                attachment_bytes=self._attachment_bytes,
                mime_type=self._mime_type,
            )
            self.succeeded.emit(drafts)
        except AIServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - nunca deixar a thread morrer silenciosa
            self.failed.emit(f"Erro inesperado: {exc}")


class FinancialHealthWorker(QThread):
    """Gera diagnóstico de saúde financeira com IA em background. Emite `succeeded(FinancialHealthReport)` ou `failed(str)`."""

    succeeded = Signal(object)  # FinancialHealthReport
    failed = Signal(str)

    def __init__(
        self,
        service: AIService,
        payload: Dict[str, Any],
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._service = service
        self._payload = payload

    def run(self) -> None:
        try:
            report: FinancialHealthReport = self._service.generate_financial_health_report(
                self._payload
            )
            self.succeeded.emit(report)
        except AIServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - nunca deixar a thread morrer silenciosa
            self.failed.emit(f"Erro inesperado: {exc}")


class AICopilotWorker(QThread):
    """Responde perguntas ao Copiloto Financeiro em background. Emite `succeeded(str)` ou `failed(str)`."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        service: AIService,
        question: str,
        payload: Dict[str, Any],
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._service = service
        self._question = question
        self._payload = payload

    def run(self) -> None:
        try:
            answer = self._service.ask_financial_copilot(self._question, self._payload)
            self.succeeded.emit(answer)
        except AIServiceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - nunca deixar a thread morrer silenciosa
            self.failed.emit(f"Erro inesperado: {exc}")
