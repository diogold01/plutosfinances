"""Serviço de IA (BYOK / Google Gemini) para interpretar lançamentos em linguagem natural.

Camada de serviço pura: não depende de Qt nem grava no banco. Recebe o contexto
(contas, cartões e categorias) e devolve DTOs de rascunho para confirmação do usuário.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional

from app.domain.models import KIND_DESPESA, KIND_RECEITA

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_TIMEOUT_SECONDS = 20


class AIServiceError(Exception):
    """Erro amigável de configuração, rede ou interpretação da resposta da IA."""


@dataclass
class AIContext:
    """Catálogo local enviado à IA para evitar contas/categorias inexistentes."""

    contas: List[str] = field(default_factory=list)
    cartoes: List[str] = field(default_factory=list)
    categorias_despesa: List[str] = field(default_factory=list)
    categorias_receita: List[str] = field(default_factory=list)


@dataclass
class TransactionDraft:
    """Rascunho de lançamento sugerido pela IA (ainda não persistido)."""

    tipo: str  # KIND_DESPESA | KIND_RECEITA
    descricao: str
    valor: float
    data: date
    conta: Optional[str] = None
    cartao: Optional[str] = None
    categoria: Optional[str] = None
    efetivada: bool = True


_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "lancamentos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "tipo": {"type": "STRING", "enum": ["DESPESA", "RECEITA"]},
                    "descricao": {
                        "type": "STRING",
                        "description": (
                            "Descrição clara, elegante e padronizada com iniciais maiúsculas "
                            "(Title Case, ex.: 'Uber', 'Farmácia Nathaly', 'Mercado Unigran'), "
                            "corrigindo erros de digitação e sem redundâncias como 'saída' ou 'despesa'."
                        ),
                    },
                    "valor": {"type": "NUMBER"},
                    "data": {"type": "STRING", "description": "YYYY-MM-DD"},
                    "conta": {"type": "STRING", "nullable": True},
                    "cartao": {"type": "STRING", "nullable": True},
                    "categoria": {"type": "STRING", "nullable": True},
                    "efetivada": {"type": "BOOLEAN"},
                },
                "required": ["tipo", "descricao", "valor", "data"],
            },
        }
    },
    "required": ["lancamentos"],
}

@dataclass
class FinancialHealthReport:
    """Diagnóstico de saúde financeira devolvido pela IA (somente leitura)."""

    score_saude: int  # 0-100
    resumo: str
    essenciais_pct: float
    estilo_vida_pct: float
    poupanca_pct: float
    comentario_regra: str
    alertas_anomalias: List[str]
    projecao_fechamento: str
    recomendacoes_praticas: List[str]


_HEALTH_REPORT_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "score_saude": {"type": "INTEGER", "description": "Nota de saúde financeira de 0 a 100."},
        "resumo": {"type": "STRING", "description": "Resumo geral em 1-2 frases."},
        "regra_50_30_20": {
            "type": "OBJECT",
            "properties": {
                "essenciais_pct": {"type": "NUMBER"},
                "estilo_vida_pct": {"type": "NUMBER"},
                "poupanca_pct": {"type": "NUMBER"},
                "comentario": {"type": "STRING"},
            },
            "required": ["essenciais_pct", "estilo_vida_pct", "poupanca_pct", "comentario"],
        },
        "alertas_anomalias": {"type": "ARRAY", "items": {"type": "STRING"}},
        "projecao_fechamento": {"type": "STRING"},
        "recomendacoes_praticas": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "3 a 4 ações práticas e mensuráveis.",
        },
    },
    "required": [
        "score_saude",
        "resumo",
        "regra_50_30_20",
        "alertas_anomalias",
        "projecao_fechamento",
        "recomendacoes_praticas",
    ],
}

# Transporte injetável (facilita testes sem rede): (url, headers, body) -> texto JSON
Transport = Callable[[str, Dict[str, str], bytes, int], str]


def _http_transport(url: str, headers: Dict[str, str], body: bytes, timeout: int) -> str:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise AIServiceError("Chave de API inválida ou sem permissão.") from exc
        if exc.code == 404:
            raise AIServiceError("Modelo não encontrado na API (HTTP 404). Selecione 'gemini-1.5-flash'.") from exc
        if exc.code == 429:
            raise AIServiceError("Limite de requisições da API atingido. Tente em instantes.") from exc
        raise AIServiceError(f"Erro da API Gemini (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIServiceError("Sem conexão com a internet ou API indisponível.") from exc


def format_clean_description(text: str) -> str:
    """Padroniza e embeleza a descrição garantindo Title Case e corrigindo caixas extremas."""
    cleaned = (text or "").strip()
    if not cleaned:
        return "Lançamento"

    # Se a string veio totalmente em minúsculas ou totalmente em maiúsculas (e não é sigla curta como PIX ou IOF)
    if cleaned.islower() or (cleaned.isupper() and len(cleaned) > 4):
        words = cleaned.split()
        low_words = {"de", "da", "do", "das", "dos", "e", "em", "para", "com", "no", "na", "nos", "nas"}
        parts: List[str] = []
        for i, w in enumerate(words):
            wl = w.lower()
            if i > 0 and wl in low_words:
                parts.append(wl)
            else:
                parts.append(w.capitalize())
        cleaned = " ".join(parts)
    return cleaned


class AIService:
    """Interpreta texto livre em lançamentos usando Gemini com saída JSON estruturada."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        transport: Optional[Transport] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model = (model or "gemini-3.5-flash-lite").strip()
        self._transport = transport or _http_transport
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    # ------------------------------------------------------------------ API
    def parse_transactions(
        self, text: str, context: AIContext, today: Optional[date] = None
    ) -> List[TransactionDraft]:
        """Converte `text` em uma lista de rascunhos (1 ou mais lançamentos)."""
        if not text or not text.strip():
            raise AIServiceError("Digite o lançamento a ser interpretado.")
        today = today or date.today()
        raw = self._generate(self._build_prompt(text.strip(), context, today))
        return self._parse_response(raw, context, today, source_text=text)

    def test_connection(self) -> bool:
        """Valida a chave com uma chamada mínima; levanta `AIServiceError` em falha."""
        self._generate("Responda apenas: ok", json_mode=False)
        return True

    # ------------------------------------------------------------- internals
    def _build_prompt(self, text: str, ctx: AIContext, today: date) -> str:
        return (
            "Você extrai lançamentos financeiros de um texto em português do Brasil.\n"
            f"Data de hoje: {today.isoformat()}. Resolva 'hoje', 'ontem', 'anteontem' etc. a partir dela.\n"
            "Regras:\n"
            "- Um texto pode conter vários lançamentos; retorne um item para cada.\n"
            "- tipo: DESPESA (gastos, compras, contas pagas) ou RECEITA (salário, recebimentos).\n"
            "- valor sempre positivo, em número (ex.: 1234.56).\n"
            "- descricao: Formate com elegância e padrão legível com iniciais maiúsculas "
            "(Title Case em nomes de lojas, marcas e pessoas, ex.: 'Uber', 'Farmácia Nathaly', 'Mercado Unigran', 'Padaria Central').\n"
            "- Higienize a descrição: corrija erros óbvios de digitação ou grafia informal do usuário "
            "(ex.: 'farmarcia' -> 'Farmácia', 'ubr' -> 'Uber', 'salgado nathaly' -> 'Salgado Nathaly'). "
            "Remova termos operacionais redundantes que indicam apenas a transação "
            "(como 'saída', 'entrada', 'despesa', 'gasto', 'valor de', 'compras de', 'pago').\n"
            "- 'conta', 'cartao' e 'categoria' DEVEM ser exatamente um nome das listas abaixo; "
            "se nada corresponder com clareza, use null. Nunca invente nomes.\n"
            "- Se mencionar cartão de crédito (mesmo sem citar o nome do banco), preencha 'cartao' "
            "com o cartão correspondente ou o primeiro da lista Cartões, e deixe 'conta' null.\n"
            "- efetivada=true se já foi pago/recebido; false se for futuro/agendado.\n"
            f"Contas: {json.dumps(ctx.contas, ensure_ascii=False)}\n"
            f"Cartões: {json.dumps(ctx.cartoes, ensure_ascii=False)}\n"
            f"Categorias de despesa: {json.dumps(ctx.categorias_despesa, ensure_ascii=False)}\n"
            f"Categorias de receita: {json.dumps(ctx.categorias_receita, ensure_ascii=False)}\n"
            f"Texto: {text}"
        )

    def generate_financial_health_report(
        self, summary_payload: Dict[str, Any]
    ) -> FinancialHealthReport:
        """Gera o diagnóstico de saúde financeira a partir do payload anonimizado."""
        if not summary_payload:
            raise AIServiceError("Sem dados financeiros para analisar.")
        raw = self._generate(
            self._build_health_prompt(summary_payload),
            schema=_HEALTH_REPORT_SCHEMA,
            temperature=0.3,
        )
        return self._parse_health_response(raw)

    @staticmethod
    def _build_health_prompt(payload: Dict[str, Any]) -> str:
        return (
            "Você é um consultor de finanças pessoais brasileiro, objetivo e consultivo.\n"
            "Analise APENAS os dados agregados e anonimizados abaixo (valores em R$, mês ativo "
            "comparado à média dos 2 meses anteriores) e responda em português do Brasil.\n"
            "Regras:\n"
            "- score_saude: inteiro 0-100 considerando poupança (meta 20%), essenciais (meta 50%), "
            "estilo de vida (meta 30%), resultado líquido e estabilidade vs. meses anteriores.\n"
            "- regra_50_30_20: use os percentuais reais fornecidos (não recalcule) e escreva em "
            "'comentario' um diagnóstico curto de cada faixa.\n"
            "- alertas_anomalias: apenas categorias com variação relevante (acima de ~20% vs. média) "
            "ou participação desproporcional; cite categoria, variação e impacto em R$. "
            "Lista vazia se não houver.\n"
            "- projecao_fechamento: resumo de 1-3 frases sobre o fechamento do mês e o ritmo de gastos "
            "(burn rate) com base nos dados; não invente valores ausentes.\n"
            "- recomendacoes_praticas: 3 a 4 ações concretas, mensuráveis e priorizadas, "
            "citando categorias e valores-alvo quando possível.\n"
            "- Não invente dados, nomes, bancos ou instituições; não dê recomendação de produto específico.\n"
            "- Tom direto, sem jargão, sem julgamento.\n"
            f"Dados: {json.dumps(payload, ensure_ascii=False)}"
        )

    @staticmethod
    def _parse_health_response(raw: str) -> FinancialHealthReport:
        try:
            envelope = json.loads(raw)
            text = envelope["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
            rule = data["regra_50_30_20"]
            report = FinancialHealthReport(
                score_saude=max(0, min(100, int(data["score_saude"]))),
                resumo=str(data.get("resumo", "")).strip(),
                essenciais_pct=float(rule["essenciais_pct"]),
                estilo_vida_pct=float(rule["estilo_vida_pct"]),
                poupanca_pct=float(rule["poupanca_pct"]),
                comentario_regra=str(rule.get("comentario", "")).strip(),
                alertas_anomalias=[
                    str(a).strip() for a in data.get("alertas_anomalias", []) if str(a).strip()
                ],
                projecao_fechamento=str(data.get("projecao_fechamento", "")).strip(),
                recomendacoes_praticas=[
                    str(r).strip() for r in data["recomendacoes_praticas"] if str(r).strip()
                ],
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("Resposta da IA em formato inesperado.") from exc
        if not report.recomendacoes_praticas:
            raise AIServiceError("A IA não retornou recomendações.")
        return report

    def _generate(
        self,
        prompt: str,
        json_mode: bool = True,
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0,
    ) -> str:
        if not self.is_configured:
            raise AIServiceError("Chave de API do Gemini não configurada.")
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if json_mode:
            payload["generationConfig"].update(
                {
                    "responseMimeType": "application/json",
                    "responseSchema": schema or _RESPONSE_SCHEMA,
                }
            )
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        body = json.dumps(payload).encode("utf-8")
        return self._transport(
            GEMINI_ENDPOINT.format(model=self.model), headers, body, self.timeout
        )

    @staticmethod
    def _match(value: Any, options: List[str]) -> Optional[str]:
        """Casa o nome retornado com o catálogo local (case/acento-insensível simples)."""
        if not value or not isinstance(value, str):
            return None
        wanted = value.strip().casefold()
        for opt in options:
            if opt.casefold() == wanted:
                return opt
        return None

    def _parse_response(
        self, raw: str, ctx: AIContext, today: date, source_text: str = ""
    ) -> List[TransactionDraft]:
        try:
            envelope = json.loads(raw)
            text = envelope["candidates"][0]["content"]["parts"][0]["text"]
            items = json.loads(text)["lancamentos"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("Resposta da IA em formato inesperado.") from exc

        src_low = source_text.casefold()
        mentions_generic_card = any(
            kw in src_low for kw in ("cartao", "cartão", "no credito", "no crédito")
        )
        drafts: List[TransactionDraft] = []
        for it in items:
            try:
                tipo = KIND_RECEITA if str(it["tipo"]).upper() == KIND_RECEITA else KIND_DESPESA
                valor = abs(float(it["valor"]))
                if valor <= 0:
                    continue
                try:
                    when = date.fromisoformat(str(it.get("data", "")))
                except ValueError:
                    when = today
                cats = ctx.categorias_receita if tipo == KIND_RECEITA else ctx.categorias_despesa
                cartao = self._match(it.get("cartao"), ctx.cartoes) if tipo == KIND_DESPESA else None
                conta = None if cartao else self._match(it.get("conta"), ctx.contas)
                if (
                    tipo == KIND_DESPESA
                    and cartao is None
                    and conta is None
                    and ctx.cartoes
                    and mentions_generic_card
                ):
                    cartao = ctx.cartoes[0]
                drafts.append(
                    TransactionDraft(
                        tipo=tipo,
                        descricao=format_clean_description(str(it.get("descricao", ""))),
                        valor=round(valor, 2),
                        data=when,
                        conta=conta,
                        cartao=cartao,
                        categoria=self._match(it.get("categoria"), cats),
                        efetivada=bool(it.get("efetivada", True)) if not cartao else False,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not drafts:
            raise AIServiceError("Nenhum lançamento identificado no texto.")
        return drafts
