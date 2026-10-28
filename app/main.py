"""Ponto de entrada da aplicação nativa Minhas Finanças Desktop (PySide6)."""

from __future__ import annotations

import sys
from pathlib import Path

# Garante que o diretório raiz do projeto esteja no sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from app.config.app_settings import AppSettings
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.database.repositories.profile_repository import ProfileRepository
from app.ui.main_window import MainWindow
from app.ui.style_manager import apply_app_theme, load_bundled_fonts


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Plutos")
    app.setOrganizationName("PlutosLocal")

    font_family = load_bundled_fonts()
    app.setFont(QFont(font_family, 10))

    settings = AppSettings.load()
    apply_app_theme(app, settings.theme_mode)

    db = ConnectionManager(settings=settings, auto_connect=True)
    backup_service = BackupSchedulerService(
        connection_manager=db, settings=settings
    )
    backup_service.start_background_scheduler()

    # Verifica PIN local caso configurado
    prof_repo = ProfileRepository(db)
    if prof_repo.has_local_pin():
        pin_txt, ok = QInputDialog.getText(
            None,
            "Desbloqueio — Plutos",
            "Informe seu PIN local de acesso:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not prof_repo.verify_local_pin(pin_txt):
            QMessageBox.critical(
                None, "Acesso Negado", "PIN inválido. Encerrando aplicação."
            )
            backup_service.stop_background_scheduler()
            db.close()
            return 1

    window = MainWindow(db=db, backup_service=backup_service)
    window.show()

    exit_code = app.exec()
    backup_service.stop_background_scheduler()
    db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
