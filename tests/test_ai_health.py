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
from app.ui.ai_worker import AICopilotWorker, FinancialHealthWorker


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


def test_ask_financial_copilot_success_and_validation() -> None:
    captured_prompts: list[str] = []

    def transport(url: str, headers: Dict[str, str], body: bytes, timeout: int) -> str:
        decoded = json.loads(body.decode("utf-8"))
        captured_prompts.append(decoded["contents"][0]["parts"][0]["text"])
        inner = json.dumps(
            {"resposta": "Com receita de R$ 5.000,00 e folga de R$ 1.500,00, você pode parcelar."}
        )
        return json.dumps({"candidates": [{"content": {"parts": [{"text": inner}]}}]})

    svc = AIService("valid-key", transport=transport)
    snapshot = {"periodo": "10/2026", "totais": {"receitas": 5000.0, "resultado_liquido": 1500.0}}
    ans = svc.ask_financial_copilot("Posso parcelar 1.500 em 3x?", snapshot)
    assert "R$ 1.500,00" in ans
    assert "Posso parcelar 1.500 em 3x?" in captured_prompts[0]
    assert "EXCLUSIVA" in captured_prompts[0]

    with pytest.raises(AIServiceError, match="Digite uma pergunta"):
        svc.ask_financial_copilot("   ", snapshot)

    with pytest.raises(AIServiceError, match="Sem dados financeiros"):
        svc.ask_financial_copilot("Como estou?", {})

    with pytest.raises(AIServiceError, match="Chave de API do Gemini não configurada"):
        AIService("").ask_financial_copilot("Como estou?", snapshot)

    bad = AIService("valid-key", transport=lambda *a: "nao-json")
    with pytest.raises(AIServiceError, match="Resposta da IA em formato inesperado"):
        bad.ask_financial_copilot("Como estou?", snapshot)


def test_ai_copilot_worker_success_and_failure() -> None:
    svc_ok = AIService(
        "test-key",
        transport=_fake_health_transport({"resposta": "Reserva atual dentro da meta de 20%."}),
    )
    worker_ok = AICopilotWorker(svc_ok, "Como está minha poupança?", {"periodo": "10/2026"})
    ok_res: list[str] = []
    ok_err: list[str] = []
    worker_ok.succeeded.connect(ok_res.append)
    worker_ok.failed.connect(ok_err.append)
    worker_ok.run()
    assert ok_res == ["Reserva atual dentro da meta de 20%."]
    assert ok_err == []

    worker_fail = AICopilotWorker(AIService(""), "Como está minha poupança?", {"periodo": "10/2026"})
    fail_res: list[str] = []
    fail_err: list[str] = []
    worker_fail.succeeded.connect(fail_res.append)
    worker_fail.failed.connect(fail_err.append)
    worker_fail.run()
    assert fail_res == []
    assert "Chave de API do Gemini não configurada" in fail_err[0]


def test_financial_health_report_to_dict_and_from_dict() -> None:
    original = FinancialHealthReport(
        score_saude=88,
        resumo="Saúde positiva.",
        essenciais_pct=42.5,
        estilo_vida_pct=22.5,
        poupanca_pct=35.0,
        comentario_regra="Tudo equilibrado.",
        alertas_anomalias=["Streaming subiu 15%."],
        projecao_fechamento="Fechamento positivo.",
        recomendacoes_praticas=["Aportar na reserva."],
    )
    cloned = FinancialHealthReport.from_dict(original.to_dict())
    assert cloned == original
