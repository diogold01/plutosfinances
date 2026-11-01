"""Módulo de configuração e cliente de autenticação e Open Finance Pluggy (BYOK).

Responsável por:
1. Armazenar com segurança local as credenciais (clientId e clientSecret) e itens conectados em `dados_usuario/pluggy_config.local`.
2. Validar credenciais contra `POST https://api.pluggy.ai/auth`.
3. Criar Connect Tokens para o widget Pluggy Connect via `POST https://api.pluggy.ai/connect_token`.
4. Listar, consultar e remover conexões bancárias via `GET /items`, `GET /items/{id}` e `DELETE /items/{id}`.
5. Buscar Contas (`GET /accounts`), Investimentos (`GET /investments`) e Transações (`GET /transactions`).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLUGGY_BASE_URL = "https://api.pluggy.ai"
PLUGGY_CONNECT_URL = "https://connect.pluggy.ai"
DEFAULT_TIMEOUT_SECONDS = 15


@dataclass
class PluggyConnectedItem:
    """Representação local de uma instituição bancária conectada via Pluggy."""

    item_id: str
    connector_id: Optional[int] = None
    connector_name: str = ""
    connector_image_url: str = ""
    status: str = "UPDATED"
    execution_status: str = "SUCCESS"
    last_updated_at: str = ""

    @classmethod
    def from_api_item(cls, data: Dict[str, Any]) -> "PluggyConnectedItem":
        item_id = str(data.get("id") or "")
        connector = data.get("connector") or {}
        return cls(
            item_id=item_id,
            connector_id=connector.get("id"),
            connector_name=connector.get("name") or "Instituição Financeira",
            connector_image_url=connector.get("imageUrl") or "",
            status=data.get("status") or "UPDATED",
            execution_status=data.get("executionStatus") or "SUCCESS",
            last_updated_at=data.get("lastUpdatedAt") or data.get("updatedAt") or "",
        )


@dataclass
class PluggyConfig:
    """Configurações persistidas em `dados_usuario/pluggy_config.local`."""

    client_id: str = ""
    client_secret: str = ""
    items: List[PluggyConnectedItem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluggyConfig":
        items_raw = data.get("items", [])
        items = [
            PluggyConnectedItem(**it) if isinstance(it, dict) else it
            for it in items_raw
        ]
        return cls(
            client_id=str(data.get("client_id", "") or "").strip(),
            client_secret=str(data.get("client_secret", "") or "").strip(),
            items=items,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "items": [asdict(it) for it in self.items],
        }

    def upsert_item(self, item: PluggyConnectedItem) -> None:
        """Adiciona ou atualiza uma instituição bancária na lista."""
        for idx, existing in enumerate(self.items):
            if existing.item_id == item.item_id:
                self.items[idx] = item
                return
        self.items.append(item)

    def remove_item(self, item_id: str) -> bool:
        """Remove um item por seu ID local."""
        initial_len = len(self.items)
        self.items = [it for it in self.items if it.item_id != item_id]
        return len(self.items) < initial_len


class PluggyConfigManager:
    """Gerencia a leitura e escrita do arquivo local de credenciais Pluggy."""

    def __init__(self, user_data_dir: Union[Path, str]) -> None:
        self.user_data_dir = Path(user_data_dir)
        self.config_path = self.user_data_dir / "pluggy_config.local"

    def load_config(self) -> PluggyConfig:
        if not self.config_path.exists():
            return PluggyConfig()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return PluggyConfig.from_dict(data)
        except Exception:
            return PluggyConfig()

    def save_config(self, config: PluggyConfig) -> None:
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.config_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
        temp_path.replace(self.config_path)


class PluggyClient:
    """Cliente HTTP puro para interagir com a API da Pluggy."""

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        base_url: str = PLUGGY_BASE_URL,
        connect_base_url: str = PLUGGY_CONNECT_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.base_url = base_url.rstrip("/")
        self.connect_base_url = connect_base_url.rstrip("/")
        self.timeout = timeout
        self._api_key: Optional[str] = None

    def _ensure_api_key(self) -> str:
        """Retorna o apiKey em cache ou realiza autenticação se necessário."""
        if not self._api_key:
            return self.authenticate()
        return self._api_key

    def authenticate(self, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> str:
        """Autentica na Pluggy e retorna o apiKey temporário."""
        cid = (client_id if client_id is not None else self.client_id).strip()
        sec = (client_secret if client_secret is not None else self.client_secret).strip()

        if not cid or not sec:
            raise ValueError("Client ID e Client Secret são obrigatórios para autenticação.")

        url = f"{self.base_url}/auth"
        payload = json.dumps({"clientId": cid, "clientSecret": sec}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Plutos-Personal-Finance/1.1",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                data = json.loads(body)
                api_key = data.get("apiKey")
                if not api_key:
                    raise ValueError("Resposta da Pluggy não continha o 'apiKey'.")
                self._api_key = api_key
                self.client_id = cid
                self.client_secret = sec
                return api_key
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            if exc.code in (401, 403):
                raise ValueError("Credenciais inválidas. Verifique seu Client ID e Client Secret.") from exc
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("message", f"Erro HTTP {exc.code}")
            except Exception:
                msg = f"Erro HTTP {exc.code}: {exc.reason}"
            raise ValueError(f"Falha na autenticação da Pluggy: {msg}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"Não foi possível conectar à Pluggy: {exc.reason}") from exc
        except Exception as exc:
            raise RuntimeError(f"Erro inesperado ao conectar à Pluggy: {exc}") from exc

    def test_connection(
        self, client_id: Optional[str] = None, client_secret: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Testa as credenciais informadas retornando (sucesso, mensagem_amigável)."""
        try:
            self.authenticate(client_id, client_secret)
            return True, "Conexão com a Pluggy estabelecida com sucesso!"
        except Exception as exc:
            return False, str(exc)

    def _send_request(
        self,
        endpoint_or_url: str,
        method: str = "GET",
        payload_dict: Optional[Dict[str, Any]] = None,
        use_api_key: bool = True,
    ) -> Dict[str, Any]:
        """Executa uma requisição HTTP com renovação automática do apiKey em caso de 401."""
        url = (
            endpoint_or_url
            if endpoint_or_url.startswith("http")
            else f"{self.base_url}/{endpoint_or_url.lstrip('/')}"
        )

        for attempt in range(2):
            headers = {
                "Accept": "application/json",
                "User-Agent": "Plutos-Personal-Finance/1.1",
            }
            if use_api_key:
                headers["X-API-KEY"] = self._ensure_api_key()

            data_bytes = None
            if payload_dict is not None:
                headers["Content-Type"] = "application/json"
                data_bytes = json.dumps(payload_dict).encode("utf-8")

            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
                    if not body or not str(body).strip():
                        return {}
                    return json.loads(str(body))
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403) and use_api_key and attempt == 0:
                    # Token expirado: força reautenticação e tenta uma segunda vez
                    self._api_key = None
                    self.authenticate()
                    continue
                err_body = exc.read().decode("utf-8", errors="ignore")
                try:
                    err_json = json.loads(err_body)
                    msg = err_json.get("message", f"HTTP {exc.code}")
                except Exception:
                    msg = f"HTTP {exc.code}: {exc.reason}"
                raise RuntimeError(f"Erro na API Pluggy ({url}): {msg}") from exc
            except urllib.error.URLError as exc:
                raise ConnectionError(f"Não foi possível conectar à Pluggy: {exc.reason}") from exc

        return {}

    def create_connect_token(self, item_id: Optional[str] = None) -> Tuple[str, str]:
        """
        Cria um token temporário de conexão do Pluggy Connect Widget.
        Retorna uma tupla (accessToken, connectWidgetUrl).
        """
        options: Dict[str, Any] = {"avoidDuplicates": True}
        if item_id:
            options["itemId"] = item_id

        data = self._send_request(
            "connect_token",
            method="POST",
            payload_dict={"options": options},
            use_api_key=True,
        )
        token = data.get("accessToken")
        if not token:
            raise ValueError("Resposta do connect_token não continha o 'accessToken'.")
        widget_url = f"{self.connect_base_url}/?connectToken={token}"
        return token, widget_url

    def generate_connect_html(self, user_data_dir: Path, item_id: Optional[str] = None) -> Path:
        """
        Gera uma página HTML local configurada com o SDK oficial do Pluggy Connect.
        Garante inicialização sem erros e exibe o ID da conexão imediatamente na tela
        com botão de cópia automática ao concluir a autenticação com sucesso.
        """
        token, _ = self.create_connect_token(item_id=item_id)
        user_data_dir.mkdir(parents=True, exist_ok=True)
        html_file = user_data_dir / "pluggy_connect.html"

        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Plutos - Conectar Instituição Bancária (Pluggy)</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 24px;
      box-sizing: border-box;
    }}
    .card {{
      background: #1e293b;
      padding: 36px 32px;
      border-radius: 16px;
      border: 1px solid #334155;
      max-width: 500px;
      width: 100%;
      text-align: center;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    }}
    h2 {{ margin-top: 0; color: #38bdf8; font-size: 22px; }}
    p {{ color: #94a3b8; font-size: 15px; line-height: 1.5; margin: 12px 0 20px 0; }}
    .btn {{
      background: #2563eb;
      color: white;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 15px;
      cursor: pointer;
      transition: background 0.2s, transform 0.1s;
    }}
    .btn:hover {{ background: #1d4ed8; }}
    .btn:active {{ transform: scale(0.98); }}
    .id-box {{
      background: #0f172a;
      border: 1px dashed #38bdf8;
      padding: 14px;
      border-radius: 8px;
      font-family: monospace;
      font-size: 16px;
      color: #38bdf8;
      margin: 18px 0;
      word-break: break-all;
      user-select: all;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      background: #064e3b;
      color: #34d399;
      margin-bottom: 12px;
    }}
  </style>
  <script src="https://cdn.pluggy.ai/pluggy-connect/latest/pluggy-connect.js"></script>
</head>
<body>
  <div class="card" id="box-init">
    <h2>Plutos &bull; Open Finance</h2>
    <p>O assistente oficial da Pluggy será aberto para você escolher e conectar sua conta bancária:</p>
    <button class="btn" id="btn-open">Abrir Conector de Bancos</button>
  </div>

  <div class="card" id="box-success" style="display: none;">
    <div class="badge">&#10003; CONEXÃO AUTORIZADA</div>
    <h2 style="color: #34d399;">Banco Conectado com Sucesso!</h2>
    <p>Copie o <b>ID da Conexão</b> abaixo e cole no Plutos no botão <b>"+ Adicionar por ID"</b>:</p>
    <div class="id-box" id="txt-item-id"></div>
    <button class="btn" id="btn-copy">Copiar ID da Conexão</button>
    <p style="margin-top: 16px; font-size: 13px; color: #64748b;">(Você já pode fechar esta aba após copiar)</p>
  </div>

  <script>
    let currentItemId = '';
    const connect = new PluggyConnect({{
      connectToken: '{token}',
      includeSandbox: true,
      onSuccess: function(itemData) {{
        console.log('Pluggy success:', itemData);
        currentItemId = itemData.item ? itemData.item.id : '';
        document.getElementById('box-init').style.display = 'none';
        document.getElementById('box-success').style.display = 'block';
        document.getElementById('txt-item-id').innerText = currentItemId;
        navigator.clipboard.writeText(currentItemId).catch(() => {{}});
      }},
      onError: function(err) {{
        console.error('Pluggy error:', err);
      }},
      onClose: function() {{
        if (currentItemId) {{
          document.getElementById('box-init').style.display = 'none';
          document.getElementById('box-success').style.display = 'block';
        }}
      }}
    }});

    document.getElementById('btn-open').addEventListener('click', function() {{
      connect.init();
    }});

    document.getElementById('btn-copy').addEventListener('click', function() {{
      if (currentItemId) {{
        navigator.clipboard.writeText(currentItemId).then(() => {{
          alert('ID copiado com sucesso! Agora vá no Plutos e clique em "+ Adicionar por ID".');
        }});
      }}
    }});

    // Inicializa automaticamente
    window.addEventListener('load', function() {{
      setTimeout(() => connect.init(), 300);
    }});
  </script>
</body>
</html>
"""
        html_file.write_text(html_content, encoding="utf-8")
        return html_file

    def fetch_items(self, local_items: Optional[List[PluggyConnectedItem]] = None) -> List[PluggyConnectedItem]:
        """
        Consulta todos os itens (conexões bancárias) cadastrados na conta Pluggy.
        Como o endpoint global 'GET /items' é restrito pela Pluggy a planos pagos,
        fazemos fallback transparente consultando individualmente cada item já
        registrado localmente via 'GET /items/{id}'.
        """
        try:
            data = self._send_request("items", method="GET", use_api_key=True)
            raw_results = data.get("results") or []
            return [PluggyConnectedItem.from_api_item(it) for it in raw_results]
        except RuntimeError as exc:
            # Fallback seguro para contas individuais/desenvolvedor
            if "Unauthorized" in str(exc) or "401" in str(exc) or "403" in str(exc):
                if local_items:
                    refreshed: List[PluggyConnectedItem] = []
                    for it in local_items:
                        try:
                            refreshed.append(self.fetch_item(it.item_id))
                        except Exception:
                            refreshed.append(it)
                    return refreshed
                return []
            raise

    def fetch_item(self, item_id: str) -> PluggyConnectedItem:
        """Consulta os detalhes e status de um item específico."""
        if not item_id:
            raise ValueError("item_id é obrigatório.")
        data = self._send_request(f"items/{item_id}", method="GET", use_api_key=True)
        return PluggyConnectedItem.from_api_item(data)

    def delete_item(self, item_id: str) -> bool:
        """Remove a conexão bancária na Pluggy (revoga consentimento e exclui dados)."""
        if not item_id:
            raise ValueError("item_id é obrigatório para exclusão.")
        try:
            self._send_request(f"items/{item_id}", method="DELETE", use_api_key=True)
            return True
        except RuntimeError as exc:
            if "404" in str(exc):
                return True
            raise

    def fetch_accounts(self, item_id: str) -> List[Dict[str, Any]]:
        """Consulta todas as contas (corrente, poupança, cartão de crédito) de uma conexão."""
        if not item_id:
            raise ValueError("item_id é obrigatório para buscar contas.")
        data = self._send_request(
            f"accounts?itemId={urllib.parse.quote(item_id)}", method="GET", use_api_key=True
        )
        return data.get("results") or []

    def fetch_investments(self, item_id: str) -> List[Dict[str, Any]]:
        """Consulta todos os investimentos vinculados à instituição."""
        if not item_id:
            raise ValueError("item_id é obrigatório para buscar investimentos.")
        data = self._send_request(
            f"investments?itemId={urllib.parse.quote(item_id)}", method="GET", use_api_key=True
        )
        return data.get("results") or []

    def fetch_transactions(
        self, account_id: str, from_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Consulta transações de uma conta utilizando a API moderna v2/transactions com paginação por cursor.
        Se informado from_date (YYYY-MM-DD), filtra apenas as transações a partir dessa data.
        """
        if not account_id:
            raise ValueError("account_id é obrigatório para buscar transações.")

        all_results: List[Dict[str, Any]] = []
        next_cursor: Optional[str] = f"?accountId={urllib.parse.quote(account_id)}"

        while next_cursor:
            endpoint = f"v2/transactions{next_cursor}"
            data = self._send_request(endpoint, method="GET", use_api_key=True)
            batch = data.get("results") or []
            all_results.extend(batch)
            next_cursor = data.get("next")
            if from_date and batch:
                oldest_in_batch = (batch[-1].get("date") or "")[:10]
                if oldest_in_batch and oldest_in_batch < from_date:
                    break

        if from_date:
            all_results = [
                tx for tx in all_results
                if (tx.get("date") or "")[:10] >= from_date
            ]

        return all_results
