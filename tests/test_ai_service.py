"""Testes do AIService (sem rede, com transporte falso)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.config.app_settings import AppSettings
from app.domain.models import KIND_DESPESA, KIND_RECEITA
from app.domain.services.ai_service import AIContext, AIService, AIServiceError

CTX = AIContext(
    contas=["Itaú Corrente"],
    cartoes=["Nubank"],
    categorias_despesa=["Alimentação", "Saúde"],
    categorias_receita=["Salário"],
)
TODAY = date(2026, 10, 31)


def _fake(items):
    def transport(url, headers, body, timeout):
        assert "x-goog-api-key" in headers
        inner = json.dumps({"lancamentos": items})
        return json.dumps({"candidates": [{"content": {"parts": [{"text": inner}]}}]})

    return transport


def test_parse_batch_and_catalog_matching() -> None:
    svc = AIService(
        "k",
        transport=_fake(
            [
                {"tipo": "DESPESA", "descricao": "Almoço", "valor": 45.9, "data": "2026-10-31",
                 "cartao": "nubank", "conta": "Itaú Corrente", "categoria": "alimentação"},
                {"tipo": "RECEITA", "descricao": "Salário", "valor": 3500, "data": "2026-10-30",
                 "conta": "Inexistente", "categoria": "Salário"},
            ]
        ),
    )
    d = svc.parse_transactions("almoço 45,90 nubank e salário 3500", CTX, TODAY)
    assert [x.tipo for x in d] == [KIND_DESPESA, KIND_RECEITA]
    assert d[0].cartao == "Nubank" and d[0].conta is None and d[0].categoria == "Alimentação"
    assert d[1].conta is None and d[1].categoria == "Salário"
    assert d[1].data == date(2026, 10, 30)


def test_requires_api_key_and_text() -> None:
    with pytest.raises(AIServiceError):
        AIService("").parse_transactions("x", CTX, TODAY)
    with pytest.raises(AIServiceError):
        AIService("k").parse_transactions("  ", CTX, TODAY)


def test_invalid_response_and_empty_result() -> None:
    bad = AIService("k", transport=lambda *a: "não é json")
    with pytest.raises(AIServiceError):
        bad.parse_transactions("x", CTX, TODAY)
    with pytest.raises(AIServiceError):
        AIService("k", transport=_fake([{"tipo": "DESPESA", "descricao": "a", "valor": 0,
                                         "data": "2026-10-31"}])).parse_transactions("x", CTX, TODAY)


def test_key_store_resolution_and_no_leak_into_settings(tmp_path, monkeypatch) -> None:
    from app.config import gemini_key_store as ks

    monkeypatch.delenv(ks.ENV_VAR, raising=False)
    assert ks.resolve_gemini_key(tmp_path) == ("", ks.SOURCE_NONE)
    ks.save_gemini_key(tmp_path, "  chave-arquivo-123  ")
    assert ks.resolve_gemini_key(tmp_path) == ("chave-arquivo-123", ks.SOURCE_FILE)
    monkeypatch.setenv(ks.ENV_VAR, "chave-env")
    assert ks.resolve_gemini_key(tmp_path) == ("chave-env", ks.SOURCE_ENV)
    monkeypatch.delenv(ks.ENV_VAR)
    ks.clear_gemini_key(tmp_path)
    assert ks.resolve_gemini_key(tmp_path)[1] == ks.SOURCE_NONE
    assert "chave" not in ks.mask_key("chave-arquivo-123")

    s = AppSettings.load(tmp_path / "s.json")
    s.save()
    assert "api_key" not in (tmp_path / "s.json").read_text(encoding="utf-8")
