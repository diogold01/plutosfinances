"""Armazenamento local da chave de API do Gemini (BYOK).

Ordem de leitura: variável de ambiente `GEMINI_API_KEY` > `dados_usuario/gemini_key.local`.
A chave nunca é gravada em `app_settings.json`, Git, logs ou instalador.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

ENV_VAR = "GEMINI_API_KEY"
KEY_FILE_NAME = "gemini_key.local"

SOURCE_ENV = "env"
SOURCE_FILE = "arquivo"
SOURCE_NONE = "nenhuma"


def key_file_path(user_data_dir: Path | str) -> Path:
    return Path(user_data_dir) / KEY_FILE_NAME


def resolve_gemini_key(user_data_dir: Path | str) -> Tuple[str, str]:
    """Retorna `(chave, origem)`; chave vazia e origem 'nenhuma' se não configurada."""
    env_key = os.environ.get(ENV_VAR, "").strip()
    if env_key:
        return env_key, SOURCE_ENV
    path = key_file_path(user_data_dir)
    try:
        if path.exists():
            file_key = path.read_text(encoding="utf-8").strip()
            if file_key:
                return file_key, SOURCE_FILE
    except OSError:
        pass
    return "", SOURCE_NONE


def save_gemini_key(user_data_dir: Path | str, key: str) -> Path:
    path = key_file_path(user_data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip(), encoding="utf-8")
    return path


def clear_gemini_key(user_data_dir: Path | str) -> None:
    path = key_file_path(user_data_dir)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def mask_key(key: Optional[str]) -> str:
    """Máscara para exibição (nunca mostrar a chave completa em textos/logs)."""
    if not key:
        return ""
    return f"{key[:4]}…{key[-3:]}" if len(key) > 8 else "••••"
