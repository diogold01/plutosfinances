"""Gerenciador de conexões e transações SQLite com confirmação imediata em disco (Requisito 4)."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence

from app.config.app_settings import (
    AppSettings,
    DateReferenceMode,
    SQL_ASSETS_DIR,
)
from app.database.schema_initializer import (
    ensure_schema_migrations,
    initialize_new_database_file,
)


class DatabaseError(Exception):
    """Exceção de domínio para erros de persistência SQLite."""


class ConnectionManager:
    """
    Gerencia a conexão ativa com o arquivo único SQLite (.db / .sqlite).
    Garante:
    - Seleção livre de diretório/arquivo para criar nova base ou abrir existente.
    - Persistência estrita em arquivo único (`PRAGMA journal_mode = DELETE`, `PRAGMA synchronous = FULL`).
    - Transações atômicas (`BEGIN IMMEDIATE ... COMMIT`) com gravação física imediata a cada operação.
    - Rastreamento determinístico de modificações (`mutation_counter`) para a rotina de backup online.
    """

    VALID_EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".s3db"}

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        auto_connect: bool = True,
    ) -> None:
        self._lock = threading.RLock()
        self.settings = settings or AppSettings.load()
        self._conn: Optional[sqlite3.Connection] = None
        self._db_path: Optional[Path] = None
        self._on_database_changed_callbacks: List[Callable[[Path], None]] = []
        self._sql_cache: Dict[str, str] = {}

        if auto_connect:
            self.ensure_connected()

    @property
    def db_path(self) -> Optional[Path]:
        return self._db_path

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def add_database_changed_listener(
        self, callback: Callable[[Path], None]
    ) -> None:
        """Registra um listener notificado sempre que o usuário cria ou carrega outra base."""
        if callback not in self._on_database_changed_callbacks:
            self._on_database_changed_callbacks.append(callback)

    def _notify_database_changed(self, path: Path) -> None:
        for cb in list(self._on_database_changed_callbacks):
            try:
                cb(path)
            except Exception:
                pass

    def ensure_connected(self) -> Path:
        """Conecta ao banco ativo configurado em AppSettings (criando-o se ainda não existir)."""
        with self._lock:
            if self._conn is not None and self._db_path is not None:
                return self._db_path

            configured_path = Path(self.settings.active_db_path).resolve()
            if configured_path.exists():
                return self.open_existing_database(configured_path)
            return self.create_new_database(configured_path, overwrite=True)

    def _configure_connection_pragmas(self, conn: sqlite3.Connection) -> None:
        """
        Configura PRAGMAs de durabilidade máxima em arquivo único:
        - journal_mode = DELETE: mantém 100% dos dados contidos no arquivo único .db/.sqlite em repouso.
        - synchronous = FULL: força fsync imediato em disco a cada COMMIT (zero perda de dados).
        - foreign_keys = ON: integridade referencial ativa.
        """
        conn.execute("PRAGMA busy_timeout = 10000;")
        conn.execute("PRAGMA journal_mode = DELETE;")
        conn.execute("PRAGMA synchronous = FULL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA temp_store = MEMORY;")

    def _open_raw_connection(self, path: Path) -> sqlite3.Connection:
        """Abre uma conexão SQLite com controle manual de transações (isolation_level=None)."""
        conn = sqlite3.connect(
            str(path),
            isolation_level=None,  # Controle explícito BEGIN IMMEDIATE / COMMIT imediato
            check_same_thread=False,
            timeout=15.0,
        )
        conn.row_factory = sqlite3.Row
        self._configure_connection_pragmas(conn)
        return conn

    def create_new_database(
        self,
        target_path: Path | str,
        overwrite: bool = False,
    ) -> Path:
        """
        Cria uma nova base de dados SQLite (.db ou .sqlite) no diretório selecionado pelo usuário,
        popula o esquema e taxonomia inicial e passa a utilizá-la imediatamente.
        """
        with self._lock:
            resolved = Path(target_path).resolve()
            if resolved.suffix.lower() not in self.VALID_EXTENSIONS:
                resolved = resolved.with_suffix(".sqlite")

            self.close()
            initialize_new_database_file(resolved, overwrite=overwrite)
            self._conn = self._open_raw_connection(resolved)
            self._db_path = resolved
            self.settings.register_db_path(resolved)
            self._notify_database_changed(resolved)
            return resolved

    def open_existing_database(self, target_path: Path | str) -> Path:
        """
        Carrega uma base de dados SQLite (.db ou .sqlite) existente selecionada pelo usuário,
        valida sua integridade e aplica migrações idempotentes.
        """
        with self._lock:
            resolved = Path(target_path).resolve()
            if not resolved.exists() or not resolved.is_file():
                raise FileNotFoundError(
                    f"Arquivo de banco de dados não encontrado: {resolved}"
                )

            # Verifica cabeçalho SQLite ou validade do arquivo antes de substituir a conexão ativa
            test_conn = self._open_raw_connection(resolved)
            try:
                integrity = test_conn.execute("PRAGMA quick_check;").fetchone()
                if not integrity or integrity[0].lower() != "ok":
                    raise DatabaseError(
                        f"Falha na verificação de integridade do banco SQLite: {resolved}"
                    )
                ensure_schema_migrations(test_conn)
            except sqlite3.DatabaseError as exc:
                test_conn.close()
                raise DatabaseError(
                    f"O arquivo selecionado não é um banco SQLite válido: {resolved}"
                ) from exc

            self.close()
            self._conn = test_conn
            self._db_path = resolved
            self.settings.register_db_path(resolved)
            self._notify_database_changed(resolved)
            return resolved

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        """
        Context manager transacional com gravação e confirmação imediata em disco (BEGIN IMMEDIATE / COMMIT).
        Se ocorrer qualquer erro, executa ROLLBACK imediatamente.
        """
        with self._lock:
            if self._conn is None:
                self.ensure_connected()
            assert self._conn is not None

            cursor = self._conn.cursor()
            in_outer_tx = self._conn.in_transaction
            if not in_outer_tx:
                cursor.execute("BEGIN IMMEDIATE;")
            try:
                yield cursor
                if not in_outer_tx and self._conn.in_transaction:
                    cursor.execute("COMMIT;")
            except Exception:
                if not in_outer_tx and self._conn.in_transaction:
                    try:
                        cursor.execute("ROLLBACK;")
                    except Exception:
                        pass
                raise
            finally:
                cursor.close()

    def execute_write(
        self,
        sql: str,
        params: Sequence[Any] | Dict[str, Any] = (),
    ) -> int:
        """
        Executa uma operação de escrita (INSERT, UPDATE, DELETE) com confirmação imediata em disco.
        Retorna a quantidade de linhas afetadas (`rowcount`).
        """
        with self.transaction() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def executemany_write(
        self,
        sql: str,
        seq_of_params: Iterable[Sequence[Any] | Dict[str, Any]],
    ) -> int:
        """
        Executa um lote de escritas em uma única transação atômica com confirmação imediata em disco.
        """
        with self.transaction() as cur:
            cur.executemany(sql, seq_of_params)
            return cur.rowcount

    def execute_query(
        self,
        sql: str,
        params: Sequence[Any] | Dict[str, Any] = (),
    ) -> List[sqlite3.Row]:
        """Executa uma consulta de leitura (SELECT) e retorna todas as linhas."""
        with self._lock:
            if self._conn is None:
                self.ensure_connected()
            assert self._conn is not None
            cur = self._conn.execute(sql, params)
            try:
                return cur.fetchall()
            finally:
                cur.close()

    def fetch_one(
        self,
        sql: str,
        params: Sequence[Any] | Dict[str, Any] = (),
    ) -> Optional[sqlite3.Row]:
        """Executa uma consulta de leitura e retorna a primeira linha ou None."""
        with self._lock:
            if self._conn is None:
                self.ensure_connected()
            assert self._conn is not None
            cur = self._conn.execute(sql, params)
            try:
                return cur.fetchone()
            finally:
                cur.close()

    def fetch_scalar(
        self,
        sql: str,
        params: Sequence[Any] | Dict[str, Any] = (),
        default: Any = None,
    ) -> Any:
        """Executa uma consulta e retorna o valor da primeira coluna da primeira linha."""
        row = self.fetch_one(sql, params)
        if row is None or len(row) == 0:
            return default
        return row[0]

    def get_mutation_counter(self) -> int:
        """Retorna o contador monotônico de modificações gravadas no banco."""
        val = self.fetch_scalar(
            "SELECT value FROM app_metadata WHERE key = 'mutation_counter'",
            default="0",
        )
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    def get_last_modified_utc(self) -> Optional[str]:
        """Retorna o timestamp ISO UTC da última modificação gravada no banco."""
        return self.fetch_scalar(
            "SELECT value FROM app_metadata WHERE key = 'last_modified_utc'",
            default=None,
        )

    def get_mutation_token(self) -> str:
        """
        Gera o token determinístico de estado de modificação do banco ativo.
        Usado pelo serviço de backup para identificar se houve modificações pendentes.
        """
        with self._lock:
            if self._db_path is None:
                self.ensure_connected()
            counter = self.get_mutation_counter()
            return f"{self._db_path}::{counter}"

    def perform_online_backup_to(
        self,
        destination_path: Path | str,
        pages_per_step: int = 100,
    ) -> Path:
        """
        Executa cópia online consistente do banco ativo para `destination_path`
        utilizando a API oficial de Backup Online do SQLite (`sqlite3.Connection.backup`).
        """
        dest = Path(destination_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._conn is None:
                self.ensure_connected()
            assert self._conn is not None

            dest_conn = sqlite3.connect(str(dest))
            try:
                self._conn.backup(dest_conn, pages=pages_per_step)
                dest_conn.execute("PRAGMA journal_mode = DELETE;")
                dest_conn.execute("PRAGMA synchronous = FULL;")
                dest_conn.commit()
            finally:
                dest_conn.close()
        return dest

    def load_sql_asset(
        self,
        relative_sql_path: str,
        date_ref_mode: Optional[DateReferenceMode | str] = None,
        extra_params_sql: str = "",
        template_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Carrega um arquivo .sql de `app/assets/sql/` e injeta dinamicamente:
        - `{param_data_ref}`: expressão SQL do modo de data de referência ativo (Vencimento, Lançamento ou Efetivação).
        - `{params}` / `{params_calc}`: cláusulas adicionais de filtro SQL.
        """
        norm_rel = relative_sql_path.replace("\\", "/").lstrip("/")
        if norm_rel not in self._sql_cache:
            full_path = SQL_ASSETS_DIR / norm_rel
            if not full_path.exists():
                raise FileNotFoundError(
                    f"Arquivo SQL não encontrado em assets/sql: {norm_rel}"
                )
            self._sql_cache[norm_rel] = full_path.read_text(
                encoding="utf-8", errors="replace"
            )

        raw_sql = self._sql_cache[norm_rel]
        if "{param_data_ref}" in raw_sql:
            mode = (
                DateReferenceMode(date_ref_mode)
                if date_ref_mode
                else DateReferenceMode(self.settings.date_reference_mode)
            )
            ref_file = mode.resolve_sql_file_for_context(norm_rel)
            if ref_file not in self._sql_cache:
                self._sql_cache[ref_file] = (
                    SQL_ASSETS_DIR / ref_file
                ).read_text(encoding="utf-8", errors="replace")
            raw_sql = raw_sql.replace(
                "{param_data_ref}", self._sql_cache[ref_file].strip()
            )

        if "{params}" in raw_sql:
            raw_sql = raw_sql.replace("{params}", extra_params_sql)
        if "{params_calc}" in raw_sql:
            raw_sql = raw_sql.replace("{params_calc}", extra_params_sql)

        if template_vars:
            for k, v in template_vars.items():
                raw_sql = raw_sql.replace(f"{{{k}}}", v)

        return raw_sql

    def close(self) -> None:
        """Fecha a conexão SQLite ativa com segurança."""
        with self._lock:
            if self._conn is not None:
                try:
                    if self._conn.in_transaction:
                        self._conn.execute("COMMIT;")
                except Exception:
                    pass
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
