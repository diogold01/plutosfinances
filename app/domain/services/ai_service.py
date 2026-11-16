"""Serviço de IA (BYOK / Google Gemini) para interpretar lançamentos em linguagem natural.

Camada de serviço pura: não depende de Qt nem grava no banco. Recebe o contexto
(contas, cartões e categorias) e devolve DTOs de rascunho para confirmação do usuário.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_TIMEOUT_SECONDS = 20
SUPPORTED_ATTACHMENT_MIMES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "application/pdf"}
)


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

    tipo: str  # KIND_DESPESA | KIND_RECEITA | KIND_TRANSFERENCIA
    descricao: str
    valor: float
    data: date
    conta: Optional[str] = None
    cartao: Optional[str] = None
    categoria: Optional[str] = None
    efetivada: bool = True
    conta_destino: Optional[str] = None
    num_parcelas: int = 1
    valor_por_parcela: bool = False
    recorrente_mensal: bool = False


_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "lancamentos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "tipo": {
                        "type": "STRING",
                        "enum": ["DESPESA", "RECEITA", "TRANSFERENCIA"],
                    },
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
                    "conta_destino": {"type": "STRING", "nullable": True},
                    "cartao": {"type": "STRING", "nullable": True},
                    "categoria": {"type": "STRING", "nullable": True},
                    "efetivada": {"type": "BOOLEAN"},
                    "num_parcelas": {"type": "INTEGER", "nullable": True},
                    "valor_por_parcela": {"type": "BOOLEAN", "nullable": True},
                    "recorrente_mensal": {"type": "BOOLEAN", "nullable": True},
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score_saude": int(self.score_saude),
            "resumo": self.resumo,
            "regra_50_30_20": {
                "essenciais_pct": float(self.essenciais_pct),
                "estilo_vida_pct": float(self.estilo_vida_pct),
                "poupanca_pct": float(self.poupanca_pct),
                "comentario": self.comentario_regra,
            },
            "alertas_anomalias": list(self.alertas_anomalias),
            "projecao_fechamento": self.projecao_fechamento,
            "recomendacoes_praticas": list(self.recomendacoes_praticas),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FinancialHealthReport":
        rule = data.get("regra_50_30_20")
        if isinstance(rule, dict):
            ess = float(rule["essenciais_pct"])
            est = float(rule["estilo_vida_pct"])
            pou = float(rule["poupanca_pct"])
            com = str(rule.get("comentario", "")).strip()
        else:
            ess = float(data["essenciais_pct"])
            est = float(data["estilo_vida_pct"])
            pou = float(data["poupanca_pct"])
            com = str(data.get("comentario_regra", "")).strip()
        return cls(
            score_saude=max(0, min(100, int(data["score_saude"]))),
            resumo=str(data.get("resumo", "")).strip(),
            essenciais_pct=ess,
            estilo_vida_pct=est,
            poupanca_pct=pou,
            comentario_regra=com,
            alertas_anomalias=[
                str(a).strip() for a in data.get("alertas_anomalias", []) if str(a).strip()
            ],
            projecao_fechamento=str(data.get("projecao_fechamento", "")).strip(),
            recomendacoes_praticas=[
                str(r).strip() for r in data["recomendacoes_praticas"] if str(r).strip()
            ],
        )


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


_COPILOT_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "resposta": {
            "type": "STRING",
            "description": "Resposta direta, consultiva e baseada nos números do snapshot.",
        }
    },
    "required": ["resposta"],
}


@dataclass
class BatchCategorizationItem:
    """Item retornado pela categorização e higienização em lote pela IA."""

    descricao_original: str
    descricao_limpa: str
    categoria: Optional[str] = None
    eh_transferencia_propria: bool = False


_BATCH_CATEGORIZATION_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "itens": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "descricao_original": {"type": "STRING"},
                    "descricao_limpa": {"type": "STRING"},
                    "categoria": {"type": "STRING", "nullable": True},
                    "eh_transferencia_propria": {"type": "BOOLEAN", "nullable": True},
                },
                "required": ["descricao_original", "descricao_limpa"],
            },
        }
    },
    "required": ["itens"],
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
        self,
        text: str,
        context: AIContext,
        today: Optional[date] = None,
        *,
        attachment_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
    ) -> List[TransactionDraft]:
        """Converte `text` e/ou anexo multimodal em rascunhos (1 ou mais lançamentos)."""
        cleaned_text = (text or "").strip()
        if not cleaned_text and not attachment_bytes:
            raise AIServiceError("Digite o lançamento a ser interpretado.")

        inline_data: Optional[Dict[str, str]] = None
        if attachment_bytes:
            norm_mime = (mime_type or "").strip().lower()
            if norm_mime == "image/jpg":
                norm_mime = "image/jpeg"
            if norm_mime not in SUPPORTED_ATTACHMENT_MIMES:
                raise AIServiceError(
                    "Formato de anexo não suportado. Use PNG, JPG, WEBP ou PDF."
                )
            inline_data = {
                "mime_type": norm_mime,
                "data": base64.b64encode(attachment_bytes).decode("ascii"),
            }
            if not cleaned_text:
                cleaned_text = (
                    "Extraia todos os lançamentos financeiros visíveis neste "
                    "comprovante, cupom fiscal ou fatura."
                )

        today = today or date.today()
        raw = self._generate(
            self._build_prompt(cleaned_text, context, today),
            inline_data=inline_data,
        )
        return self._parse_response(raw, context, today, source_text=cleaned_text)

    def test_connection(self) -> bool:
        """Valida a chave com uma chamada mínima; levanta `AIServiceError` em falha."""
        self._generate("Responda apenas: ok", json_mode=False)
        return True

    # ------------------------------------------------------------- internals
    def _build_prompt(self, text: str, ctx: AIContext, today: date) -> str:
        return (
            "Você extrai lançamentos financeiros de um texto ou documento (comprovante, cupom, fatura) em português do Brasil.\n"
            f"Data de hoje: {today.isoformat()}. Resolva 'hoje', 'ontem', 'anteontem' etc. a partir dela.\n"
            "Regras:\n"
            "- Um texto ou documento pode conter vários lançamentos; retorne um item para cada.\n"
            "- tipo: DESPESA (gastos, compras, contas pagas), RECEITA (salário, recebimentos) ou TRANSFERENCIA (movimentação entre contas próprias, ex.: 'transferi 500 do Nubank para o Itaú').\n"
            "- valor sempre positivo, em número (ex.: 1234.56).\n"
            "- Parcelamento: se houver parcelas (ex.: 'em 10x', '10x de 150', '3/12'), preencha num_parcelas (inteiro >= 1). "
            "Use valor_por_parcela=true quando o texto informar o valor de cada parcela (ex.: '10x de 150') e false quando informar o valor total (ex.: '1500 em 10x').\n"
            "- Recorrência fixa mensal: preencha recorrente_mensal=true quando for conta/receita fixa todo mês (ex.: 'todo mês', 'mensalidade fixa', 'todo dia 5').\n"
            "- Para TRANSFERENCIA: 'conta' é a conta de origem, 'conta_destino' é a conta de destino (ambas da lista Contas), deixe 'cartao' e 'categoria' null, e num_parcelas=1.\n"
            "- descricao: Formate com elegância e padrão legível com iniciais maiúsculas "
            "(Title Case em nomes de lojas, marcas e pessoas, ex.: 'Uber', 'Farmácia Nathaly', 'Mercado Unigran', 'Padaria Central').\n"
            "- Higienize a descrição: corrija erros óbvios de digitação ou grafia informal do usuário "
            "(ex.: 'farmarcia' -> 'Farmácia', 'ubr' -> 'Uber', 'salgado nathaly' -> 'Salgado Nathaly'). "
            "Remova termos operacionais redundantes que indicam apenas a transação "
            "(como 'saída', 'entrada', 'despesa', 'gasto', 'valor de', 'compras de', 'pago').\n"
            "- 'conta', 'conta_destino', 'cartao' e 'categoria' DEVEM ser exatamente um nome das listas abaixo; "
            "se nada corresponder com clareza, use null. Nunca invente nomes.\n"
            "- Se mencionar cartão de crédito (mesmo sem citar o nome do banco), preencha 'cartao' "
            "com o cartão correspondente ou o primeiro da lista Cartões, e deixe 'conta' null.\n"
            "- efetivada=true se já foi pago/recebido/transferido; false se for futuro/agendado.\n"
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
            "comparado à média dos 2 meses anteriores, além de projeção de caixa 30/60/90d, "
            "orçamentos em risco, faturas futuras de cartões e objetivos quando presentes) e responda em português do Brasil.\n"
            "Regras:\n"
            "- score_saude: inteiro 0-100 considerando poupança (meta 20%), essenciais (meta 50%), "
            "estilo de vida (meta 30%), resultado líquido, risco de orçamentos e estabilidade vs. meses anteriores.\n"
            "- regra_50_30_20: use os percentuais reais fornecidos (não recalcule) e escreva em "
            "'comentario' um diagnóstico curto de cada faixa.\n"
            "- alertas_anomalias: apenas categorias com variação relevante (acima de ~20% vs. média), "
            "orçamentos em alerta/estouro ou pressão de faturas futuras; cite categoria, variação e impacto em R$. "
            "Lista vazia se não houver.\n"
            "- projecao_fechamento: resumo de 1-3 frases sobre o fechamento do mês, o ritmo de gastos "
            "(burn rate) e a trajetória de caixa para 30/60/90 dias com base nos dados; não invente valores ausentes.\n"
            "- recomendacoes_praticas: 3 a 4 ações concretas, mensuráveis e priorizadas, "
            "citando categorias, faturas, orçamentos ou metas e valores-alvo quando possível.\n"
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
            if not isinstance(data.get("regra_50_30_20"), dict):
                raise KeyError("regra_50_30_20")
            report = FinancialHealthReport.from_dict(data)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("Resposta da IA em formato inesperado.") from exc
        if not report.recomendacoes_praticas:
            raise AIServiceError("A IA não retornou recomendações.")
        return report

    def ask_financial_copilot(
        self,
        question: str,
        financial_snapshot: Dict[str, Any],
    ) -> str:
        """Responde uma pergunta do usuário usando apenas métricas agregadas (somente leitura)."""
        cleaned_q = (question or "").strip()
        if not cleaned_q:
            raise AIServiceError("Digite uma pergunta para o Copiloto.")
        if not financial_snapshot:
            raise AIServiceError("Sem dados financeiros para analisar.")
        raw = self._generate(
            self._build_copilot_prompt(cleaned_q, financial_snapshot),
            schema=_COPILOT_RESPONSE_SCHEMA,
            temperature=0.2,
        )
        try:
            envelope = json.loads(raw)
            text = envelope["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(text)
            answer = str(data["resposta"]).strip()
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("Resposta da IA em formato inesperado.") from exc
        if not answer:
            raise AIServiceError("Resposta da IA em formato inesperado.")
        return answer

    @staticmethod
    def _build_copilot_prompt(question: str, financial_snapshot: Dict[str, Any]) -> str:
        return (
            "Você é o Copiloto Financeiro do Plutos, consultivo e objetivo, em português do Brasil.\n"
            "Responda à pergunta do usuário com base EXCLUSIVA nos números agregados do snapshot abaixo "
            "(nunca invente valores, nunca recomende produtos financeiros ou investimentos específicos e nunca altere dados).\n"
            "Formato: responda em 2 a 5 frases diretas, citando valores em R$ e percentuais reais do snapshot.\n"
            f"Pergunta do usuário: {question}\n"
            f"Snapshot financeiro: {json.dumps(financial_snapshot, ensure_ascii=False)}"
        )

    def categorize_descriptions_batch(
        self,
        items: List[Tuple[str, str]],
        context: AIContext,
    ) -> Dict[Tuple[str, str], BatchCategorizationItem]:
        """Higieniza e categoriza em uma única requisição descrições inéditas de extratos."""
        unique_pairs: List[Tuple[str, str]] = []
        seen_keys: set[Tuple[str, str]] = set()
        for raw_desc, raw_tipo in items:
            desc = (raw_desc or "").strip()
            if not desc:
                continue
            tipo = KIND_RECEITA if str(raw_tipo or "").upper() == KIND_RECEITA else KIND_DESPESA
            key = (desc.casefold(), tipo)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_pairs.append((desc, tipo))
            if len(unique_pairs) >= 80:
                break

        if not unique_pairs:
            return {}

        payload_items = [
            {"descricao_original": desc, "tipo": tipo} for desc, tipo in unique_pairs
        ]
        prompt = (
            "Você higieniza e categoriza lançamentos de extratos bancários brasileiros.\n"
            "Regras:\n"
            "- Para cada item da lista, devolva 'descricao_original' idêntica à entrada.\n"
            "- 'descricao_limpa': padronize em Title Case legível removendo prefixos e códigos "
            "bancários/adquirentes (ex.: 'PAG*', 'MP*', 'IFD*', 'PIX TRANSF', CNPJs e números de terminal).\n"
            "- 'categoria': escolha EXATAMENTE um nome da lista correspondente ao 'tipo' "
            "(Categorias de despesa ou Categorias de receita); se não houver correspondência clara, use null.\n"
            "- 'eh_transferencia_propria': true apenas se indicar transferência entre contas próprias, "
            "aplicação/resgate interno ou pagamento de fatura do próprio titular; caso contrário false.\n"
            f"Categorias de despesa: {json.dumps(context.categorias_despesa, ensure_ascii=False)}\n"
            f"Categorias de receita: {json.dumps(context.categorias_receita, ensure_ascii=False)}\n"
            f"Itens: {json.dumps(payload_items, ensure_ascii=False)}"
        )

        raw = self._generate(
            prompt,
            schema=_BATCH_CATEGORIZATION_SCHEMA,
            temperature=0,
        )
        try:
            envelope = json.loads(raw)
            text = envelope["candidates"][0]["content"]["parts"][0]["text"]
            parsed_items = json.loads(text)["itens"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("Resposta da IA em formato inesperado.") from exc

        orig_by_key = {(desc.casefold(), tipo): desc for desc, tipo in unique_pairs}
        result: Dict[Tuple[str, str], BatchCategorizationItem] = {}

        for it in parsed_items:
            if not isinstance(it, dict):
                continue
            orig = str(it.get("descricao_original") or "").strip()
            if not orig:
                continue
            orig_low = orig.casefold()
            # Tenta casar pelo par exato ou pelo único tipo daquela descrição
            matched_keys = [k for k in orig_by_key if k[0] == orig_low]
            if not matched_keys:
                continue
            for key in matched_keys:
                tipo = key[1]
                cats = (
                    context.categorias_receita
                    if tipo == KIND_RECEITA
                    else context.categorias_despesa
                )
                clean_desc = format_clean_description(
                    str(it.get("descricao_limpa") or orig_by_key[key])
                )
                matched_cat = self._match(it.get("categoria"), cats)
                is_self_tr = bool(it.get("eh_transferencia_propria") or False)
                result[key] = BatchCategorizationItem(
                    descricao_original=orig_by_key[key],
                    descricao_limpa=clean_desc,
                    categoria=matched_cat,
                    eh_transferencia_propria=is_self_tr,
                )

        return result

    def _generate(
        self,
        prompt: str,
        json_mode: bool = True,
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0,
        inline_data: Optional[Dict[str, str]] = None,
    ) -> str:
        if not self.is_configured:
            raise AIServiceError("Chave de API do Gemini não configurada.")
        parts: List[Dict[str, Any]] = [{"text": prompt}]
        if inline_data:
            parts.append({"inline_data": inline_data})
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
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
                tipo_raw = str(it["tipo"]).upper()
                if tipo_raw == KIND_TRANSFERENCIA:
                    tipo = KIND_TRANSFERENCIA
                elif tipo_raw == KIND_RECEITA:
                    tipo = KIND_RECEITA
                else:
                    tipo = KIND_DESPESA

                valor = abs(float(it["valor"]))
                if valor <= 0:
                    continue
                try:
                    when = date.fromisoformat(str(it.get("data", "")))
                except ValueError:
                    when = today

                if tipo == KIND_TRANSFERENCIA:
                    conta = self._match(it.get("conta"), ctx.contas)
                    conta_destino = self._match(it.get("conta_destino"), ctx.contas)
                    cartao = None
                    categoria = None
                    num_parcelas = 1
                    valor_por_parcela = False
                    recorrente_mensal = False
                    efetivada = bool(it.get("efetivada", True))
                else:
                    cats = (
                        ctx.categorias_receita
                        if tipo == KIND_RECEITA
                        else ctx.categorias_despesa
                    )
                    cartao = (
                        self._match(it.get("cartao"), ctx.cartoes)
                        if tipo == KIND_DESPESA
                        else None
                    )
                    conta = None if cartao else self._match(it.get("conta"), ctx.contas)
                    conta_destino = None
                    if (
                        tipo == KIND_DESPESA
                        and cartao is None
                        and conta is None
                        and ctx.cartoes
                        and mentions_generic_card
                    ):
                        cartao = ctx.cartoes[0]
                    categoria = self._match(it.get("categoria"), cats)
                    raw_parcs = it.get("num_parcelas")
                    num_parcelas = max(1, int(raw_parcs)) if raw_parcs else 1
                    recorrente_mensal = bool(it.get("recorrente_mensal") or False)
                    if recorrente_mensal:
                        num_parcelas = 1
                    valor_por_parcela = (
                        bool(it.get("valor_por_parcela") or False)
                        if num_parcelas > 1
                        else False
                    )
                    efetivada = bool(it.get("efetivada", True)) if not cartao else False

                drafts.append(
                    TransactionDraft(
                        tipo=tipo,
                        descricao=format_clean_description(str(it.get("descricao", ""))),
                        valor=round(valor, 2),
                        data=when,
                        conta=conta,
                        cartao=cartao,
                        categoria=categoria,
                        efetivada=efetivada,
                        conta_destino=conta_destino,
                        num_parcelas=num_parcelas,
                        valor_por_parcela=valor_por_parcela,
                        recorrente_mensal=recorrente_mensal,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if not drafts:
            raise AIServiceError("Nenhum lançamento identificado no texto.")
        return drafts
