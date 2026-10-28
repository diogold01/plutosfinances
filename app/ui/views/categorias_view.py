"""Tela de Categorias e Subcategorias (`CategoriasView`)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.theme_palette import CATEGORY_SWATCH_COLORS
from app.database.connection_manager import ConnectionManager
from app.database.repositories.category_repository import (
    CategoryDTO,
    CategoryRepository,
)
from app.ui.bank_icons import create_color_badge_icon
from app.ui.icons import get_line_icon


class CategoryItemDialog(QDialog):
    """Modal limpo para criar ou editar Categoria ou Subcategoria com seletor visual de cores."""

    def __init__(
        self,
        title: str,
        initial_name: str = "",
        initial_color: str = "#2196F3",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.selected_name = initial_name
        self.selected_color = initial_color

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_head = QLabel(title)
        lbl_head.setObjectName("SectionTitle")
        lbl_sub = QLabel("Informe o nome e selecione uma cor de identificação visual.")
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_head)
        title_box.addWidget(lbl_sub)
        root.addLayout(title_box)

        form = QFormLayout()
        form.setSpacing(12)

        self.ed_name = QLineEdit(initial_name)
        self.ed_name.setPlaceholderText("Ex.: Alimentação, Moradia, Transporte...")
        form.addRow("Nome:", self.ed_name)

        self.cb_color = QComboBox()
        self.cb_color.setIconSize(QSize(18, 18))
        for hex_col in CATEGORY_SWATCH_COLORS:
            self.cb_color.addItem(
                create_color_badge_icon(hex_col, size=16), hex_col, hex_col
            )
        idx = self.cb_color.findData(initial_color.upper())
        if idx >= 0:
            self.cb_color.setCurrentIndex(idx)
        form.addRow("Cor de Destaque:", self.cb_color)
        root.addLayout(form)

        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setObjectName("SecondaryButton")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Salvar")
        btn_ok.setObjectName("PrimaryButton")
        btn_ok.clicked.connect(self._on_save)

        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        root.addLayout(btns)

    def _on_save(self) -> None:
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Campo Obrigatório", "Informe o nome.")
            return
        self.selected_name = name
        self.selected_color = str(self.cb_color.currentData() or "#2196F3")
        self.accept()


class CategoriasView(QWidget):
    """Vista hierárquica de Categorias e Subcategorias (Despesas, Receitas e Contas)."""

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
        self.cat_repo = CategoryRepository(db)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        top_bar = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        lbl_title = QLabel("Categorias")
        lbl_title.setObjectName("SectionTitle")
        lbl_sub = QLabel(
            "Organize a taxonomia de despesas, receitas e contas bancárias"
        )
        lbl_sub.setObjectName("MutedText")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        top_bar.addLayout(title_box)
        top_bar.addStretch()

        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)

        self.btn_new_sub = QPushButton("+ Nova Subcategoria")
        self.btn_new_sub.setObjectName("SecondaryButton")
        self.btn_new_sub.setIcon(get_line_icon("plus", size=14))
        self.btn_new_sub.clicked.connect(self._on_new_subcategory)

        self.btn_edit = QPushButton("Editar")
        self.btn_edit.setObjectName("SecondaryButton")
        self.btn_edit.setIcon(get_line_icon("pencil", size=14))
        self.btn_edit.clicked.connect(self._on_edit_selected)

        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.setObjectName("SecondaryButton")
        self.btn_delete.setIcon(get_line_icon("trash", size=14))
        self.btn_delete.clicked.connect(self._on_delete_selected)

        self.btn_new_cat = QPushButton("+ Nova Categoria")
        self.btn_new_cat.setObjectName("PrimaryButton")
        self.btn_new_cat.setIcon(get_line_icon("plus", size=14, color="#FFFFFF"))
        self.btn_new_cat.clicked.connect(self._on_new_category)

        btns_row.addWidget(self.btn_edit)
        btns_row.addWidget(self.btn_delete)
        btns_row.addWidget(self.btn_new_sub)
        btns_row.addWidget(self.btn_new_cat)
        top_bar.addLayout(btns_row)
        root.addLayout(top_bar)

        self.tabs = QTabWidget()
        self.tree_despesas = self._create_tree()
        self.tree_receitas = self._create_tree()
        self.tree_contas = self._create_tree()

        self.tabs.addTab(self.tree_despesas, "Despesas")
        self.tabs.addTab(self.tree_receitas, "Receitas")
        self.tabs.addTab(self.tree_contas, "Contas")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, stretch=1)

    def _create_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels(["Categoria / Subcategoria", "Tipo", "Cor"])
        tree.setIconSize(QSize(18, 18))
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tree.itemDoubleClicked.connect(lambda _it, _col: self._on_edit_selected())
        return tree

    def _current_kind_and_tree(self) -> tuple[str, QTreeWidget]:
        idx = self.tabs.currentIndex()
        if idx == 0:
            return "DESPESA", self.tree_despesas
        if idx == 1:
            return "RECEITA", self.tree_receitas
        return "CONTA", self.tree_contas

    def _on_tab_changed(self, idx: int) -> None:
        self.btn_new_sub.setEnabled(idx in (0, 1))

    def refresh_data(self) -> None:
        profile_id, _, _, search_text = self.get_context()
        query = search_text.strip().lower()

        self._populate_tree(
            self.tree_despesas,
            self.cat_repo.list_expense_categories(profile_id),
            query,
        )
        self._populate_tree(
            self.tree_receitas,
            self.cat_repo.list_income_categories(profile_id),
            query,
        )
        self._populate_tree(
            self.tree_contas,
            self.cat_repo.list_account_categories(profile_id),
            query,
        )

    def _populate_tree(
        self,
        tree: QTreeWidget,
        categories: list[CategoryDTO],
        query: str,
    ) -> None:
        tree.clear()
        for cat in categories:
            matching_subs = [
                s
                for s in cat.subcategories
                if not query
                or query in s.nome.lower()
                or query in cat.nome.lower()
            ]
            if query and query not in cat.nome.lower() and not matching_subs:
                continue

            sub_count = f" ({len(cat.subcategories)})" if cat.subcategories else ""
            cat_item = QTreeWidgetItem(
                [
                    f"{cat.nome}{sub_count}",
                    f"Categoria ({cat.kind.title()})",
                    cat.color_hex,
                ]
            )
            cat_item.setIcon(
                0, create_color_badge_icon(cat.color_hex, "", size=16)
            )
            cat_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "node_type": "category",
                    "kind": cat.kind,
                    "id": cat.id,
                    "nome": cat.nome,
                    "color_hex": cat.color_hex,
                },
            )
            f_bold = cat_item.font(0)
            f_bold.setBold(True)
            cat_item.setFont(0, f_bold)

            for sub in matching_subs:
                sub_item = QTreeWidgetItem(
                    [sub.nome, "Subcategoria", sub.color_hex]
                )
                sub_item.setIcon(
                    0, create_color_badge_icon(sub.color_hex, "", size=12)
                )
                sub_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "node_type": "subcategory",
                        "kind": cat.kind,
                        "id": sub.id,
                        "id_categoria": cat.id,
                        "nome": sub.nome,
                        "color_hex": sub.color_hex,
                    },
                )
                cat_item.addChild(sub_item)

            tree.addTopLevelItem(cat_item)
            cat_item.setExpanded(True)

    def _on_new_category(self) -> None:
        profile_id, _, _, _ = self.get_context()
        kind, _ = self._current_kind_and_tree()
        dlg = CategoryItemDialog(f"Nova Categoria ({kind.title()})", parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cat_repo.create_category(
                kind=kind,
                nome=dlg.selected_name,
                color_hex=dlg.selected_color,
                profile_id=profile_id,
            )
            self.refresh_data()
            if self.on_data_mutated:
                self.on_data_mutated()

    def _on_new_subcategory(self) -> None:
        profile_id, _, _, _ = self.get_context()
        kind, tree = self._current_kind_and_tree()
        if kind == "CONTA":
            return
        cur = tree.currentItem()
        if cur is None:
            QMessageBox.information(
                self,
                "Selecione uma Categoria",
                "Selecione uma categoria principal na árvore para adicionar uma subcategoria.",
            )
            return
        meta = cur.data(0, Qt.ItemDataRole.UserRole) or {}
        cat_id = (
            meta["id"]
            if meta.get("node_type") == "category"
            else meta.get("id_categoria")
        )
        default_col = meta.get("color_hex", "#2196F3")
        dlg = CategoryItemDialog(
            f"Nova Subcategoria ({kind.title()})",
            initial_color=default_col,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.cat_repo.create_subcategory(
                kind=kind,
                category_id=str(cat_id),
                nome=dlg.selected_name,
                color_hex=dlg.selected_color,
                profile_id=profile_id,
            )
            self.refresh_data()
            if self.on_data_mutated:
                self.on_data_mutated()

    def _on_edit_selected(self) -> None:
        kind, tree = self._current_kind_and_tree()
        cur = tree.currentItem()
        if cur is None:
            QMessageBox.information(
                self, "Seleção", "Selecione uma categoria ou subcategoria para editar."
            )
            return
        meta = cur.data(0, Qt.ItemDataRole.UserRole) or {}
        dlg = CategoryItemDialog(
            f"Editar {meta.get('nome', '')}",
            initial_name=meta.get("nome", ""),
            initial_color=meta.get("color_hex", "#2196F3"),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if meta.get("node_type") == "category":
                self.cat_repo.update_category(
                    kind=kind,
                    category_id=str(meta["id"]),
                    nome=dlg.selected_name,
                    color_hex=dlg.selected_color,
                )
            else:
                self.cat_repo.update_subcategory(
                    kind=kind,
                    subcategory_id=str(meta["id"]),
                    nome=dlg.selected_name,
                    color_hex=dlg.selected_color,
                )
            self.refresh_data()
            if self.on_data_mutated:
                self.on_data_mutated()

    def _on_delete_selected(self) -> None:
        kind, tree = self._current_kind_and_tree()
        cur = tree.currentItem()
        if cur is None:
            return
        meta = cur.data(0, Qt.ItemDataRole.UserRole) or {}
        ans = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Deseja excluir '{meta.get('nome', '')}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            if meta.get("node_type") == "category":
                self.cat_repo.delete_category(kind, str(meta["id"]), soft=True)
            else:
                self.cat_repo.delete_subcategory(kind, str(meta["id"]), soft=True)
            self.refresh_data()
            if self.on_data_mutated:
                self.on_data_mutated()
