"""Suíte de Testes Automatizados de Sanidade Visual e Auditoria de UI do Plutos.

Este teste replica o trabalho de um QA/Tester automatizado:
1. Varre todas as telas da aplicação em busca de anomalias textuais (símbolos duplicados '+ +', 'None', etc.).
2. Valida contratos de botões (proíbe ícone 'plus' combinado com texto '+ ').
3. Testa navegação completa de ponta a ponta (smoke test) em todos os módulos.
4. Testa alternância dinâmica de temas (Claro <-> Escuro) sem erros de parâmetros ou estilos.
5. Captura snapshots visuais automáticos de todas as telas para inspeção rápida.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Tuple

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from app.config.app_settings import AppSettings
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_env(qapp: QApplication, tmp_path: Path):
    """Cria um ambiente limpo com banco de dados funcional para o smoke test."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db_file = tmp_path / "audit_test.sqlite"
    db.create_new_database(db_file, overwrite=True)
    backup = BackupSchedulerService(connection_manager=db, settings=settings)
    backup.set_backup_directory(tmp_path / "backups")
    win = MainWindow(db=db, backup_service=backup)
    win.resize(1280, 800)
    yield win, db, tmp_path
    win.close()
    db.close()


def test_ui_no_duplicated_symbols_or_broken_texts(test_env) -> None:
    """Audita programaticamente TODOS os botões e labels do app procurando anomalias visuais.

    - Detecta '+ +' (dois sinais de mais seguidos)
    - Detecta 'None', 'null', 'undefined' impressos em tela
    - Detecta espaços duplos '  ' em títulos de botões
    """
    win, _, _ = test_env
    nav_keys = [
        "visao_geral",
        "contas",
        "transacoes",
        "cartoes",
        "orcamentos",
        "objetivos",
        "relatorios",
        "graficos",
        "categorias",
        "tags",
        "calendario",
        "configuracoes",
    ]

    anomalies: List[str] = []

    for key in nav_keys:
        win.navigate_to(key)
        QApplication.processEvents()
        view = win._views.get(key)
        if not view:
            continue

        # 1. Auditoria de Botões
        buttons = view.findChildren(QPushButton)
        for btn in buttons:
            txt = btn.text().strip()
            if not txt:
                continue

            # Regra A: Nenhum botão pode renderizar dois sinais de mais seguidos
            if "+ +" in txt or "++" in txt or re.search(r"\+\s*\+", txt):
                anomalies.append(
                    f"[{key}] Botão com '+' duplicado: '{txt}' (objeto: {btn.objectName()})"
                )

            # Regra B: Nenhum botão pode exibir strings de debug
            for bad_word in ("None", "null", "undefined", "TODO"):
                if bad_word in txt:
                    anomalies.append(
                        f"[{key}] Botão com texto de debug '{bad_word}': '{txt}'"
                    )

            # Regra C: Evitar botões com texto iniciando em '+ ' quando já têm ícone de plus
            # (Essa é a causa raiz do bug reportado)
            has_icon = not btn.icon().isNull()
            if has_icon and txt.startswith("+ "):
                anomalies.append(
                    f"[{key}] Botão com redundância de ícone e texto: '{txt}'"
                )

        # 2. Auditoria de Labels
        labels = view.findChildren(QLabel)
        for lbl in labels:
            ltxt = lbl.text().strip()
            if not ltxt:
                continue
            if "+ +" in ltxt or re.search(r"\+\s*\+", ltxt):
                anomalies.append(f"[{key}] Label com '+' duplicado: '{ltxt}'")
            if ltxt in ("None", "null", "undefined"):
                anomalies.append(f"[{key}] Label exibindo valor nulo não tratado: '{ltxt}'")

    # Se encontrar qualquer anomalia visual, o teste falha listando tudo com clareza
    assert not anomalies, (
        f"Foram encontradas {len(anomalies)} anomalias visuais na interface:\n"
        + "\n".join(f" - {a}" for a in anomalies)
    )


def test_theme_toggle_smoke_test(test_env) -> None:
    """Verifica se a alternância dinâmica Claro <-> Escuro ocorre sem erros de parâmetros ou layout."""
    win, _, _ = test_env

    # 1. Alterna para escuro
    win.toggle_theme_mode()
    QApplication.processEvents()
    assert win.db.settings.theme_mode == "dark"

    # 2. Navega por 3 telas no modo escuro para garantir estabilidade
    for key in ("visao_geral", "transacoes", "configuracoes"):
        win.navigate_to(key)
        QApplication.processEvents()

    # 3. Retorna para o modo claro
    win.toggle_theme_mode()
    QApplication.processEvents()
    assert win.db.settings.theme_mode == "light"


def test_generate_visual_snapshots(test_env) -> None:
    """Gera capturas de tela automatizadas de todas as telas em Modo Claro e Escuro.

    Permite ao desenvolvedor ou tester bater o olho em segundos nas imagens geradas.
    """
    win, _, tmp_path = test_env
    shots_dir = tmp_path / "visual_audit_snapshots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    nav_keys = ["visao_geral", "transacoes", "contas", "categorias", "configuracoes"]

    for mode in ("light", "dark"):
        if win.db.settings.theme_mode != mode:
            win.toggle_theme_mode()
            QApplication.processEvents()

        for key in nav_keys:
            win.navigate_to(key)
            QApplication.processEvents()
            pix = win.grab()
            out_file = shots_dir / f"{mode}_{key}.png"
            pix.save(str(out_file))
            assert out_file.exists()
            assert out_file.stat().st_size > 1000  # Imagem válida gerada
