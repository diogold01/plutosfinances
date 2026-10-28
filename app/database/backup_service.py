"""Serviço de Backup Online em 2º Plano com Retenção de Exatamente 6 Arquivos (Requisito 5)."""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from app.config.app_settings import (
    BACKUP_INTERVAL_3_HOURS_SECONDS,
    BACKUP_RETENTION_MAX_FILES,
    AppSettings,
)
from app.database.connection_manager import ConnectionManager

BACKUP_FILENAME_PREFIX = "plutos_backup_"
BACKUP_FILENAME_REGEX = re.compile(
    r"^(?:plutos_backup_|minhasfinancas_backup_)(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})(?:_(\d+))?\.(?:sqlite|db)$",
    re.IGNORECASE,
)


@dataclass
class BackupResult:
    """Resultado detalhado de uma execução do ciclo de backup."""

    performed: bool
    reason: str
    created_file: Optional[Path] = None
    removed_files: List[Path] = field(default_factory=list)
    retained_files: List[Path] = field(default_factory=list)
    mutation_token: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


class BackupSchedulerService:
    """
    Gerencia a rotina de backup automático do banco SQLite:
    - Diretório de backup livremente configurável.
    - Execução automática em segundo plano a cada 3 horas (10.800 segundos).
    - Utiliza exclusivamente a API de Backup Online do SQLite (`sqlite3.Connection.backup`).
    - Executa apenas se houver modificações pendentes no banco desde o último backup.
    - Política estrita de retenção de exatamente 6 arquivos com data e hora no nome,
      descartando automaticamente o mais antigo ao atingir o limite.
    - Aviso prévio inteligente de 5 minutos antes do início do próximo ciclo.
    """

    RETENTION_LIMIT: int = BACKUP_RETENTION_MAX_FILES
    DEFAULT_INTERVAL_SECONDS: int = BACKUP_INTERVAL_3_HOURS_SECONDS

    def __init__(
        self,
        connection_manager: ConnectionManager,
        settings: Optional[AppSettings] = None,
        interval_seconds: Optional[int] = None,
    ) -> None:
        self.connection_manager = connection_manager
        self.settings = settings or connection_manager.settings
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None and interval_seconds > 0
            else self.settings.backup_interval_seconds
        )
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._listeners: List[Callable[[BackupResult], None]] = []
        self._advance_warning_listeners: List[Callable[[float], None]] = []
        self._next_run_timestamp: Optional[datetime] = None
        self._advance_warning_notified: bool = False

    @property
    def backup_dir(self) -> Path:
        path = Path(self.settings.backup_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def is_running(self) -> bool:
        return (
            self._worker_thread is not None
            and self._worker_thread.is_alive()
            and not self._stop_event.is_set()
        )

    def set_backup_directory(self, directory: Path | str) -> Path:
        """Altera o diretório onde os backups são armazenados."""
        with self._lock:
            return self.settings.set_backup_directory(directory)

    def add_backup_listener(
        self, callback: Callable[[BackupResult], None]
    ) -> None:
        """Registra um callback invocado após cada ciclo de backup."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def add_advance_warning_listener(
        self, callback: Callable[[float], None]
    ) -> None:
        """Registra callback invocado quando o próximo backup estiver prestes a ocorrer (<= 5 minutos)."""
        if callback not in self._advance_warning_listeners:
            self._advance_warning_listeners.append(callback)

    def _notify_advance_warning(self, seconds_left: float) -> None:
        for cb in list(self._advance_warning_listeners):
            try:
                cb(seconds_left)
            except Exception:
                pass

    def get_seconds_until_next_cycle(self) -> Optional[float]:
        """Retorna os segundos restantes até o próximo ciclo de backup automático."""
        with self._lock:
            if not self._next_run_timestamp:
                return None
            rem = (self._next_run_timestamp - datetime.now()).total_seconds()
            return max(0.0, rem)

    def is_advance_warning_active(self, threshold_seconds: float = 300.0) -> bool:
        """Retorna True se o próximo backup automático estiver a 5 minutos (300s) ou menos de acontecer."""
        rem = self.get_seconds_until_next_cycle()
        if rem is None:
            return False
        return 0.0 < rem <= threshold_seconds

    def _notify_listeners(self, result: BackupResult) -> None:
        for cb in list(self._listeners):
            try:
                cb(result)
            except Exception:
                pass

    def list_backups(self) -> List[Path]:
        """
        Lista os arquivos de backup existentes no diretório configurado,
        ordenados do mais antigo para o mais recente (ordem cronológica).
        """
        folder = self.backup_dir
        if not folder.exists():
            return []

        matched: List[tuple[str, int, float, Path]] = []
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            m = BACKUP_FILENAME_REGEX.match(entry.name)
            if m:
                dt_part = m.group(1)
                seq_part = int(m.group(2)) if m.group(2) is not None else 0
                mtime = entry.stat().st_mtime
                matched.append((dt_part, seq_part, mtime, entry))

        matched.sort(key=lambda item: (item[0], item[1], item[2], item[3].name))
        return [item[3] for item in matched]

    def has_pending_modifications(self) -> bool:
        """
        Verifica se o banco de dados possui modificações pendentes desde o último backup.
        Retorna True somente se:
        - O contador de mutações do banco for > 0, E
        - O token de mutação atual divergir do último token salvo no backup (ou se não existir arquivo de backup na pasta).
        """
        with self._lock:
            counter = self.connection_manager.get_mutation_counter()
            if counter <= 0:
                return False

            current_token = self.connection_manager.get_mutation_token()
            existing_backups = self.list_backups()
            if not existing_backups:
                return True

            return current_token != self.settings.last_backed_up_mutation_token

    def _build_backup_filepath(self, timestamp: Optional[datetime] = None) -> Path:
        """Gera o caminho do arquivo de backup contendo data e hora no nome."""
        dt = timestamp or datetime.now()
        stamp = dt.strftime("%Y-%m-%d_%H-%M-%S")
        folder = self.backup_dir
        candidate = folder / f"{BACKUP_FILENAME_PREFIX}{stamp}.sqlite"
        if not candidate.exists():
            return candidate

        # Caso mais de um backup ocorra no mesmo segundo, adiciona sufixo sequencial mantendo ordenação
        seq = 1
        while True:
            candidate = folder / f"{BACKUP_FILENAME_PREFIX}{stamp}_{seq:03d}.sqlite"
            if not candidate.exists():
                return candidate
            seq += 1

    def _enforce_retention_policy(self) -> tuple[List[Path], List[Path]]:
        """
        Aplica a política de retenção de exatamente 6 arquivos:
        se houver mais de 6 arquivos de backup no diretório, descarta os mais antigos.
        Retorna (arquivos_removidos, arquivos_retidos).
        """
        all_backups = self.list_backups()
        removed: List[Path] = []
        while len(all_backups) > self.RETENTION_LIMIT:
            oldest = all_backups.pop(0)
            try:
                oldest.unlink()
                removed.append(oldest)
            except OSError:
                pass
        return removed, all_backups

    def run_backup_cycle(
        self,
        force: bool = False,
        timestamp: Optional[datetime] = None,
    ) -> BackupResult:
        """
        Executa um ciclo de verificação e backup online:
        1. Verifica se há modificações pendentes (a menos que `force=True`).
        2. Caso haja modificações, usa a API Online Backup do SQLite (`sqlite3.Connection.backup`).
        3. Aplica a rotação automática mantendo no máximo 6 arquivos e descartando o mais antigo.
        """
        with self._lock:
            if not force and not self.has_pending_modifications():
                retained = self.list_backups()
                result = BackupResult(
                    performed=False,
                    reason="no_pending_modifications",
                    retained_files=retained,
                    mutation_token=self.connection_manager.get_mutation_token(),
                )
                self._notify_listeners(result)
                return result

            target_file = self._build_backup_filepath(timestamp=timestamp)
            self.connection_manager.perform_online_backup_to(target_file)
            current_token = self.connection_manager.get_mutation_token()

            removed_files, retained_files = self._enforce_retention_policy()

            now_iso = (timestamp or datetime.now()).isoformat(timespec="seconds")
            self.settings.last_backed_up_mutation_token = current_token
            self.settings.last_backup_timestamp_iso = now_iso
            self.settings.save()

            result = BackupResult(
                performed=True,
                reason="forced" if force else "pending_modifications",
                created_file=target_file,
                removed_files=removed_files,
                retained_files=retained_files,
                mutation_token=current_token,
                timestamp=now_iso,
            )
            self._notify_listeners(result)
            return result

    def restore_from_backup(self, backup_file: Path | str) -> Path:
        """
        Restaura um arquivo de backup para o banco de dados ativo utilizando a Online Backup API.
        """
        src_path = Path(backup_file).resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"Arquivo de backup não encontrado: {src_path}")

        with self._lock:
            active_path = self.connection_manager.ensure_connected()
            self.connection_manager.close()

            src_conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
            dst_conn = sqlite3.connect(str(active_path))
            try:
                src_conn.backup(dst_conn)
                dst_conn.commit()
            finally:
                src_conn.close()
                dst_conn.close()

            self.connection_manager.open_existing_database(active_path)
            self.settings.last_backed_up_mutation_token = (
                self.connection_manager.get_mutation_token()
            )
            self.settings.save()
            return active_path

    def start_background_scheduler(self) -> None:
        """Inicia o agendador em segundo plano que executa a verificação a cada 3 horas."""
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._advance_warning_notified = False
            self._next_run_timestamp = datetime.now() + timedelta(
                seconds=float(self.interval_seconds)
            )
            self._worker_thread = threading.Thread(
                target=self._background_loop,
                name="Plutos-BackupScheduler",
                daemon=True,
            )
            self._worker_thread.start()

    def stop_background_scheduler(self, timeout: float = 2.0) -> None:
        """Interrompe com segurança a thread de agendamento em segundo plano."""
        with self._lock:
            self._stop_event.set()
            thread = self._worker_thread
            self._worker_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def _background_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=1.0):
                break
            with self._lock:
                if not self._next_run_timestamp:
                    self._next_run_timestamp = datetime.now() + timedelta(
                        seconds=float(self.interval_seconds)
                    )
                now = datetime.now()
                rem = (self._next_run_timestamp - now).total_seconds()

            if 0.0 < rem <= 300.0 and not self._advance_warning_notified:
                self._advance_warning_notified = True
                self._notify_advance_warning(rem)

            if rem <= 0.0:
                if self.settings.backup_enabled:
                    try:
                        self.run_backup_cycle(force=False)
                    except Exception:
                        pass
                with self._lock:
                    self._advance_warning_notified = False
                    self._next_run_timestamp = datetime.now() + timedelta(
                        seconds=float(self.interval_seconds)
                    )
