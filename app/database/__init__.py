"""Camada de persistência SQLite e serviço de backup online em 2º plano."""

from .backup_service import BackupResult, BackupSchedulerService
from .connection_manager import ConnectionManager, DatabaseError
from .schema_initializer import (
    ensure_schema_migrations,
    initialize_new_database_file,
)

__all__ = [
    "BackupResult",
    "BackupSchedulerService",
    "ConnectionManager",
    "DatabaseError",
    "ensure_schema_migrations",
    "initialize_new_database_file",
]
