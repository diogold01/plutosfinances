"""Suíte de testes automatizados da Etapa 3 (Shell PySide6, Temas, Perfis, Categorias, Tags e Contas/Saldos)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.config.app_settings import AppSettings
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.profile_repository import ProfileRepository
from app.database.repositories.tag_repository import TagRepository
from app.ui.bank_icons import list_available_bank_icons
from app.ui.main_window import MainWindow
from app.ui.style_manager import format_currency


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_profile_repository_and_local_pin(tmp_path: Path) -> None:
    """Valida criação de perfis isolados, clonagem de categorias semente e PIN local."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(tmp_path / "perfis.sqlite")

    prof_repo = ProfileRepository(db)
    cat_repo = CategoryRepository(db)

    active = prof_repo.get_active_profile()
    assert active.id == "1"
    assert active.name == "Pessoal"

    # Cria novo perfil 'Empresa' e clona taxonomia padrão
    emp = prof_repo.create_profile(
        name="Empresa",
        color_hex="#17A05E",
        set_current=True,
        seed_default_categories=True,
    )
    assert prof_repo.get_active_profile().id == emp.id
    assert len(cat_repo.list_expense_categories(emp.id)) == 11
    assert len(cat_repo.list_income_categories(emp.id)) == 8
    assert len(cat_repo.list_account_categories(emp.id)) == 4

    # PIN local
    assert prof_repo.has_local_pin() is False
    prof_repo.set_local_pin("4321")
    assert prof_repo.has_local_pin() is True
    assert prof_repo.verify_local_pin("4321") is True
    assert prof_repo.verify_local_pin("0000") is False
    prof_repo.set_local_pin("")
    assert prof_repo.has_local_pin() is False
    db.close()


def test_category_and_subcategory_crud(tmp_path: Path) -> None:
    """Valida CRUD de Categorias e Subcategorias de Despesas, Receitas e Contas."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(tmp_path / "cats.sqlite")
    repo = CategoryRepository(db)

    new_cat = repo.create_category("DESPESA", "Pets", "#26A69A", profile_id="1")
    assert new_cat.nome == "Pets"
    assert len(new_cat.subcategories) == 1
    assert new_cat.subcategories[0].nome == "Outros"

    sub = repo.create_subcategory(
        "DESPESA", new_cat.id, "Ração e Veterinário", "#26A69A", profile_id="1"
    )
    all_desp = repo.list_expense_categories("1")
    pets_found = [c for c in all_desp if c.id == new_cat.id][0]
    assert len(pets_found.subcategories) == 2

    repo.update_subcategory("DESPESA", sub.id, "Veterinário", "#00897B")
    repo.delete_subcategory("DESPESA", sub.id, soft=True)
    pets_after = [c for c in repo.list_expense_categories("1") if c.id == new_cat.id][0]
    assert len(pets_after.subcategories) == 1
    db.close()


def test_tag_repository_crud_and_usage_counts(tmp_path: Path) -> None:
    """Valida CRUD de Tags, arquivamento e contagem de vínculos em transações."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(tmp_path / "tags.sqlite")
    repo = TagRepository(db)

    t1 = repo.create_tag("#viagem", "#3F51B5", profile_id="1")
    t2 = repo.create_tag("trabalho", "#17A05E", profile_id="1")
    assert t1.nome == "viagem"

    repo.set_transaction_tags("tx_001", "DESPESA", [t1.id, t2.id])
    repo.set_transaction_tags("tx_002", "DESPESA", [t1.id])

    listed = repo.list_tags("1")
    assert len(listed) == 2
    assert listed[0].id == t1.id
    assert listed[0].utilizacoes == 2
    assert listed[1].utilizacoes == 1

    repo.update_tag(t2.id, "trabalho_remoto", "#17A05E", arquivada="S")
    assert len(repo.list_tags("1", include_archived=False)) == 1
    assert len(repo.list_tags("1", include_archived=True)) == 2

    repo.delete_tag(t1.id)
    assert len(repo.list_tags("1", include_archived=True)) == 1
    db.close()


def test_account_repository_monthly_balances_and_reconciliation(
    tmp_path: Path,
) -> None:
    """Valida criação de contas, saldos iniciais mensais, fluxos de entrada/saída e reconciliação."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(tmp_path / "contas.sqlite")
    repo = AccountRepository(db)

    acc_id = repo.create_account(
        descricao="Nubank Conta",
        id_categoria="3",
        saldo_inicial=1000.00,
        cheque_especial=500.00,
        padrao="S",
        fav=1,
        image_key="ic_nubank.png",
        profile_id="1",
        mes_inicial=10,
        ano_inicial=2026,
    )

    # Insere 1 receita efetivada (R$ 3000), 1 receita pendente (R$ 500),
    # 1 despesa paga (R$ 800) e 1 despesa pendente (R$ 200) em Outubro/2026
    db.execute_write(
        """
        INSERT INTO receitas (id, id_profile, id_conta, descricao, valor, data, efetivado, recorrencia)
        VALUES ('r1', '1', ?, 'Salário', 3000.00, '2026-10-05', 'S', 'U'),
               ('r2', '1', ?, 'Bônus', 500.00, '2026-10-25', 'N', 'U')
        """,
        (acc_id, acc_id),
    )
    db.execute_write(
        """
        INSERT INTO despesas (id, id_profile, id_conta, descricao, valor, data, status, recorrencia, contabilizar)
        VALUES ('d1', '1', ?, 'Aluguel', 800.00, '2026-10-10', 'pg', 'U', 'S'),
               ('d2', '1', ?, ' Luz', 200.00, '2026-10-20', 'pd', 'U', 'S')
        """,
        (acc_id, acc_id),
    )

    summary = repo.get_account_summary(acc_id, mes=10, ano=2026)
    assert summary is not None
    assert summary.saldo_inicial == pytest.approx(1000.00)
    assert summary.receitas_efetivadas == pytest.approx(3000.00)
    assert summary.despesas_pagas == pytest.approx(800.00)
    assert summary.saldo_atual == pytest.approx(3200.00)  # 1000 + 3000 - 800
    assert summary.saldo_previsto == pytest.approx(3500.00)  # 3200 + 500 - 200
    assert summary.disponivel_com_cheque_especial == pytest.approx(3700.00)

    # Verifica propagação automática de Saldo Inicial para o mês seguinte (Novembro/2026)
    summary_nov = repo.get_account_summary(acc_id, mes=11, ano=2026)
    assert summary_nov is not None
    assert summary_nov.saldo_inicial == pytest.approx(3200.00)

    # Reconcilia o saldo confirmado de Outubro/2026 para R$ 3.450,00
    new_si = repo.reconcile_account_balance(acc_id, 10, 2026, 3450.00)
    assert new_si == pytest.approx(1250.00)
    summary_after = repo.get_account_summary(acc_id, mes=10, ano=2026)
    assert summary_after is not None
    assert summary_after.saldo_atual == pytest.approx(3450.00)
    db.close()


def test_native_main_window_navigation_and_views(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida a instanciação e navegação da MainWindow nativa PySide6 em modo offscreen."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(tmp_path / "ui_test.sqlite")
    backup = BackupSchedulerService(connection_manager=db, settings=settings)
    backup.set_backup_directory(tmp_path / "backups")

    banks = list_available_bank_icons()
    assert len(banks) >= 150
    assert format_currency(1234.56) == "R$ 1.234,56"

    win = MainWindow(db=db, backup_service=backup)
    win.navigate_to("contas")
    assert win.current_nav_key == "contas"

    win.navigate_to("categorias")
    assert win.current_nav_key == "categorias"
    assert win.categorias_view.tree_despesas.topLevelItemCount() == 11
    assert win.categorias_view.tree_receitas.topLevelItemCount() == 8
    assert win.categorias_view.tree_contas.topLevelItemCount() == 4

    win.navigate_to("tags")
    assert win.current_nav_key == "tags"

    win.navigate_to("configuracoes")
    assert win.current_nav_key == "configuracoes"

    # Alterna período mensal e tema
    win.go_next_month()
    win.go_previous_month()
    win.toggle_theme_mode()
    assert settings.theme_mode == "dark"
    win.toggle_sidebar()
    assert settings.sidebar_collapsed is True

    win.close()
    db.close()


def test_global_components_and_styles(qapp: QApplication) -> None:
    """Valida os componentes visuais globais (Badges, KpiCards, EmptyStates, BaseModal) e folha QSS."""
    from app.config.theme_palette import ThemePalette
    from app.ui.components import Badge, KpiCard, EmptyStateWidget, BaseModalDialog
    from app.ui.style_manager import build_stylesheet

    # 1. Badges
    b_ok = Badge("Efetivada", "success")
    assert b_ok.objectName() == "BadgeSuccess"
    assert b_ok.text() == "Efetivada"

    b_alert = Badge("Pendente", "warning")
    assert b_alert.objectName() == "BadgeWarning"

    b_danger = Badge("Atrasada", "danger")
    assert b_danger.objectName() == "BadgeDanger"

    # 2. KpiCard
    kpi = KpiCard("Saldo em Contas", "R$ 3.450,00", "positive")
    assert kpi.lbl_title.text() == "Saldo em Contas"
    assert "3.450,00" in kpi.lbl_value.text()
    kpi.update_value("R$ 2.000,00", "negative")
    assert "2.000,00" in kpi.lbl_value.text()

    # 3. EmptyStateWidget
    cb_called = []
    empty = EmptyStateWidget(
        title="Nenhum lançamento",
        subtitle="Adicione uma despesa ou receita para começar",
        icon_name="list",
        action_text="Novo Lançamento",
        action_callback=lambda: cb_called.append(True),
    )
    assert empty.lbl_title.text() == "Nenhum lançamento"

    # 4. BaseModalDialog
    dlg = BaseModalDialog(title="Novo Item", subtitle="Preencha os dados abaixo")
    assert dlg.windowTitle() == "Novo Item"
    assert dlg.btn_confirm.text() == "Confirmar"
    assert dlg.btn_cancel.text() == "Cancelar"

    # 5. Folha de estilo QSS
    pal = ThemePalette.light()
    qss = build_stylesheet(pal)
    assert "QCheckBox" in qss
    assert "QRadioButton" in qss
    assert "QDialogButtonBox" in qss
    assert "QToolTip" in qss
    assert "QGroupBox" in qss
    assert "QMessageBox" in qss
    assert pal.primary in qss

