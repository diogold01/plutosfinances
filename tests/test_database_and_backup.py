"""Suíte de testes automatizados da Etapa 2 (Ativos, Motor SQLite e Rotina de Backup Online)."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.config.app_settings import (
    BACKUP_INTERVAL_3_HOURS_SECONDS,
    BACKUP_RETENTION_MAX_FILES,
    BANKS_ICONS_DIR,
    CATEGORIAS_MAP_JSON_PATH,
    CREDIT_CARD_ICONS_DIR,
    EXCEL_TEMPLATES_DIR,
    FONTS_DIR,
    SEED_DEFAULT_DB_PATH,
    SQL_ASSETS_DIR,
    AppSettings,
    DateReferenceMode,
)
from app.config.theme_palette import ThemePalette, argb_int_to_hex, hex_to_argb_int
from app.database.backup_service import BackupSchedulerService
from app.database.connection_manager import ConnectionManager


def test_reusable_assets_copied_and_complete() -> None:
    """Verifica se todos os ativos visuais, templates Excel, SQLs e seeds foram organizados em app/assets."""
    assert BANKS_ICONS_DIR.exists()
    bank_icons = list(BANKS_ICONS_DIR.glob("ic_*.*"))
    assert len(bank_icons) >= 150

    assert CREDIT_CARD_ICONS_DIR.exists()
    card_icons = list(CREDIT_CARD_ICONS_DIR.glob("*.png"))
    assert len(card_icons) >= 7

    assert FONTS_DIR.exists()
    assert (FONTS_DIR / "sans_regular.ttf").exists()
    assert (FONTS_DIR / "sans_bold.ttf").exists()

    assert EXCEL_TEMPLATES_DIR.exists()
    xlsx_files = list(EXCEL_TEMPLATES_DIR.glob("*.xlsx"))
    assert len(xlsx_files) == 6

    assert SQL_ASSETS_DIR.exists()
    sql_files = list(SQL_ASSETS_DIR.rglob("*.sql"))
    assert len(sql_files) >= 240

    assert SEED_DEFAULT_DB_PATH.exists()
    assert CATEGORIAS_MAP_JSON_PATH.exists()


def test_color_palette_and_argb_conversions() -> None:
    """Valida a conversão exata dos inteiros ARGB 32-bit com sinal do SQLite para Hexadecimal."""
    assert argb_int_to_hex(-14575885) == "#2196F3"
    assert hex_to_argb_int("#2196F3") == -14575885
    assert argb_int_to_hex(-15228834) == "#17A05E"
    assert hex_to_argb_int("#17A05E") == -15228834
    assert argb_int_to_hex(-1092784) == "#EF5350"
    assert hex_to_argb_int("#EF5350") == -1092784

    light = ThemePalette.for_mode("light")
    dark = ThemePalette.for_mode("dark")
    assert light.primary in ("#E5603D", "#D97757")
    assert dark.mode == "dark"


def test_create_and_switch_databases_across_custom_directories(tmp_path: Path) -> None:
    """
    Requisito 4: Verifica a seleção livre de diretório para criar uma nova base (.db / .sqlite)
    ou carregar uma base existente, validando o esquema relacional e a taxonomia inicial.
    """
    settings_file = tmp_path / "config" / "settings.json"
    dir_a = tmp_path / "pasta_a" / "financas_pessoal.sqlite"
    dir_b = tmp_path / "pasta_b" / "financas_empresa.db"

    settings = AppSettings.load(settings_file)
    db = ConnectionManager(settings=settings, auto_connect=False)

    # 1. Cria primeira base em pasta_a
    created_a = db.create_new_database(dir_a)
    assert created_a == dir_a.resolve()
    assert created_a.exists()

    # Verifica taxonomia inicial (seed)
    profile = db.fetch_one("SELECT id, name, color FROM profiles WHERE id = '1'")
    assert profile is not None
    assert profile["name"] == "Pessoal"
    assert argb_int_to_hex(profile["color"]) == "#2196F3"

    assert db.fetch_scalar("SELECT COUNT(*) FROM contas_cat") == 4
    assert db.fetch_scalar("SELECT COUNT(*) FROM despesas_cat") == 11
    assert db.fetch_scalar("SELECT COUNT(*) FROM despesas_subcat") == 39
    assert db.fetch_scalar("SELECT COUNT(*) FROM receitas_cat") == 8
    assert db.fetch_scalar("SELECT COUNT(*) FROM receitas_subcat") == 13

    # Insere uma conta exclusiva na base A
    db.execute_write(
        """
        INSERT INTO contas (id, descricao, id_categoria, id_profile, exibir_resumo, somar_total, padrao)
        VALUES ('conta_a', 'Conta Exclusiva A', '3', '1', 'S', 'S', 'S')
        """
    )
    assert db.fetch_scalar("SELECT COUNT(*) FROM contas WHERE id = 'conta_a'") == 1

    # 2. Cria segunda base em pasta_b (.db)
    created_b = db.create_new_database(dir_b)
    assert created_b == dir_b.resolve()
    assert created_b.exists()
    assert db.fetch_scalar("SELECT COUNT(*) FROM contas WHERE id = 'conta_a'") == 0

    # 3. Reabre a base A existente e confirma que o dado está íntegro
    reopened_a = db.open_existing_database(dir_a)
    assert reopened_a == dir_a.resolve()
    assert db.fetch_scalar("SELECT COUNT(*) FROM contas WHERE id = 'conta_a'") == 1
    assert str(dir_a.resolve()) in settings.recent_db_paths
    assert str(dir_b.resolve()) in settings.recent_db_paths

    db.close()


def test_immediate_disk_commit_and_rollback_safety(tmp_path: Path) -> None:
    """
    Requisito 4: Garante gravação e confirmação imediata em disco a cada operação
    (zero perda de dados em encerramento súbito) e rollback atômico em falhas.
    """
    settings = AppSettings.load(tmp_path / "settings.json")
    db_file = tmp_path / "imediato.sqlite"
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_file)

    assert db.get_mutation_counter() == 0

    # Executa escrita
    db.execute_write(
        """
        INSERT INTO despesas (id, id_profile, descricao, valor, status, recorrencia, data)
        VALUES ('desp_1', '1', 'Supermercado', 250.75, 'P', 'U', '2026-10-16')
        """
    )
    assert db.get_mutation_counter() == 1

    # Sem fechar `db` (simulando leitura externa imediata ou encerramento abrupto do processo),
    # abre uma segunda conexão independente somente leitura diretamente no arquivo em disco:
    external_conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    try:
        row = external_conn.execute(
            "SELECT descricao, valor FROM despesas WHERE id = 'desp_1'"
        ).fetchone()
        assert row is not None
        assert row[0] == "Supermercado"
        assert row[1] == pytest.approx(250.75)
    finally:
        external_conn.close()

    # Verifica que não há arquivos temporários WAL/SHM pendentes fora do arquivo único
    assert not Path(f"{db_file}-wal").exists()
    assert not Path(f"{db_file}-shm").exists()

    # Testa rollback em caso de exceção no meio de uma transação
    with pytest.raises(RuntimeError):
        with db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO despesas (id, id_profile, descricao, valor, status, recorrencia, data)
                VALUES ('desp_abortada', '1', 'Não deve persistir', 999.99, 'P', 'U', '2026-10-16')
                """
            )
            raise RuntimeError("Simulando erro antes do commit")

    assert (
        db.fetch_scalar("SELECT COUNT(*) FROM despesas WHERE id = 'desp_abortada'")
        == 0
    )
    assert db.get_mutation_counter() == 1
    db.close()


def test_sql_asset_loader_and_three_date_reference_modes(tmp_path: Path) -> None:
    """Verifica o carregamento das queries SQL originais com os modos de data de referência."""
    settings = AppSettings.load(tmp_path / "settings.json")
    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(tmp_path / "sql_test.sqlite")

    for mode in (
        DateReferenceMode.VENCIMENTO,
        DateReferenceMode.LANCAMENTO,
        DateReferenceMode.LANCAMENTO_DISTRIBUIR,
        DateReferenceMode.EFETIVACAO,
    ):
        for rel_query in (
            "orcamentos/listar_mensais_despesas.sql",
            "orcamentos/listar_mensais_receitas.sql",
        ):
            sql = db.load_sql_asset(
                rel_query,
                date_ref_mode=mode,
                extra_params_sql="",
            )
            assert "{param_data_ref}" not in sql
            assert "{params}" not in sql
            rows = db.execute_query(
                sql,
                {
                    "datainicio": "2026-10-01",
                    "somente_resumo": "N",
                    "valor_receitas": 5000.0,
                    "iniciar_fixa_no_lancamento": "N",
                    "mostrar_pais": "S",
                    "mostrar_filhos": "S",
                },
            )
            assert isinstance(rows, list)

    db.close()


def test_backup_service_3h_config_pending_modifications_and_6_file_rotation(
    tmp_path: Path,
) -> None:
    """
    Requisito 5:
    - Configuração de diretório de backup.
    - Intervalo padrão de 3 horas (10.800s).
    - Execução via SQLite Online Backup API apenas se houver modificações pendentes.
    - Retenção estrita de exatamente 6 arquivos com data e hora no nome, descartando o mais antigo.
    """
    settings = AppSettings.load(tmp_path / "settings.json")
    db_file = tmp_path / "db" / "base_principal.sqlite"
    backup_dir = tmp_path / "meus_backups"

    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_file)

    backup_service = BackupSchedulerService(connection_manager=db, settings=settings)
    backup_service.set_backup_directory(backup_dir)

    assert backup_service.interval_seconds == BACKUP_INTERVAL_3_HOURS_SECONDS == 10800
    assert backup_service.RETENTION_LIMIT == BACKUP_RETENTION_MAX_FILES == 6
    assert backup_service.backup_dir == backup_dir.resolve()

    # 1. Banco recém-criado sem modificações não deve gerar backup automático desnecessário
    assert not backup_service.has_pending_modifications()
    res0 = backup_service.run_backup_cycle(force=False)
    assert res0.performed is False
    assert res0.reason == "no_pending_modifications"
    assert len(backup_service.list_backups()) == 0

    # 2. Realiza 1ª modificação -> deve detectar modificação pendente e criar 1º backup
    base_time = datetime(2026, 10, 16, 8, 0, 0)
    db.execute_write(
        "INSERT INTO tags (id, id_profile, nome, cor) VALUES ('tag_1', '1', 'Tag 1', -14575885)"
    )
    assert backup_service.has_pending_modifications() is True

    res1 = backup_service.run_backup_cycle(force=False, timestamp=base_time)
    assert res1.performed is True
    assert res1.reason == "pending_modifications"
    assert res1.created_file is not None
    assert res1.created_file.name == "plutos_backup_2026-10-16_08-00-00.sqlite"
    assert len(backup_service.list_backups()) == 1

    # 3. Sem novas modificações no banco, um novo ciclo 3h depois NÃO deve gerar outro arquivo
    assert backup_service.has_pending_modifications() is False
    res_skip = backup_service.run_backup_cycle(
        force=False, timestamp=base_time + timedelta(hours=3)
    )
    assert res_skip.performed is False
    assert res_skip.reason == "no_pending_modifications"
    assert len(backup_service.list_backups()) == 1

    # 4. Simula mais 7 ciclos de 3 horas COM modificações no banco (total de 8 backups gerados ao longo do tempo)
    created_names: list[str] = [res1.created_file.name]
    for i in range(2, 9):
        cycle_time = base_time + timedelta(hours=3 * (i - 1))
        db.execute_write(
            "INSERT INTO tags (id, id_profile, nome, cor) VALUES (?, '1', ?, -14575885)",
            (f"tag_{i}", f"Tag {i}"),
        )
        assert backup_service.has_pending_modifications() is True
        res = backup_service.run_backup_cycle(force=False, timestamp=cycle_time)
        assert res.performed is True
        assert res.created_file is not None
        created_names.append(res.created_file.name)
        assert len(res.retained_files) <= 6

    # 5. Verifica que exatamente 6 arquivos permanecem no diretório e que os 2 mais antigos foram descartados
    final_backups = backup_service.list_backups()
    assert len(final_backups) == 6
    final_names = [p.name for p in final_backups]
    assert final_names == created_names[-6:]  # Mantém exatamente do 3º ao 8º
    assert created_names[0] not in final_names
    assert created_names[1] not in final_names

    # 6. Valida que o arquivo de backup mais antigo retido (3º ciclo, com 3 tags) é um banco SQLite íntegro
    # e testa a restauração de backup
    oldest_retained = final_backups[0]
    backup_Service_restore_path = backup_service.restore_from_backup(oldest_retained)
    assert backup_Service_restore_path == db_file.resolve()
    assert db.fetch_scalar("SELECT COUNT(*) FROM tags") == 3

    db.close()


def test_backup_advance_warning_notification(tmp_path: Path) -> None:
    """Valida o aviso prévio de 5 minutos (300s) e contagem regressiva do agendador de backup."""
    settings = AppSettings.load(tmp_path / "settings_warn.json")
    db_file = tmp_path / "warn.sqlite"
    backup_dir = tmp_path / "backups_warn"

    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(db_file)

    backup_service = BackupSchedulerService(
        connection_manager=db,
        settings=settings,
        interval_seconds=600,  # 10 minutos
    )
    backup_service.set_backup_directory(backup_dir)

    # 1. Sem agendador ativo, tempo restante é None e aviso é False
    assert backup_service.get_seconds_until_next_cycle() is None
    assert backup_service.is_advance_warning_active() is False

    # 2. Inicia agendador: timestamp é configurado ~600s no futuro (> 300s, logo não está em aviso)
    backup_service.start_background_scheduler()
    assert backup_service.is_running is True
    sec = backup_service.get_seconds_until_next_cycle()
    assert sec is not None and 550.0 < sec <= 600.0
    assert backup_service.is_advance_warning_active() is False

    # 3. Simula aproximação da janela de 5 minutos (ex.: 240 segundos restantes)
    warning_calls: list[float] = []
    backup_service.add_advance_warning_listener(lambda left: warning_calls.append(left))

    with backup_service._lock:
        backup_service._next_run_timestamp = datetime.now() + timedelta(seconds=240)
        backup_service._advance_warning_notified = False

    assert backup_service.is_advance_warning_active() is True
    time.sleep(1.2)  # Permite ao loop detectar e disparar o listener
    assert len(warning_calls) >= 1
    assert warning_calls[0] <= 300.0

    backup_service.stop_background_scheduler()
    db.close()

