"""Testes unitários para o módulo Pluggy Client e Config Manager (Fases 1 e 2)."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from app.services.pluggy_client import (
    PluggyClient,
    PluggyConfig,
    PluggyConfigManager,
    PluggyConnectedItem,
)


def test_pluggy_config_serialization(tmp_path: Path):
    manager = PluggyConfigManager(tmp_path)
    cfg = manager.load_config()
    assert cfg.client_id == ""
    assert cfg.client_secret == ""
    assert cfg.items == []

    # Salva nova configuração
    new_cfg = PluggyConfig(
        client_id="test_id_123",
        client_secret="test_secret_456",
        items=[
            PluggyConnectedItem(
                item_id="item_01",
                connector_name="Nubank",
                status="UPDATED",
            )
        ],
    )
    manager.save_config(new_cfg)

    # Recarrega do disco
    loaded = manager.load_config()
    assert loaded.client_id == "test_id_123"
    assert loaded.client_secret == "test_secret_456"
    assert len(loaded.items) == 1
    assert loaded.items[0].connector_name == "Nubank"
    assert loaded.items[0].item_id == "item_01"


def test_pluggy_config_upsert_and_remove():
    cfg = PluggyConfig()
    it1 = PluggyConnectedItem(item_id="item_1", connector_name="Itaú")
    cfg.upsert_item(it1)
    assert len(cfg.items) == 1
    assert cfg.items[0].connector_name == "Itaú"

    # Atualiza mesmo item
    it1_updated = PluggyConnectedItem(item_id="item_1", connector_name="Itaú Unibanco")
    cfg.upsert_item(it1_updated)
    assert len(cfg.items) == 1
    assert cfg.items[0].connector_name == "Itaú Unibanco"

    # Adiciona segundo item
    it2 = PluggyConnectedItem(item_id="item_2", connector_name="Nubank")
    cfg.upsert_item(it2)
    assert len(cfg.items) == 2

    # Remove item 1
    removed = cfg.remove_item("item_1")
    assert removed is True
    assert len(cfg.items) == 1
    assert cfg.items[0].item_id == "item_2"


def test_pluggy_client_requires_credentials():
    client = PluggyClient()
    with pytest.raises(ValueError, match="obrigatórios"):
        client.authenticate("", "")


def test_pluggy_client_authenticate_success():
    client = PluggyClient("test_id", "test_secret")

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"apiKey": "jwt_token_sample_123"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        token = client.authenticate()
        assert token == "jwt_token_sample_123"
        assert client._api_key == "jwt_token_sample_123"
        mock_urlopen.assert_called_once()


def test_pluggy_client_authenticate_invalid_credentials():
    client = PluggyClient("bad_id", "bad_secret")

    http_error = urllib.error.HTTPError(
        url="https://api.pluggy.ai/auth",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=BytesIO(b'{"message": "Invalid clientId or clientSecret"}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(ValueError, match="Credenciais inválidas"):
            client.authenticate()


def test_pluggy_client_create_connect_token():
    client = PluggyClient("test_id", "test_secret")
    client._api_key = "mock_api_key"

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"accessToken": "connect_token_xyz"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        token, url = client.create_connect_token()
        assert token == "connect_token_xyz"
        assert url == "https://connect.pluggy.ai/?connectToken=connect_token_xyz"


def test_pluggy_client_fetch_items():
    client = PluggyClient("test_id", "test_secret")
    client._api_key = "mock_api_key"

    sample_api_response = {
        "results": [
            {
                "id": "item_123",
                "connector": {"id": 201, "name": "Nubank", "imageUrl": "http://img.png"},
                "status": "UPDATED",
                "executionStatus": "SUCCESS",
                "lastUpdatedAt": "2026-10-31T20:00:00Z",
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(sample_api_response).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        items = client.fetch_items()
        assert len(items) == 1
        assert items[0].item_id == "item_123"
        assert items[0].connector_name == "Nubank"
        assert items[0].status == "UPDATED"


def test_pluggy_client_delete_item():
    client = PluggyClient("test_id", "test_secret")
    client._api_key = "mock_api_key"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"count": 1}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = client.delete_item("item_123")
        assert res is True
