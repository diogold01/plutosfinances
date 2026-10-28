"""Inicializador e migrador idempotente do esquema relacional SQLite (Minhas Finanças)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple

from app.config.app_settings import SEED_BLANK_DB_PATH, SEED_DEFAULT_DB_PATH

# Tabelas dinâmicas criadas em tempo de execução pela aplicação de referência (escopo 100% local)
DYNAMIC_TABLES_DDL: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS "tags" (
        "id" Text NOT NULL PRIMARY KEY,
        "id_profile" Text NOT NULL,
        "nome" Text NOT NULL,
        "cor" Integer,
        "arquivada" Text DEFAULT 'N',
        CONSTRAINT "unique_id" UNIQUE ( id )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "tags_transacoes" (
        "id_transacao" Text NOT NULL,
        "tipo_transacao" Text NOT NULL,
        "id_tag" Text NOT NULL,
        "id_transacao_origem" Text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "filtros_tags" (
        "id_filtro" Text,
        "id_tag" Text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "orcamentos_tags" (
        "id_orcamento" TEXT NOT NULL,
        "id_tag" TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "orcamentos_categorias" (
        "id_orcamento" TEXT NOT NULL,
        "id_categoria" TEXT NOT NULL,
        "id_subcategoria" TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "orcamentos_cartoes" (
        "id_orcamento" TEXT NOT NULL,
        "id_cartao" TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "orcamentos_agrupamento" (
        "id_pai" TEXT NOT NULL,
        "id_filho" TEXT NOT NULL,
        UNIQUE("id_filho"),
        CHECK ("id_pai" <> "id_filho"),
        FOREIGN KEY ("id_pai") REFERENCES "orcamentos"("id") ON DELETE CASCADE,
        FOREIGN KEY ("id_filho") REFERENCES "orcamentos"("id") ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "modelos_csv" (
        "id" Text PRIMARY KEY,
        "valor_negativo_despesas" Text NOT NULL,
        "descricao" Text NOT NULL,
        "observacoes" Text,
        "id_conta" Text,
        "id_cartao" Text,
        "separador" Text NOT NULL,
        "possui_cabecalho" Text NOT NULL,
        "formato_data" Text NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "modelos_csv_campos" (
        "id" Text PRIMARY KEY,
        "coluna" INTEGER,
        "id_modelo" TEXT,
        "campo" TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "membros" (
        "id" Text NOT NULL PRIMARY KEY,
        "nome" Text NOT NULL,
        "data_nascimento" DateTime,
        "parentesco" Number,
        "id_perfil" Text,
        "id_dispositivo" Text,
        "url_foto" Text,
        "foto_doc_id" Text,
        "arquivado" Text DEFAULT 'N',
        CONSTRAINT "unique_id" UNIQUE (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "cotacoes" (
        "base" Text NOT NULL,
        "symbol" Text NOT NULL,
        "rate" Double NOT NULL,
        "date" Date NOT NULL,
        "last" Text NOT NULL,
        "expiration" DATETIME,
        "auto" TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "app_metadata" (
        "key" TEXT PRIMARY KEY NOT NULL,
        "value" TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS "import_fingerprints" (
        "fingerprint" TEXT PRIMARY KEY NOT NULL,
        "id_profile" TEXT NOT NULL DEFAULT '1',
        "kind" TEXT NOT NULL,
        "id_transacao" TEXT NOT NULL,
        "source_file" TEXT,
        "imported_at" TEXT NOT NULL
    )
    """,
]

# Índices adicionais de performance
DYNAMIC_INDEXES_DDL: List[str] = [
    "CREATE INDEX IF NOT EXISTS ux_orc_cartoes ON orcamentos_cartoes(id_orcamento, id_cartao)",
    "CREATE INDEX IF NOT EXISTS ux_orc_tags ON orcamentos_tags(id_orcamento, id_tag)",
    "CREATE INDEX IF NOT EXISTS ux_orc_cat ON orcamentos_categorias(id_orcamento, id_categoria, id_subcategoria)",
    "CREATE INDEX IF NOT EXISTS idx_orc_agru_pai ON orcamentos_agrupamento(id_pai)",
    "CREATE INDEX IF NOT EXISTS idx_orc_agru_filho ON orcamentos_agrupamento(id_filho)",
    "CREATE INDEX IF NOT EXISTS idx_despesas_rec_data ON despesas(recorrencia, data)",
    "CREATE INDEX IF NOT EXISTS idx_dcv_iddesp_data ON despesas_cat_valor(id_despesa, data)",
    "CREATE INDEX IF NOT EXISTS idx_df_iddesp_data ON despesas_fixas(id_despesa, data)",
    "CREATE INDEX IF NOT EXISTS idx_orcamentos_data_criacao ON orcamentos(data_criacao)",
    "CREATE INDEX IF NOT EXISTS idx_tags_transacoes_lookup ON tags_transacoes(id_transacao, tipo_transacao)",
    "CREATE INDEX IF NOT EXISTS idx_tags_profile ON tags(id_profile)",
]

# Colunas adicionadas por migrações em tempo de execução sobre as tabelas base
RUNTIME_COLUMN_MIGRATIONS: Dict[str, List[Tuple[str, str]]] = {
    "profiles": [
        ("currency", "TEXT DEFAULT 'BRL'"),
        ("pin", "TEXT"),
    ],
    "contas": [
        ("currency", "TEXT DEFAULT 'BRL'"),
        ("conta_pai", "TEXT"),
        ("id_conta_pai", "TEXT"),
        ("cotacao", "REAL DEFAULT 1"),
        ("investimento", "TEXT DEFAULT 'N'"),
        ("liquidacao", "TEXT"),
        ("somar_todas_contas_agrupadas", "TEXT DEFAULT 'S'"),
        ("image_url", "TEXT"),
    ],
    "cartoes_credito": [
        ("nome_carteira", "TEXT"),
        ("image_id", "NUMERIC"),
        ("image_url", "TEXT"),
        ("holder_type", "TEXT"),
    ],
    "cartoes_credito_mes": [
        ("data_fecha_manual", "TEXT"),
        ("data_venc_manual", "TEXT"),
        ("status_manual", "TEXT"),
    ],
    "despesas": [
        ("ignore_orc", "TEXT DEFAULT 'N'"),
        ("cotacao", "REAL DEFAULT 1"),
        ("lembrete_vencimento", "TEXT"),
        ("origem_ajuste", "TEXT"),
        ("reconhecer_data_diferente", "TEXT"),
        ("reconhecer_valor_diferente", "TEXT"),
        ("sugerir_descricao", "TEXT"),
        ("ultima_modificacao", "DATETIME"),
        ("buscar_similares", "TEXT"),
    ],
    "despesas_fixas": [
        ("ignore_orc", "TEXT DEFAULT 'N'"),
        ("cotacao", "REAL DEFAULT 1"),
        ("data_evento", "DATETIME"),
    ],
    "receitas": [
        ("ignore_orc", "TEXT DEFAULT 'N'"),
        ("cotacao", "REAL DEFAULT 1"),
        ("data_evento", "DATETIME"),
        ("lembrete_vencimento", "TEXT"),
        ("origem_ajuste", "TEXT"),
        ("reconhecer_data_diferente", "TEXT"),
        ("reconhecer_valor_diferente", "TEXT"),
        ("sugerir_descricao", "TEXT"),
        ("ultima_modificacao", "DATETIME"),
        ("buscar_similares", "TEXT"),
    ],
    "receitas_fixas": [
        ("ignore_orc", "TEXT DEFAULT 'N'"),
        ("cotacao", "REAL DEFAULT 1"),
        ("data_evento", "DATETIME"),
    ],
    "transferencias": [
        ("data_cadastro", "DATETIME"),
        ("data_efetivacao", "DATETIME"),
        ("sugerir_descricao", "TEXT"),
        ("ultima_modificacao", "DATETIME"),
    ],
    "transferencias_fixas": [
        ("data_efetivacao", "DATETIME"),
    ],
    "orcamentos": [
        ("descricao", "TEXT"),
        ("cor", "INTEGER"),
        ("icon_id", "INTEGER"),
        ("perc_receitas", "REAL"),
        ("id_orcamento_receita_referencia", "TEXT"),
        ("data_inicial", "TEXT"),
        ("data_final", "TEXT"),
        ("saldo_previsto", "TEXT"),
        ("tipo_logica_tags", "TEXT DEFAULT 'OR'"),
        ("somar", "TEXT DEFAULT 'S'"),
    ],
    "orcamentos_mensal": [
        ("perc_receitas", "REAL"),
        ("id_orcamento_receita_referencia", "TEXT"),
    ],
    "tags": [
        ("arquivada", "TEXT DEFAULT 'N'"),
    ],
}

# Tabelas auditadas automaticamente por triggers para rastrear modificações pendentes (Requisito 5)
AUDITED_DOMAIN_TABLES: List[str] = [
    "profiles",
    "login",
    "preferencias",
    "contas",
    "contas_cat",
    "contas_saldo",
    "cartoes_credito",
    "cartoes_credito_mes",
    "despesas",
    "despesas_cat",
    "despesas_subcat",
    "despesas_fixas",
    "despesas_cat_valor",
    "receitas",
    "receitas_cat",
    "receitas_subcat",
    "receitas_fixas",
    "transferencias",
    "transferencias_fixas",
    "orcamentos",
    "orcamentos_mensal",
    "orcamentos_tags",
    "orcamentos_categorias",
    "orcamentos_cartoes",
    "orcamentos_agrupamento",
    "objetivos",
    "objetivos_dep",
    "tags",
    "tags_transacoes",
    "emprestimos",
    "emprestimos_vinculos",
    "notas",
    "filtros",
    "filtros_contas",
    "filtros_cartoes",
    "filtros_categorias",
    "filtros_tags",
    "modelos_csv",
    "modelos_csv_campos",
    "membros",
    "cotacoes",
]


def _get_existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return {r[1].lower() for r in rows}


def _install_mutation_tracking_triggers(conn: sqlite3.Connection) -> None:
    """Instala triggers AFTER INSERT/UPDATE/DELETE que incrementam atomicamente o mutation_counter."""
    existing_tables = {t.lower(): t for t in _get_existing_tables(conn)}
    for tbl_lower in AUDITED_DOMAIN_TABLES:
        actual_table = existing_tables.get(tbl_lower)
        if not actual_table:
            continue
        for op in ("INSERT", "UPDATE", "DELETE"):
            trig_name = f"tg_mf_audit_{op.lower()}_{tbl_lower}"
            conn.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS "{trig_name}"
                AFTER {op} ON "{actual_table}"
                FOR EACH ROW
                BEGIN
                    INSERT INTO app_metadata (key, value)
                    VALUES ('mutation_counter', '1')
                    ON CONFLICT(key) DO UPDATE SET
                        value = CAST(CAST(value AS INTEGER) + 1 AS TEXT);
                    INSERT INTO app_metadata (key, value)
                    VALUES ('last_modified_utc', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value;
                END;
                """
            )


def ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    """
    Aplica de forma idempotente todas as tabelas dinâmicas, colunas de migração,
    índices e triggers de rastreamento de modificação em uma conexão SQLite.
    """
    with conn:
        for ddl in DYNAMIC_TABLES_DDL:
            conn.execute(ddl)

        existing_tables = {t.lower(): t for t in _get_existing_tables(conn)}
        for table_lower, columns in RUNTIME_COLUMN_MIGRATIONS.items():
            actual_table = existing_tables.get(table_lower)
            if not actual_table:
                continue
            existing_cols = _get_table_columns(conn, actual_table)
            for col_name, col_type in columns:
                if col_name.lower() not in existing_cols:
                    conn.execute(
                        f'ALTER TABLE "{actual_table}" ADD COLUMN "{col_name}" {col_type}'
                    )

        for idx_ddl in DYNAMIC_INDEXES_DDL:
            try:
                conn.execute(idx_ddl)
            except sqlite3.OperationalError:
                pass

        # Inicializa contadores em app_metadata se ainda não existirem
        conn.execute(
            """
            INSERT OR IGNORE INTO app_metadata (key, value)
            VALUES ('mutation_counter', '0')
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO app_metadata (key, value)
            VALUES ('last_modified_utc', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO app_metadata (key, value)
            VALUES ('schema_version', '1.2609.432.0')
            """
        )

        # Instala os triggers de auditoria de mutação após popular metadados iniciais
        _install_mutation_tracking_triggers(conn)


def initialize_new_database_file(
    target_db_path: Path | str,
    overwrite: bool = False,
) -> Path:
    """
    Cria um novo arquivo de banco de dados SQLite (.db ou .sqlite) no diretório selecionado
    a partir do banco semente oficial (`minhasfinancas.db` / `minhasfinancas_blank.db`)
    e aplica todas as migrações e triggers locais.
    """
    dest_path = Path(target_db_path).resolve()
    if dest_path.exists() and not overwrite:
        raise FileExistsError(
            f"O arquivo de banco de dados já existe em: {dest_path}"
        )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and overwrite:
        dest_path.unlink()

    # Seleciona o banco semente com a taxonomia oficial (perfis, categorias, subcategorias)
    seed_source = (
        SEED_DEFAULT_DB_PATH
        if SEED_DEFAULT_DB_PATH.exists()
        else SEED_BLANK_DB_PATH
    )
    if not seed_source.exists():
        raise FileNotFoundError(
            f"Banco de dados semente não encontrado em: {seed_source}"
        )

    # Usa a própria Online Backup API do SQLite para clonar o banco semente com integridade
    src_conn = sqlite3.connect(f"file:{seed_source}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(str(dest_path))
    try:
        src_conn.backup(dst_conn)
        ensure_schema_migrations(dst_conn)
        # Reseta o mutation_counter para 0 após a criação inicial da base
        with dst_conn:
            dst_conn.execute(
                "UPDATE app_metadata SET value = '0' WHERE key = 'mutation_counter'"
            )
    finally:
        src_conn.close()
        dst_conn.close()

    return dest_path
