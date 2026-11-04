"""Módulo de compatibilidade para ai_key_store.

Reexporta todas as funções e constantes de `app.config.ai_key_store`.
"""

from __future__ import annotations

from app.config.ai_key_store import (
    ENV_VAR,
    FALLBACK_ENV_VAR,
    FALLBACK_KEY_FILE,
    KEY_FILE_NAME,
    PRIMARY_ENV_VAR,
    PRIMARY_KEY_FILE,
    SOURCE_ENV,
    SOURCE_FILE,
    SOURCE_NONE,
    clear_ai_key,
    clear_gemini_key,
    key_file_path,
    mask_key,
    resolve_ai_key,
    resolve_gemini_key,
    save_ai_key,
    save_gemini_key,
)

__all__ = [
    "ENV_VAR",
    "FALLBACK_ENV_VAR",
    "FALLBACK_KEY_FILE",
    "KEY_FILE_NAME",
    "PRIMARY_ENV_VAR",
    "PRIMARY_KEY_FILE",
    "SOURCE_ENV",
    "SOURCE_FILE",
    "SOURCE_NONE",
    "clear_ai_key",
    "clear_gemini_key",
    "key_file_path",
    "mask_key",
    "resolve_ai_key",
    "resolve_gemini_key",
    "save_ai_key",
    "save_gemini_key",
]
