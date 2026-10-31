"""Gerenciamento de configurações locais e caminhos de ativos da aplicação."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


def _resolve_app_and_project_dirs() -> tuple[Path, Path]:
    """Resolve diretórios tanto em execução Python quanto compilado via PyInstaller (`sys.frozen`)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        bundle_dir = Path(getattr(sys, "_MEIPASS", exe_dir))
        candidate_app = bundle_dir / "app"
        if (candidate_app / "assets").exists():
            return candidate_app, exe_dir
        return bundle_dir, exe_dir
    app_dir = Path(__file__).resolve().parent.parent
    return app_dir, app_dir.parent


def _resolve_default_user_data_dir(project_dir: Path) -> Path:
    """
    Resolve a pasta padrão de dados do usuário (`dados_usuario`):
    - No código-fonte ou modo portátil (quando a pasta ao lado do `.exe` é gravável e não está em Program Files),
      usa `<project_dir>/dados_usuario`.
    - Quando instalado em `Program Files` pelo instalador, usa `%LOCALAPPDATA%\\MinhasFinancas\\dados_usuario`.
    """
    if getattr(sys, "frozen", False):
        local_candidate = project_dir / "dados_usuario"
        prog_files = os.environ.get("ProgramFiles", "C:\\Program Files").lower()
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)").lower()
        proj_str = str(project_dir).lower()
        if not proj_str.startswith(prog_files) and not proj_str.startswith(prog_files_x86):
            try:
                local_candidate.mkdir(parents=True, exist_ok=True)
                (local_candidate / "backups").mkdir(parents=True, exist_ok=True)
                return local_candidate
            except OSError:
                pass
        appdata_base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        user_dir = appdata_base / "Plutos" / "dados_usuario"
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "backups").mkdir(parents=True, exist_ok=True)
        return user_dir
    return project_dir / "dados_usuario"


# Diretórios base da aplicação
APP_ROOT_DIR, PROJECT_ROOT_DIR = _resolve_app_and_project_dirs()
ASSETS_DIR: Path = APP_ROOT_DIR / "assets"
BANKS_ICONS_DIR: Path = ASSETS_DIR / "banks"
CREDIT_CARD_ICONS_DIR: Path = ASSETS_DIR / "credit_card"
IMAGES_DIR: Path = ASSETS_DIR / "images"
FONTS_DIR: Path = ASSETS_DIR / "fonts"
EXCEL_TEMPLATES_DIR: Path = ASSETS_DIR / "excel_templates"
SQL_ASSETS_DIR: Path = ASSETS_DIR / "sql"
SEED_DIR: Path = ASSETS_DIR / "seed"
SEED_BLANK_DB_PATH: Path = SEED_DIR / "minhasfinancas_blank.db"
SEED_DEFAULT_DB_PATH: Path = SEED_DIR / "minhasfinancas.db"
CATEGORIAS_MAP_JSON_PATH: Path = SEED_DIR / "categorias_map.json"

DEFAULT_USER_DATA_DIR: Path = _resolve_default_user_data_dir(PROJECT_ROOT_DIR)
DEFAULT_SETTINGS_FILE: Path = DEFAULT_USER_DATA_DIR / "app_settings.json"
DEFAULT_DB_FILE: Path = DEFAULT_USER_DATA_DIR / "plutos.sqlite"
DEFAULT_BACKUP_DIR: Path = DEFAULT_USER_DATA_DIR / "backups"

BACKUP_INTERVAL_3_HOURS_SECONDS: int = 3 * 3600  # 10.800 segundos (3 horas)
BACKUP_RETENTION_MAX_FILES: int = 6  # Exatamente 6 arquivos retidos


class DateReferenceMode(str, Enum):
    """Modos de data de referência para filtros, extrato, gráficos, relatórios e orçamentos."""

    VENCIMENTO = "vencimento"
    LANCAMENTO = "lancamento"
    LANCAMENTO_DISTRIBUIR = "lancamento_distribuir"
    EFETIVACAO = "efetivacao"

    def resolve_sql_file_for_context(self, query_relative_path: str) -> str:
        """Resolve o fragmento `data_referencia_*.sql` correspondente ao módulo da query."""
        norm = query_relative_path.replace("\\", "/").lower()
        if norm.startswith("orcamentos/listar_personalizados"):
            suffix = "_receita" if "receita" in norm else "_desp"
            return f"orcamentos/data_referencia_{self.value}{suffix}.sql"
        if norm.startswith("receitas/") or (
            norm.startswith("orcamentos/") and "receita" in norm
        ):
            return f"receitas/data_referencia_{self.value}.sql"
        if norm.startswith("transferencias/"):
            mode_val = (
                "lancamento"
                if self == DateReferenceMode.LANCAMENTO_DISTRIBUIR
                else self.value
            )
            return f"transferencias/data_referencia_{mode_val}.sql"
        return f"despesas/data_referencia_{self.value}.sql"



@dataclass
class AppSettings:
    """Configurações persistidas localmente em arquivo JSON com flush atômico em disco."""

    active_db_path: str = field(default_factory=lambda: str(DEFAULT_DB_FILE))
    recent_db_paths: List[str] = field(default_factory=list)
    backup_dir: str = field(default_factory=lambda: str(DEFAULT_BACKUP_DIR))
    backup_enabled: bool = True
    backup_interval_seconds: int = BACKUP_INTERVAL_3_HOURS_SECONDS
    backup_retention_count: int = BACKUP_RETENTION_MAX_FILES
    last_backed_up_mutation_token: Optional[str] = None
    last_backup_timestamp_iso: Optional[str] = None
    active_profile_id: str = "1"
    theme_mode: str = "light"  # 'light' ou 'dark'
    date_reference_mode: str = DateReferenceMode.VENCIMENTO.value
    window_width: int = 1366
    window_height: int = 840
    sidebar_collapsed: bool = False
    show_technical_details: bool = True
    gemini_model: str = "gemini-3.5-flash-lite"
    _settings_path: Path = field(
        default_factory=lambda: DEFAULT_SETTINGS_FILE, repr=False, compare=False
    )

    @property
    def user_data_dir(self) -> Path:
        """Pasta onde vivem `app_settings.json` e arquivos locais (ex.: chave Gemini)."""
        return self._settings_path.parent

    @classmethod
    def load(cls, settings_path: Optional[Path | str] = None) -> "AppSettings":
        """Carrega as configurações do disco ou inicializa com os padrões."""
        target_path = Path(settings_path) if settings_path else DEFAULT_SETTINGS_FILE
        if not target_path.exists():
            instance = cls(_settings_path=target_path)
            instance.save()
            return instance

        try:
            raw = json.loads(target_path.read_text(encoding="utf-8"))
            valid_keys = {
                k for k in cls.__dataclass_fields__.keys() if not k.startswith("_")
            }
            filtered = {k: v for k, v in raw.items() if k in valid_keys}
            instance = cls(**filtered, _settings_path=target_path)
            # Garante políticas obrigatórias do Requisito 5
            instance.backup_retention_count = BACKUP_RETENTION_MAX_FILES
            if instance.backup_interval_seconds <= 0:
                instance.backup_interval_seconds = BACKUP_INTERVAL_3_HOURS_SECONDS
            return instance
        except Exception:
            instance = cls(_settings_path=target_path)
            instance.save()
            return instance

    def save(self) -> None:
        """Persiste as configurações no disco de forma imediata e atômica."""
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            k: v
            for k, v in asdict(self).items()
            if not k.startswith("_")
        }
        tmp_path = self._settings_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(self._settings_path)

    def register_db_path(self, db_path: Path | str) -> None:
        """Atualiza o caminho do banco de dados ativo e mantém histórico de recentes."""
        resolved = str(Path(db_path).resolve())
        if self.active_db_path != resolved:
            # Ao trocar de banco, reseta o token de último backup para o novo arquivo
            self.last_backed_up_mutation_token = None
        self.active_db_path = resolved
        if resolved in self.recent_db_paths:
            self.recent_db_paths.remove(resolved)
        self.recent_db_paths.insert(0, resolved)
        self.recent_db_paths = self.recent_db_paths[:10]
        self.save()

    def set_backup_directory(self, backup_dir: Path | str) -> Path:
        """Configura e cria (se necessário) o diretório de backup."""
        resolved = Path(backup_dir).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        self.backup_dir = str(resolved)
        self.save()
        return resolved
