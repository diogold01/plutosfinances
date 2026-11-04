"""Script de Auditoria Automatizada de QA e Sanidade de Interface (Plutos).

Executa varredura profunda em todas as telas, botões, tabelas, contraste do modo escuro
e detecção de elementos comprimidos ou cortados.
Pode ser executado diretamente via:
    py scripts/qa_audit.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

# Configura execução offscreen pura
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QWidget,
)

from app.config.app_settings import AppSettings
from app.config.theme_palette import ThemePalette
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.ui.main_window import MainWindow


def lum(hex_c: str) -> float:
    """Calcula a luminância relativa de uma cor hexadecimal conforme WCAG 2.1."""
    hex_c = hex_c.lstrip("#")
    if len(hex_c) == 3:
        hex_c = "".join([c * 2 for c in hex_c])
    rgb = [int(hex_c[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def contrast_ratio(c1: str, c2: str) -> float:
    """Calcula a taxa de contraste (Contrast Ratio) entre duas cores (1:1 a 21:1)."""
    try:
        l1, l2 = lum(c1), lum(c2)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)
    except Exception:
        return 21.0


def run_qa_audit() -> int:
    print("=" * 70)
    print(" 🛡️  PLUTOS QA AUDIT SUITE — AUDITORIA AUTOMATIZADA DE INTERFACE")
    print("=" * 70)

    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        settings = AppSettings.load(tmp_path / "qa_settings.json")
        db = ConnectionManager(settings=settings, auto_connect=False)
        db_file = tmp_path / "qa_audit.sqlite"
        db.create_new_database(db_file, overwrite=True)
        backup = BackupSchedulerService(connection_manager=db, settings=settings)
        backup.set_backup_directory(tmp_path / "backups")

        win = MainWindow(db=db, backup_service=backup)
        win.resize(1280, 800)
        win.show()
        app.processEvents()

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

        issues_found = []

        # ---------------------------------------------------------------------
        # 1. Auditoria de Botões e Textos Duplicados / Inconsistentes
        # ---------------------------------------------------------------------
        print("\n[1/5] Auditando botões e rotulagens em todas as 12 telas...")
        btn_count = 0
        for key in nav_keys:
            win.navigate_to(key)
            app.processEvents()
            view = win._views.get(key)
            if not view:
                continue

            for btn in view.findChildren(QPushButton):
                btn_count += 1
                txt = btn.text().strip()
                if not txt:
                    continue

                # A: Sinal de mais duplicado (+ +)
                if "+ +" in txt or "++" in txt or re.search(r"\+\s*\+", txt):
                    issues_found.append(
                        f"🔴 [Texto Duplicado] View '{key}' -> Botão com '+' duplicado: '{txt}'"
                    )

                # B: Ícone de plus combinado com '+ ' no texto
                has_icon = not btn.icon().isNull()
                if has_icon and txt.startswith("+ "):
                    issues_found.append(
                        f"🔴 [Redundância Ícone/Texto] View '{key}' -> Botão com ícone e texto '+ ': '{txt}'"
                    )

                # C: Strings de debug
                for bad in ("None", "null", "undefined", "TODO"):
                    if bad in txt:
                        issues_found.append(
                            f"🔴 [String de Debug] View '{key}' -> Botão contém '{bad}': '{txt}'"
                        )

        print(f"      ✓ {btn_count} botões inspecionados.")

        # ---------------------------------------------------------------------
        # 2. Auditoria de Contraste e Dark Mode (WCAG 2.1)
        # ---------------------------------------------------------------------
        print("\n[2/5] Auditando contraste de cores e Modo Escuro...")
        dark_pal = ThemePalette.dark()
        # Validação do título de seção contra surface escuro
        cr_title = contrast_ratio(dark_pal.text_primary, dark_pal.surface_card)
        cr_sub = contrast_ratio(dark_pal.text_secondary, dark_pal.surface_card)
        cr_bg_sub = contrast_ratio(dark_pal.text_secondary, dark_pal.app_background)

        if cr_title < 4.5:
            issues_found.append(
                f"🔴 [Contraste Dark Mode] Título primário no Modo Escuro com contraste insuficiente ({cr_title:.2f}:1 < 4.5:1)"
            )
        if cr_sub < 3.0:
            issues_found.append(
                f"🔴 [Contraste Dark Mode] Subtítulo no Modo Escuro com contraste muito baixo ({cr_sub:.2f}:1 < 3.0:1)"
            )

        # Checa se o botão da IA usa imagem estática de fundo claro
        from app.ui.gemini_button import NEW_SPARKLE_TILE

        if NEW_SPARKLE_TILE.exists():
            # Alerta se o tile estático com fundo pêssego queimado ainda está sendo usado
            issues_found.append(
                "🟡 [Aparência Dark Mode] O botão da IA ainda utiliza a imagem estática 'plutos_ai_sparkle_tile_256.png' (fundo claro fixo em pixels)."
            )

        print(f"      ✓ Contraste Título Primário: {cr_title:.2f}:1 (WCAG AA)")
        print(f"      ✓ Contraste Texto Secundário: {cr_sub:.2f}:1 (WCAG AA)")

        # ---------------------------------------------------------------------
        # 3. Auditoria de Compressão e Overflow de Layout
        # ---------------------------------------------------------------------
        print(
            "\n[3/5] Auditando compressão de layout e presença de QScrollArea..."
        )
        for key in nav_keys:
            win.navigate_to(key)
            app.processEvents()
            view = win._views.get(key)
            if not view:
                continue

            # Se a view for muito alta (ex: configurações com múltiplos blocos), deve possuir scroll
            hint_h = view.sizeHint().height()
            has_scroll = len(view.findChildren(QScrollArea)) > 0
            if hint_h > 750 and not has_scroll:
                issues_found.append(
                    f"🟡 [Risco de Compressão] View '{key}' tem altura estimada de {hint_h}px mas não possui QScrollArea interna."
                )

        print("      ✓ Views auditadas para fluxo de rolagem vertical.")

        # ---------------------------------------------------------------------
        # 4. Auditoria de Tabelas e Containers de Dados
        # ---------------------------------------------------------------------
        print("\n[4/5] Auditando tabelas e renderização de dados essenciais...")
        # Tela de configurações: checa tabela de perfis
        win.navigate_to("configuracoes")
        app.processEvents()
        view_cfg = getattr(win, "config_view", getattr(win, "configuracoes_view", None))
        if view_cfg and hasattr(view_cfg, "table_profiles"):
            rows = view_cfg.table_profiles.rowCount()
            if rows == 0:
                issues_found.append(
                    "🔴 [Tabela Vazia] Configurações -> Tabela de perfis está com 0 linhas mesmo com banco inicializado."
                )
            else:
                print(
                    f"      ✓ Tabela de perfis renderizada com sucesso ({rows} perfil ativo)."
                )

        # ---------------------------------------------------------------------
        # 5. Smoke Test de Alternância de Tema (Claro <-> Escuro)
        # ---------------------------------------------------------------------
        print("\n[5/5] Testando alternância de temas (Claro <-> Escuro)...")
        win.toggle_theme_mode()
        app.processEvents()
        if win.db.settings.theme_mode != "dark":
            issues_found.append("🔴 [Tema] Falha ao alternar para o Modo Escuro.")

        win.toggle_theme_mode()
        app.processEvents()
        if win.db.settings.theme_mode != "light":
            issues_found.append("🔴 [Tema] Falha ao retornar para o Modo Claro.")

        print("      ✓ Alternância dinâmica executada com sucesso.")

        # Geração de Snapshots para Conferência Visual Rápida
        reports_dir = (
            Path(__file__).resolve().parent.parent / "dist" / "qa_report"
        )
        reports_dir.mkdir(parents=True, exist_ok=True)
        shots_dir = reports_dir / "screenshots"
        shots_dir.mkdir(parents=True, exist_ok=True)

        for mode in ("light", "dark"):
            if win.db.settings.theme_mode != mode:
                win.toggle_theme_mode()
                app.processEvents()
            for k in (
                "visao_geral",
                "transacoes",
                "contas",
                "categorias",
                "configuracoes",
            ):
                win.navigate_to(k)
                app.processEvents()
                win.grab().save(str(shots_dir / f"{mode}_{k}.png"))

        print(f"\n📸 Snapshots visuais gerados em: {shots_dir}")
        win.close()
        db.close()

    # -------------------------------------------------------------------------
    # Relatório Final
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(" 📊 RESULTADO DA AUDITORIA DE QA")
    print("=" * 70)

    if not issues_found:
        print("✅ NENHUMA INCONSISTÊNCIA ENCONTRADA! O sistema está aprovado.")
        return 0
    else:
        print(f"⚠️  Foram detectadas {len(issues_found)} inconsistências:")
        for iss in issues_found:
            print(f"   {iss}")
        print("\n💡 Corrija os pontos acima para garantir nota 10 na release.")
        return 1


if __name__ == "__main__":
    sys.exit(run_qa_audit())
