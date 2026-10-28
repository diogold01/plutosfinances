"""Tela de Configurações, Seletor de Base SQLite, Backup Online e Perfis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import ThemePalette
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.database.repositories.profile_repository import ProfileRepository
from app.ui.bank_icons import create_color_badge_icon
from app.ui.components import Badge
from app.ui.icons import get_line_icon
from app.ui.views.categorias_view import CategoryItemDialog


class ConfiguracoesView(QWidget):
    """
    Painel de controle unificado para:
    - Seleção livre de arquivo único SQLite (.db / .sqlite) para criar nova base ou abrir existente.
    - Configuração da pasta de backup, rotina automática e restauração.
    - Gestão de Perfis Financeiros (`profiles`) e PIN de segurança local.
    """

    def __init__(
        self,
        db: ConnectionManager,
        backup_service: BackupSchedulerService,
        on_environment_changed: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.backup_service = backup_service
        self.on_environment_changed = on_environment_changed
        self.profile_repo = ProfileRepository(db)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_title = QLabel("Configurações")
        lbl_title.setObjectName("SectionTitle")
        lbl_sub = QLabel(
            "Gerenciamento de banco de dados, cópias de segurança (backup) e perfis de uso"
        )
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        root.addLayout(title_box)

        # ------------------------------------------------------------------ #
        # Card 1: Banco de Dados SQLite
        # ------------------------------------------------------------------ #
        db_card = QFrame()
        db_card.setObjectName("CardSurface")
        db_lay = QVBoxLayout(db_card)
        db_lay.setContentsMargins(20, 18, 20, 18)
        db_lay.setSpacing(12)

        db_head = QHBoxLayout()
        db_t_col = QVBoxLayout()
        db_t_col.setSpacing(2)
        lbl_db_title = QLabel("Banco de Dados Local")
        f_bold = QFont()
        f_bold.setBold(True)
        f_bold.setPointSize(11)
        lbl_db_title.setFont(f_bold)
        lbl_db_sub = QLabel("Armazenamento dos seus dados em arquivo único SQLite")
        lbl_db_sub.setObjectName("MutedText")
        db_t_col.addWidget(lbl_db_title)
        db_t_col.addWidget(lbl_db_sub)
        db_head.addLayout(db_t_col)
        db_head.addStretch()

        self.btn_toggle_tech = QPushButton("Mostrar detalhes técnicos")
        self.btn_toggle_tech.setObjectName("SecondaryButton")
        self.btn_toggle_tech.clicked.connect(self._toggle_tech_button)
        db_head.addWidget(self.btn_toggle_tech)
        db_lay.addLayout(db_head)

        self.lbl_active_db = QLabel()
        self.lbl_active_db.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        db_lay.addWidget(self.lbl_active_db)

        # Container recolhível para detalhes técnicos
        self.tech_details_frame = QFrame()
        self.tech_details_frame.setObjectName("TechDetailsFrame")
        self.tech_details_frame.setVisible(
            getattr(self.db.settings, "show_technical_details", False)
        )
        tech_lay = QVBoxLayout(self.tech_details_frame)
        tech_lay.setContentsMargins(12, 10, 12, 10)
        tech_lay.setSpacing(4)
        self.lbl_tech_info = QLabel()
        self.lbl_tech_info.setObjectName("MutedText")
        self.lbl_tech_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        tech_lay.addWidget(self.lbl_tech_info)
        db_lay.addWidget(self.tech_details_frame)

        # Checkbox escondido para compatibilidade com testes
        self.chk_show_tech = QCheckBox("Exibir Detalhes Técnicos")
        self.chk_show_tech.setVisible(False)
        self.chk_show_tech.setChecked(
            getattr(self.db.settings, "show_technical_details", False)
        )
        self.chk_show_tech.toggled.connect(self._on_toggle_technical_details)
        db_lay.addWidget(self.chk_show_tech)

        db_btns = QHBoxLayout()
        db_btns.setSpacing(8)

        btn_new_db = QPushButton("+ Novo Banco de Dados")
        btn_new_db.setObjectName("PrimaryButton")
        btn_new_db.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        btn_new_db.clicked.connect(self.action_create_new_database)

        btn_open_db = QPushButton("Abrir Existente...")
        btn_open_db.setObjectName("SecondaryButton")
        btn_open_db.setIcon(get_line_icon("folder", size=14))
        btn_open_db.clicked.connect(self.action_open_existing_database)

        self.cb_recent_dbs = QComboBox()
        self.cb_recent_dbs.setMinimumWidth(280)
        btn_switch_recent = QPushButton("Alternar")
        btn_switch_recent.setObjectName("SecondaryButton")
        btn_switch_recent.clicked.connect(self._on_switch_recent_db)

        db_btns.addWidget(btn_new_db)
        db_btns.addWidget(btn_open_db)
        db_btns.addStretch()
        db_btns.addWidget(QLabel("Bancos Recentes:"))
        db_btns.addWidget(self.cb_recent_dbs)
        db_btns.addWidget(btn_switch_recent)
        db_lay.addLayout(db_btns)

        root.addWidget(db_card)

        # ------------------------------------------------------------------ #
        # Card 2: Backup e Segurança
        # ------------------------------------------------------------------ #
        bkp_card = QFrame()
        bkp_card.setObjectName("CardSurface")
        bkp_lay = QVBoxLayout(bkp_card)
        bkp_lay.setContentsMargins(20, 18, 20, 18)
        bkp_lay.setSpacing(12)

        bkp_head = QHBoxLayout()
        bkp_t_col = QVBoxLayout()
        bkp_t_col.setSpacing(2)
        lbl_bkp_title = QLabel("Cópias de Segurança (Backup)")
        lbl_bkp_title.setFont(f_bold)
        lbl_bkp_sub = QLabel(
            "Rotina automática a cada 3 horas com retenção dos últimos 6 arquivos"
        )
        lbl_bkp_sub.setObjectName("MutedText")
        bkp_t_col.addWidget(lbl_bkp_title)
        bkp_t_col.addWidget(lbl_bkp_sub)
        bkp_head.addLayout(bkp_t_col)
        bkp_head.addStretch()

        btn_choose_bkp_dir = QPushButton("Alterar Pasta de Backup...")
        btn_choose_bkp_dir.setObjectName("SecondaryButton")
        btn_choose_bkp_dir.setIcon(get_line_icon("folder", size=14))
        btn_choose_bkp_dir.clicked.connect(self.action_select_backup_directory)
        bkp_head.addWidget(btn_choose_bkp_dir)
        bkp_lay.addLayout(bkp_head)

        self.lbl_backup_info = QLabel()
        self.lbl_backup_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        bkp_lay.addWidget(self.lbl_backup_info)

        bkp_btns = QHBoxLayout()
        bkp_btns.setSpacing(8)

        btn_run_bkp_force = QPushButton("Fazer Backup Agora")
        btn_run_bkp_force.setObjectName("PrimaryButton")
        btn_run_bkp_force.setIcon(get_line_icon("clock", size=14, color="#FFFFFF"))
        btn_run_bkp_force.clicked.connect(lambda: self._run_backup(force=True))

        btn_run_bkp_smart = QPushButton("Sincronizar se Pendente")
        btn_run_bkp_smart.setObjectName("SecondaryButton")
        btn_run_bkp_smart.clicked.connect(lambda: self._run_backup(force=False))

        btn_restore_bkp = QPushButton("Restaurar Cópia Selecionada")
        btn_restore_bkp.setObjectName("SecondaryButton")
        btn_restore_bkp.setIcon(get_line_icon("refresh_cw", size=14))
        btn_restore_bkp.clicked.connect(self._on_restore_selected_backup)

        bkp_btns.addWidget(btn_run_bkp_force)
        bkp_btns.addWidget(btn_run_bkp_smart)
        bkp_btns.addStretch()
        bkp_btns.addWidget(btn_restore_bkp)
        bkp_lay.addLayout(bkp_btns)

        self.table_backups = QTableWidget(0, 3)
        self.table_backups.setHorizontalHeaderLabels(
            ["Arquivo de Backup", "Data e Hora", "Tamanho"]
        )
        self.table_backups.setShowGrid(False)
        self.table_backups.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_backups.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_backups.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_backups.verticalHeader().setVisible(False)
        self.table_backups.verticalHeader().setDefaultSectionSize(36)
        self.table_backups.setMaximumHeight(150)
        bh = self.table_backups.horizontalHeader()
        bh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        bh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        bh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        bkp_lay.addWidget(self.table_backups)

        root.addWidget(bkp_card)

        # ------------------------------------------------------------------ #
        # Card 3: Perfis e Segurança Local
        # ------------------------------------------------------------------ #
        prof_card = QFrame()
        prof_card.setObjectName("CardSurface")
        prof_lay = QVBoxLayout(prof_card)
        prof_lay.setContentsMargins(20, 18, 20, 18)
        prof_lay.setSpacing(12)

        prof_head = QHBoxLayout()
        prof_t_col = QVBoxLayout()
        prof_t_col.setSpacing(2)
        lbl_prof_title = QLabel("Perfis e Segurança")
        lbl_prof_title.setFont(f_bold)
        lbl_prof_sub = QLabel("Gerencie perfis separados e proteção opcional por PIN")
        lbl_prof_sub.setObjectName("MutedText")
        prof_t_col.addWidget(lbl_prof_title)
        prof_t_col.addWidget(lbl_prof_sub)
        prof_head.addLayout(prof_t_col)
        prof_head.addStretch()

        prof_btns = QHBoxLayout()
        prof_btns.setSpacing(8)

        btn_new_prof = QPushButton("+ Novo Perfil")
        btn_new_prof.setObjectName("PrimaryButton")
        btn_new_prof.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        btn_new_prof.clicked.connect(self._on_new_profile)

        btn_activate_prof = QPushButton("Tornar Perfil Ativo")
        btn_activate_prof.setObjectName("SecondaryButton")
        btn_activate_prof.clicked.connect(self._on_activate_selected_profile)

        btn_pin = QPushButton("Configurar PIN")
        btn_pin.setObjectName("SecondaryButton")
        btn_pin.setIcon(get_line_icon("lock", size=14))
        btn_pin.clicked.connect(self._on_configure_pin)

        prof_btns.addWidget(btn_activate_prof)
        prof_btns.addWidget(btn_pin)
        prof_btns.addWidget(btn_new_prof)
        prof_head.addLayout(prof_btns)
        prof_lay.addLayout(prof_head)

        self.table_profiles = QTableWidget(0, 4)
        self.table_profiles.setHorizontalHeaderLabels(
            ["Perfil", "Moeda", "Cor", "Situação"]
        )
        self.table_profiles.setShowGrid(False)
        self.table_profiles.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table_profiles.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_profiles.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_profiles.verticalHeader().setVisible(False)
        self.table_profiles.verticalHeader().setDefaultSectionSize(36)
        self.table_profiles.setMaximumHeight(130)
        ph = self.table_profiles.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ph.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        prof_lay.addWidget(self.table_profiles)

        root.addWidget(prof_card)
        root.addStretch()

    def _toggle_tech_button(self) -> None:
        is_visible = self.tech_details_frame.isVisible()
        new_state = not is_visible
        self.tech_details_frame.setVisible(new_state)
        self.chk_show_tech.setChecked(new_state)
        self.btn_toggle_tech.setText(
            "Ocultar detalhes técnicos" if new_state else "Mostrar detalhes técnicos"
        )
        self.db.settings.show_technical_details = new_state
        self.db.settings.save()
        self.refresh_data()

    def _on_toggle_technical_details(self, checked: bool) -> None:
        self.tech_details_frame.setVisible(checked)
        self.btn_toggle_tech.setText(
            "Ocultar detalhes técnicos" if checked else "Mostrar detalhes técnicos"
        )
        self.db.settings.show_technical_details = checked
        self.db.settings.save()
        self.refresh_data()
        self.on_environment_changed()

    def refresh_data(self) -> None:
        db_path = self.db.ensure_connected()
        size_kb = (db_path.stat().st_size / 1024.0) if db_path.exists() else 0.0
        mut_counter = self.db.get_mutation_counter()
        last_mod = self.db.get_last_modified_utc() or "—"
        pal = ThemePalette.for_mode(self.db.settings.theme_mode)

        # Informações amigáveis principais
        self.lbl_active_db.setText(
            f"<b>Arquivo:</b> {db_path.name} ({size_kb:.1f} KB) · "
            f"<span style='color: #1F9D6A;'>Base de dados pronta e operacional</span>"
        )

        # Detalhes técnicos recolhíveis
        self.lbl_tech_info.setText(
            f"Caminho completo: {db_path}<br>"
            f"Contador de mutações gravadas: {mut_counter} | Última gravação: {last_mod}<br>"
            f"Diretório de trabalho: {db_path.parent} | Integridade: PRAGMA synchronous=FULL"
        )

        show_tech = getattr(self.db.settings, "show_technical_details", False)
        self.tech_details_frame.setVisible(show_tech)
        self.btn_toggle_tech.setText(
            "Ocultar detalhes técnicos" if show_tech else "Mostrar detalhes técnicos"
        )

        self.cb_recent_dbs.clear()
        for p in self.db.settings.recent_db_paths:
            self.cb_recent_dbs.addItem(p, p)

        pending = self.backup_service.has_pending_modifications()
        backups = self.backup_service.list_backups()
        last_bkp = self.db.settings.last_backup_timestamp_iso or "Nenhum realizado nesta sessão"
        status_bkp = "Modificações pendentes" if pending else "Tudo sincronizado"

        self.lbl_backup_info.setText(
            f"<b>Status:</b> {status_bkp} · "
            f"<b>Último backup:</b> {last_bkp} · "
            f"<b>Cópias retidas:</b> {len(backups)} / {self.backup_service.RETENTION_LIMIT}"
        )

        self.table_backups.setRowCount(len(backups))
        for idx, bpath in enumerate(reversed(backups)):
            it_name = QTableWidgetItem(bpath.name)
            it_name.setData(Qt.ItemDataRole.UserRole, str(bpath))
            self.table_backups.setItem(idx, 0, it_name)

            mtime = datetime.fromtimestamp(bpath.stat().st_mtime).strftime(
                "%d/%m/%Y %H:%M:%S"
            )
            it_dt = QTableWidgetItem(mtime)
            it_dt.setForeground(QColor(pal.text_secondary))
            self.table_backups.setItem(idx, 1, it_dt)

            sz = f"{bpath.stat().st_size / 1024.0:.1f} KB"
            it_sz = QTableWidgetItem(sz)
            it_sz.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_backups.setItem(idx, 2, it_sz)

        profiles = self.profile_repo.list_profiles(include_archived=False)
        self._profiles = profiles
        self.table_profiles.setRowCount(len(profiles))
        for idx, prof in enumerate(profiles):
            it_p = QTableWidgetItem(
                create_color_badge_icon(prof.color_hex, "", size=14),
                prof.name,
            )
            it_p.setData(Qt.ItemDataRole.UserRole, prof.id)
            f_p = it_p.font()
            if prof.current == "S":
                f_p.setBold(True)
            it_p.setFont(f_p)
            self.table_profiles.setItem(idx, 0, it_p)

            it_curr = QTableWidgetItem(prof.currency)
            it_curr.setForeground(QColor(pal.text_secondary))
            self.table_profiles.setItem(idx, 1, it_curr)

            it_hex = QTableWidgetItem(prof.color_hex)
            it_hex.setForeground(QColor(pal.text_secondary))
            self.table_profiles.setItem(idx, 2, it_hex)

            # Badge de situação
            is_active = prof.current == "S"
            badge = Badge(
                "Ativo" if is_active else "Disponível",
                variant="success" if is_active else "neutral",
            )
            c_w = QWidget()
            c_lay = QHBoxLayout(c_w)
            c_lay.setContentsMargins(4, 4, 4, 4)
            c_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lay.addWidget(badge)
            self.table_profiles.setCellWidget(idx, 3, c_w)

    def action_create_new_database(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Criar Novo Banco de Dados",
            str(Path(self.db.settings.active_db_path).parent / "novo_banco.sqlite"),
            "Banco de Dados SQLite (*.sqlite *.db *.sqlite3)",
        )
        if not file_path:
            return
        try:
            created = self.db.create_new_database(file_path, overwrite=True)
            self.refresh_data()
            self.on_environment_changed()
            QMessageBox.information(
                self,
                "Base Criada com Sucesso",
                f"Novo banco de dados criado e ativado:\n{created.name}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao Criar Base", str(exc))

    def action_open_existing_database(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Carregar Banco de Dados Existente",
            str(Path(self.db.settings.active_db_path).parent),
            "Banco de Dados SQLite (*.sqlite *.db *.sqlite3 *.s3db);;Todos os Arquivos (*.*)",
        )
        if not file_path:
            return
        try:
            opened = self.db.open_existing_database(file_path)
            self.refresh_data()
            self.on_environment_changed()
            QMessageBox.information(
                self,
                "Base Carregada com Sucesso",
                f"Banco de dados ativo alterado para:\n{opened.name}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao Abrir Base", str(exc))

    def _on_switch_recent_db(self) -> None:
        selected_path = self.cb_recent_dbs.currentData()
        if not selected_path:
            return
        try:
            self.db.open_existing_database(selected_path)
            self.refresh_data()
            self.on_environment_changed()
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao Alternar Base", str(exc))

    def action_select_backup_directory(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta de Backup",
            str(self.backup_service.backup_dir),
        )
        if not folder:
            return
        self.backup_service.set_backup_directory(folder)
        self.refresh_data()

    def _run_backup(self, force: bool = False) -> None:
        res = self.backup_service.run_backup_cycle(force=force)
        self.refresh_data()
        if res.performed and res.created_file:
            QMessageBox.information(
                self,
                "Backup Realizado",
                f"Cópia de segurança criada com sucesso:\n{res.created_file.name}\n\n"
                f"Total de cópias mantidas na pasta: {len(res.retained_files)} / 6",
            )
        else:
            QMessageBox.information(
                self,
                "Backup em Dia",
                "Não há modificações pendentes no banco de dados desde o último backup.",
            )

    def _on_restore_selected_backup(self) -> None:
        row = self.table_backups.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Selecione uma Cópia",
                "Selecione uma das cópias na tabela para restaurar.",
            )
            return
        it = self.table_backups.item(row, 0)
        bkp_path = it.data(Qt.ItemDataRole.UserRole)
        ans = QMessageBox.question(
            self,
            "Confirmar Restauração",
            f"Deseja realmente restaurar o banco de dados a partir de:\n{Path(bkp_path).name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.backup_service.restore_from_backup(bkp_path)
            self.refresh_data()
            self.on_environment_changed()
            QMessageBox.information(
                self, "Restauração Concluída", "A cópia de segurança foi restaurada com sucesso."
            )

    def _on_new_profile(self) -> None:
        dlg = CategoryItemDialog("Novo Perfil Financeiro", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.profile_repo.create_profile(
                name=dlg.selected_name,
                color_hex=dlg.selected_color,
                set_current=True,
                seed_default_categories=True,
            )
            self.refresh_data()
            self.on_environment_changed()

    def _on_activate_selected_profile(self) -> None:
        row = self.table_profiles.currentRow()
        if row < 0 or row >= len(self._profiles):
            return
        prof = self._profiles[row]
        self.profile_repo.set_active_profile(prof.id)
        self.refresh_data()
        self.on_environment_changed()

    def _on_configure_pin(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "PIN de Segurança",
            "Informe um novo PIN numérico (ou deixe em branco para desativar):",
            QLineEdit.EchoMode.Password,
        )
        if ok:
            self.profile_repo.set_local_pin(text)
            has_pin = self.profile_repo.has_local_pin()
            QMessageBox.information(
                self,
                "Segurança de Acesso",
                "PIN ativado com sucesso." if has_pin else "PIN desativado.",
            )
