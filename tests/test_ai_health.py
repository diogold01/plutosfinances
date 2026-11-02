"""Testes unitários isolados do Diagnóstico de Saúde Financeira com IA (Etapa 3 - AIService)."""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from app.domain.services.ai_service import (
    AIService,
    AIServiceError,
    FinancialHealthReport,
)
from app.ui.ai_worker import FinancialHealthWorker


def _fake_health_transport(data: Dict[str, Any]):
    """Simula a resposta da API do Google Gemini com JSON estruturado."""
    def transport(url: str, headers: Dict[str, str], body: bytes, timeout: int) -> str:
        assert "x-goog-api-key" in headers
        assert "generativelanguage.googleapis.com" in url
        # Verifica se o body continha application/json
        decoded_body = json.loads(body.decode("utf-8"))
        assert "generationConfig" in decoded_body
        assert decoded_body["generationConfig"]["responseMimeType"] == "application/json"

        inner_text = json.dumps(data)
        envelope = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": inner_text}
                        ]
                    }
                }
            ]
        }
        return json.dumps(envelope)

    return transport


SAMPLE_VALID_RESPONSE: Dict[str, Any] = {
    "score_saude": 85,
    "resumo": "Excelente equilíbrio financeiro com reserva mensal consistente acima de 20%.",
    "regra_50_30_20": {
        "essenciais_pct": 45.0,
        "estilo_vida_pct": 25.0,
        "poupanca_pct": 30.0,
        "comentario": "Despesas essenciais e estilo de vida totalmente controladas.",
    },
    "alertas_anomalias": [
        "Mercado subiu 35% em relação à média dos últimos 2 meses."
    ],
    "projecao_fechamento": "Projeção de fechamento positivo com sobra estimada de R$ 1.500,00.",
    "recomendacoes_praticas": [
        "Auditar itens supérfluos na fatura do cartão de crédito.",
        "Destinar o excedente de R$ 1.500,00 para a caixinha CDB 100% CDI.",
        "Acompanhar o ritmo de gastos semanais com alimentação fora de casa.",
    ],
}


def test_generate_health_report_success() -> None:
    svc = AIService(
        api_key="valid-gemini-key",
        transport=_fake_health_transport(SAMPLE_VALID_RESPONSE),
    )
    payload = {
        "periodo": "10/2026",
        "totais": {"receitas": 5000.0, "despesas": 3500.0},
        "detalhamento_categorias": [],
    }

    report = svc.generate_financial_health_report(payload)

    assert isinstance(report, FinancialHealthReport)
    assert report.score_saude == 85
    assert "Excelente equilíbrio" in report.resumo
    assert report.essenciais_pct == 45.0
    assert report.estilo_vida_pct == 25.0
    assert report.poupanca_pct == 30.0
    assert len(report.alertas_anomalias) == 1
    assert "Mercado subiu 35%" in report.alertas_anomalias[0]
    assert len(report.recomendacoes_praticas) == 3
    assert "caixinha CDB" in report.recomendacoes_praticas[1]


def test_score_clamping() -> None:
    # Teste de pontuação fora do intervalo (ex.: 120 e -15)
    data_high = dict(SAMPLE_VALID_RESPONSE, score_saude=120)
    svc_high = AIService("k", transport=_fake_health_transport(data_high))
    rep_high = svc_high.generate_financial_health_report({"periodo": "10/2026"})
    assert rep_high.score_saude == 100

    data_low = dict(SAMPLE_VALID_RESPONSE, score_saude=-15)
    svc_low = AIService("k", transport=_fake_health_transport(data_low))
    rep_low = svc_low.generate_financial_health_report({"periodo": "10/2026"})
    assert rep_low.score_saude == 0


def test_empty_payload_raises_error() -> None:
    svc = AIService("valid-key")
    with pytest.raises(AIServiceError, match="Sem dados financeiros"):
        svc.generate_financial_health_report({})


def test_unconfigured_api_key_raises_error() -> None:
    svc = AIService("")
    with pytest.raises(AIServiceError, match="Chave de API do Gemini não configurada"):
        svc.generate_financial_health_report({"periodo": "10/2026"})


def test_malformed_response_raises_error() -> None:
    bad_transport = lambda *a: "not a json string"
    svc = AIService("key", transport=bad_transport)
    with pytest.raises(AIServiceError, match="Resposta da IA em formato inesperado"):
        svc.generate_financial_health_report({"periodo": "10/2026"})


def test_no_recommendations_raises_error() -> None:
    data_no_recs = dict(SAMPLE_VALID_RESPONSE, recomendacoes_praticas=[])
    svc = AIService("key", transport=_fake_health_transport(data_no_recs))
    with pytest.raises(AIServiceError, match="não retornou recomendações"):
        svc.generate_financial_health_report({"periodo": "10/2026"})


def test_build_health_prompt() -> None:
    payload = {
        "periodo": "10/2026",
        "totais": {"receitas": 7000.0, "despesas": 4000.0},
        "detalhamento_categorias": [{"categoria": "Mercado", "total": 1200.0}],
    }
    prompt = AIService._build_health_prompt(payload)
    assert "consultor de finanças pessoais brasileiro" in prompt
    assert "score_saude" in prompt
    assert "regra_50_30_20" in prompt
    assert "alertas_anomalias" in prompt
    assert "7000.0" in prompt


def test_financial_health_worker_success() -> None:
    svc = AIService("test-key", transport=_fake_health_transport(SAMPLE_VALID_RESPONSE))
    payload = {"periodo": "10/2026", "totais": {"receitas": 5000.0}}
    worker = FinancialHealthWorker(svc, payload)

    results: list[FinancialHealthReport] = []
    errors: list[str] = []
    worker.succeeded.connect(results.append)
    worker.failed.connect(errors.append)

    worker.run()

    assert len(results) == 1
    assert len(errors) == 0
    assert results[0].score_saude == 85


def test_financial_health_worker_failure() -> None:
    svc = AIService("")  # Sem chave
    payload = {"periodo": "10/2026"}
    worker = FinancialHealthWorker(svc, payload)

    results: list[FinancialHealthReport] = []
    errors: list[str] = []
    worker.succeeded.connect(results.append)
    worker.failed.connect(errors.append)

    worker.run()

    assert len(results) == 0
    assert len(errors) == 1
    assert "Chave de API do Gemini não configurada" in errors[0]
