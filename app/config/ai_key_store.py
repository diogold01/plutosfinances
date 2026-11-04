"""Armazenamento local da chave de API de IA (BYOK).

Ordem de leitura:
1. Variáveis de ambiente (`AI_API_KEY` ou `GEMINI_API_KEY`).
2. Arquivos locais em `dados_usuario/` (`ai_key.local` ou fallback `gemini_key.local`).

A chave nunca é gravada em `app_settings.json`, Git, logs ou instalador.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

PRIMARY_ENV_VAR = "AI_API_KEY"
FALLBACK_ENV_VAR = "GEMINI_API_KEY"

PRIMARY_KEY_FILE = "ai_key.local"
FALLBACK_KEY_FILE = "gemini_key.local"

# Compatibilidade
ENV_VAR = PRIMARY_ENV_VAR
KEY_FILE_NAME = PRIMARY_KEY_FILE

SOURCE_ENV = "env"
SOURCE_FILE = "arquivo"
SOURCE_NONE = "nenhuma"


def key_file_path(user_data_dir: Path | str) -> Path:
    return Path(user_data_dir) / PRIMARY_KEY_FILE


def resolve_ai_key(user_data_dir: Path | str) -> Tuple[str, str]:
    """Retorna `(chave, origem)`; chave vazia e origem 'nenhuma' se não configurada.
    
    Verifica primeiro as variáveis de ambiente (AI_API_KEY, depois GEMINI_API_KEY)
    e em seguida os arquivos locais (ai_key.local, depois gemini_key.local).
    """
    for env_name in (PRIMARY_ENV_VAR, FALLBACK_ENV_VAR):
        env_key = os.environ.get(env_name, "").strip()
        if env_key:
            return env_key, SOURCE_ENV

    base_dir = Path(user_data_dir)
    for fname in (PRIMARY_KEY_FILE, FALLBACK_KEY_FILE):
        path = base_dir / fname
        try:
            if path.exists():
                file_key = path.read_text(encoding="utf-8").strip()
                if file_key:
                    return file_key, SOURCE_FILE
        except OSError:
            pass

    return "", SOURCE_NONE


def save_ai_key(user_data_dir: Path | str, key: str) -> Path:
    """Salva a chave no arquivo primário local (`ai_key.local`)."""
    path = key_file_path(user_data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip(), encoding="utf-8")
    return path


def clear_ai_key(user_data_dir: Path | str) -> None:
    """Remove ambos os arquivos locais de chave se existirem."""
    base_dir = Path(user_data_dir)
    for fname in (PRIMARY_KEY_FILE, FALLBACK_KEY_FILE):
        path = base_dir / fname
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def mask_key(key: Optional[str]) -> str:
    """Máscara para exibição (nunca mostrar a chave completa em textos/logs)."""
    if not key:
        return ""
    return f"{key[:4]}…{key[-3:]}" if len(key) > 8 else "••••"


# Aliases para retrocompatibilidade total
resolve_gemini_key = resolve_ai_key
save_gemini_key = save_ai_key
clear_gemini_key = clear_ai_key
