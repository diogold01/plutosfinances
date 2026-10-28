"""Tela de Tags / Marcadores Transversais (`TagsView`)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import ThemePalette
from app.database.connection_manager import ConnectionManager
from app.database.repositories.tag_repository import TagDTO, TagRepository
from app.ui.bank_icons import create_color_badge_icon
from app.ui.components import Badge, EmptyStateWidget
from app.ui.icons import get_line_icon
from app.ui.views.categorias_view import CategoryItemDialog


class TagsView(QWidget):
    """Vista de gerenciamento de Tags com contador de transações vinculadas."""

    def __init__(
        self,
        db: ConnectionManager,
        get_context: Callable[[], tuple[str, int, int, str]],
        on_data_mutated: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        self.get_context = get_context
        self.on_data_mutated = on_data_mutated
        self.tag_repo = TagRepository(db)
        self._tags: list[TagDTO] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        top_bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_title = QLabel("Tags")
        lbl_title.setObjectName("SectionTitle")
        lbl_sub = QLabel(
            "Classifique transações transversalmente (ex.: #viagem, #reembolsavel, #projeto)"
        )
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        top_bar.addLayout(title_box)
        top_bar.addStretch()

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        self.chk_show_archived = QCheckBox("Exibir arquivadas")
        self.chk_show_archived.stateChanged.connect(lambda _: self.refresh_data())

        self.btn_archive = QPushButton("Arquivar / Reativar")
        self.btn_archive.setObjectName("SecondaryButton")
        self.btn_archive.setIcon(get_line_icon("clock", size=14))
        self.btn_archive.clicked.connect(self._on_toggle_archive)

        self.btn_edit = QPushButton("Editar")
        self.btn_edit.setObjectName("SecondaryButton")
        self.btn_edit.setIcon(get_line_icon("pencil", size=14))
        self.btn_edit.clicked.connect(self._on_edit_selected)

        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.setObjectName("SecondaryButton")
        self.btn_delete.setIcon(get_line_icon("trash", size=14))
        self.btn_delete.clicked.connect(self._on_delete_selected)

        self.btn_new = QPushButton("+ Nova Tag")
        self.btn_new.setObjectName("PrimaryButton")
        self.btn_new.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        self.btn_new.clicked.connect(self._on_new_tag)

        btns_row.addWidget(self.chk_show_archived)
        btns_row.addSpacing(6)
        btns_row.addWidget(self.btn_edit)
        btns_row.addWidget(self.btn_archive)
        btns_row.addWidget(self.btn_delete)
        btns_row.addWidget(self.btn_new)
        top_bar.addLayout(btns_row)
        root.addLayout(top_bar)

        self.stack = QStackedWidget()

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Tag", "Cor", "Transações Vinculadas", "Situação"]
        )
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setIconSize(QSize(18, 18))
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemDoubleClicked.connect(lambda _: self._on_edit_selected())
        self.stack.addWidget(self.table)

        self.empty_widget = EmptyStateWidget(
            title="Nenhuma tag cadastrada",
            subtitle="Crie tags para categorizar despesas e receitas por projetos, viagens ou eventos.",
            action_label="+ Nova Tag",
            on_action=self._on_new_tag,
            icon_name="file_text",
        )
        self.stack.addWidget(self.empty_widget)

        root.addWidget(self.stack, stretch=1)

    def refresh_data(self) -> None:
        profile_id, _, _, search_text = self.get_context()
        self._tags = self.tag_repo.list_tags(
            profile_id=profile_id,
            include_archived=self.chk_show_archived.isChecked(),
            search_text=search_text,
        )

        if not self._tags:
            self.table.setRowCount(0)
            self.stack.setCurrentWidget(self.empty_widget)
            self.btn_edit.setEnabled(False)
            self.btn_archive.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return

        self.stack.setCurrentWidget(self.table)
        self.btn_edit.setEnabled(True)
        self.btn_archive.setEnabled(True)
        self.btn_delete.setEnabled(True)

        pal = ThemePalette.for_mode(self.db.settings.theme_mode)
        self.table.setRowCount(len(self._tags))

        for idx, t in enumerate(self._tags):
            it_name = QTableWidgetItem(
                create_color_badge_icon(t.color_hex, "", size=14),
                f"#{t.nome}",
            )
            f_bold = it_name.font()
            f_bold.setBold(True)
            it_name.setFont(f_bold)
            self.table.setItem(idx, 0, it_name)

            it_hex = QTableWidgetItem(t.color_hex)
            it_hex.setForeground(QColor(pal.text_secondary))
            self.table.setItem(idx, 1, it_hex)

            it_count = QTableWidgetItem(str(t.utilizacoes))
            it_count.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_count.setForeground(QColor(pal.text_secondary))
            self.table.setItem(idx, 2, it_count)

            # Badge de situação
            status_variant = "neutral" if t.arquivada == "S" else "success"
            status_label = "Arquivada" if t.arquivada == "S" else "Ativa"
            badge = Badge(status_label, variant=status_variant)
            c_w = QWidget()
            c_lay = QHBoxLayout(c_w)
            c_lay.setContentsMargins(4, 4, 4, 4)
            c_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lay.addWidget(badge)
            self.table.setCellWidget(idx, 3, c_w)

    def _selected_tag(self) -> Optional[TagDTO]:
        r = self.table.currentRow()
        if r < 0 or r >= len(self._tags):
            return None
        return self._tags[r]

    def _on_new_tag(self) -> None:
        profile_id, _, _, _ = self.get_context()
        dlg = CategoryItemDialog("Nova Tag", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.tag_repo.create_tag(
                nome=dlg.selected_name,
                color_hex=dlg.selected_color,
                profile_id=profile_id,
            )
            self.refresh_data()
            if self.on_data_mutated:
                self.on_data_mutated()

    def _on_edit_selected(self) -> None:
        t = self._selected_tag()
        if t is None:
            QMessageBox.information(
                self, "Seleção", "Selecione uma tag na tabela para editar."
            )
            return
        dlg = CategoryItemDialog(
            f"Editar #{t.nome}",
            initial_name=t.nome,
            initial_color=t.color_hex,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.tag_repo.update_tag(
                t.id,
                nome=dlg.selected_name,
                color_hex=dlg.selected_color,
            )
            self.refresh_data()
            if self.on_data_mutated:
                self.on_data_mutated()

    def _on_toggle_archive(self) -> None:
        t = self._selected_tag()
        if t is None:
            QMessageBox.information(
                self, "Seleção", "Selecione uma tag na tabela para arquivar/reativar."
            )
            return
        novo_status = t.arquivada != "S"
        self.tag_repo.set_archived(t.id, archived=novo_status)
        self.refresh_data()
        if self.on_data_mutated:
            self.on_data_mutated()

    def _on_delete_selected(self) -> None:
        t = self._selected_tag()
        if t is None:
            return
        ans = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Deseja excluir a tag '#{t.nome}'? Os lançamentos associados não serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.tag_repo.delete_tag(t.id, soft=True)
            self.refresh_data()
            if self.on_data_mutated:
                self.on_data_mutated()
