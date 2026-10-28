"""Repositório de Categorias e Subcategorias (Despesas, Receitas e Contas)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from app.config.theme_palette import argb_int_to_hex, hex_to_argb_int
from app.database.connection_manager import ConnectionManager


@dataclass
class SubcategoryDTO:
    id: str
    id_profile: str
    id_categoria: str
    nome: str
    color_int: int
    color_hex: str
    icon_id: int
    archived: bool = False

    @property
    def name(self) -> str:
        return self.nome


@dataclass
class CategoryDTO:
    id: str
    id_profile: str
    nome: str
    kind: str  # 'DESPESA', 'RECEITA', 'CONTA'
    color_int: int
    color_hex: str
    icon_id: int
    archived: bool = False
    subcategories: List[SubcategoryDTO] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.nome


class CategoryRepository:
    """
    Gerencia a árvore de Categorias e Subcategorias de:
    - Despesas (`despesas_cat` + `despesas_subcat`)
    - Receitas (`receitas_cat` + `receitas_subcat`)
    - Contas (`contas_cat`)
    """

    def __init__(self, db: ConnectionManager) -> None:
        self.db = db

    def list_categories(
        self,
        kind: str = "DESPESA",
        profile_id: str = "1",
        include_deleted: bool = False,
    ) -> List[CategoryDTO]:
        k = (kind or "DESPESA").upper()
        if k.startswith("REC"):
            return self.list_income_categories(profile_id, include_deleted)
        if k.startswith("CON"):
            return self.list_account_categories(profile_id)
        return self.list_expense_categories(profile_id, include_deleted)

    def list_expense_categories(
        self,
        profile_id: str = "1",
        include_deleted: bool = False,
    ) -> List[CategoryDTO]:
        where_del = "" if include_deleted else "AND data_exclusao IS NULL"
        cat_rows = self.db.execute_query(
            f"""
            SELECT id, id_profile, nome, COALESCE(cor, -10720320) AS cor,
                   COALESCE(icon_id, 955) AS icon_id, data_exclusao
            FROM despesas_cat
            WHERE id_profile = ? {where_del}
            ORDER BY nome ASC
            """,
            (str(profile_id),),
        )
        sub_rows = self.db.execute_query(
            f"""
            SELECT id, id_profile, id_categoria, nome,
                   COALESCE(cor, -10720320) AS cor,
                   COALESCE(icon_id, 955) AS icon_id, data_exclusao
            FROM despesas_subcat
            WHERE id_profile = ? {where_del}
            ORDER BY CASE WHEN LOWER(nome) = 'outros' THEN 1 ELSE 0 END, nome ASC
            """,
            (str(profile_id),),
        )
        subs_by_cat: dict[str, List[SubcategoryDTO]] = {}
        for sr in sub_rows:
            cat_id = str(sr["id_categoria"])
            subs_by_cat.setdefault(cat_id, []).append(
                SubcategoryDTO(
                    id=str(sr["id"]),
                    id_profile=str(sr["id_profile"]),
                    id_categoria=cat_id,
                    nome=str(sr["nome"] or "Outros"),
                    color_int=int(sr["cor"]),
                    color_hex=argb_int_to_hex(int(sr["cor"])),
                    icon_id=int(sr["icon_id"]),
                    archived=sr["data_exclusao"] is not None,
                )
            )

        result: List[CategoryDTO] = []
        for cr in cat_rows:
            cid = str(cr["id"])
            result.append(
                CategoryDTO(
                    id=cid,
                    id_profile=str(cr["id_profile"]),
                    nome=str(cr["nome"] or "Outros"),
                    kind="DESPESA",
                    color_int=int(cr["cor"]),
                    color_hex=argb_int_to_hex(int(cr["cor"])),
                    icon_id=int(cr["icon_id"]),
                    archived=cr["data_exclusao"] is not None,
                    subcategories=subs_by_cat.get(cid, []),
                )
            )
        return result

    def list_income_categories(
        self,
        profile_id: str = "1",
        include_deleted: bool = False,
    ) -> List[CategoryDTO]:
        where_del = "" if include_deleted else "AND data_exclusao IS NULL"
        cat_rows = self.db.execute_query(
            f"""
            SELECT id, id_profile, descricao AS nome,
                   COALESCE(cor, -11751600) AS cor,
                   COALESCE(icon_id, 276) AS icon_id, data_exclusao
            FROM receitas_cat
            WHERE id_profile = ? {where_del}
            ORDER BY descricao ASC
            """,
            (str(profile_id),),
        )
        sub_rows = self.db.execute_query(
            f"""
            SELECT id, id_profile, id_categoria, nome,
                   COALESCE(cor, -11751600) AS cor,
                   COALESCE(icon_id, 955) AS icon_id, data_exclusao
            FROM receitas_subcat
            WHERE id_profile = ? {where_del}
            ORDER BY CASE WHEN LOWER(nome) = 'outros' THEN 1 ELSE 0 END, nome ASC
            """,
            (str(profile_id),),
        )
        subs_by_cat: dict[str, List[SubcategoryDTO]] = {}
        for sr in sub_rows:
            cat_id = str(sr["id_categoria"])
            subs_by_cat.setdefault(cat_id, []).append(
                SubcategoryDTO(
                    id=str(sr["id"]),
                    id_profile=str(sr["id_profile"]),
                    id_categoria=cat_id,
                    nome=str(sr["nome"] or "Outros"),
                    color_int=int(sr["cor"]),
                    color_hex=argb_int_to_hex(int(sr["cor"])),
                    icon_id=int(sr["icon_id"]),
                    archived=sr["data_exclusao"] is not None,
                )
            )

        result: List[CategoryDTO] = []
        for cr in cat_rows:
            cid = str(cr["id"])
            result.append(
                CategoryDTO(
                    id=cid,
                    id_profile=str(cr["id_profile"]),
                    nome=str(cr["nome"] or "Outros"),
                    kind="RECEITA",
                    color_int=int(cr["cor"]),
                    color_hex=argb_int_to_hex(int(cr["cor"])),
                    icon_id=int(cr["icon_id"]),
                    archived=cr["data_exclusao"] is not None,
                    subcategories=subs_by_cat.get(cid, []),
                )
            )
        return result

    def list_account_categories(self, profile_id: str = "1") -> List[CategoryDTO]:
        rows = self.db.execute_query(
            """
            SELECT id, id_profile, descricao AS nome,
                   COALESCE(cor, -15228834) AS cor,
                   COALESCE(icon_id, 252) AS icon_id
            FROM contas_cat
            WHERE id_profile = ?
            ORDER BY descricao ASC
            """,
            (str(profile_id),),
        )
        return [
            CategoryDTO(
                id=str(r["id"]),
                id_profile=str(r["id_profile"]),
                nome=str(r["nome"] or "Conta Corrente"),
                kind="CONTA",
                color_int=int(r["cor"]),
                color_hex=argb_int_to_hex(int(r["cor"])),
                icon_id=int(r["icon_id"]),
            )
            for r in rows
        ]

    def create_category(
        self,
        kind: str,
        nome: str,
        color_hex: str = "#2196F3",
        icon_id: int = 955,
        profile_id: str = "1",
    ) -> CategoryDTO:
        cat_id = str(uuid.uuid4())[:8]
        color_int = hex_to_argb_int(color_hex)
        kind_upper = kind.upper()
        sub_dtos: List[SubcategoryDTO] = []

        with self.db.transaction() as cur:
            if kind_upper == "DESPESA":
                cur.execute(
                    """
                    INSERT INTO despesas_cat (id, id_profile, nome, cor, icon_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cat_id, str(profile_id), nome.strip(), color_int, icon_id),
                )
                sub_id = str(uuid.uuid4())[:8]
                cur.execute(
                    """
                    INSERT INTO despesas_subcat (id, id_profile, id_categoria, nome, cor, icon_id)
                    VALUES (?, ?, ?, 'Outros', ?, 955)
                    """,
                    (sub_id, str(profile_id), cat_id, color_int),
                )
                sub_dtos.append(
                    SubcategoryDTO(
                        id=sub_id,
                        id_profile=str(profile_id),
                        id_categoria=cat_id,
                        nome="Outros",
                        color_int=color_int,
                        color_hex=argb_int_to_hex(color_int),
                        icon_id=955,
                    )
                )
            elif kind_upper == "RECEITA":
                cur.execute(
                    """
                    INSERT INTO receitas_cat (id, id_profile, descricao, cor, icon_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cat_id, str(profile_id), nome.strip(), color_int, icon_id),
                )
                sub_id = str(uuid.uuid4())[:8]
                cur.execute(
                    """
                    INSERT INTO receitas_subcat (id, id_profile, id_categoria, nome, cor, icon_id)
                    VALUES (?, ?, ?, 'Outros', ?, 955)
                    """,
                    (sub_id, str(profile_id), cat_id, color_int),
                )
                sub_dtos.append(
                    SubcategoryDTO(
                        id=sub_id,
                        id_profile=str(profile_id),
                        id_categoria=cat_id,
                        nome="Outros",
                        color_int=color_int,
                        color_hex=argb_int_to_hex(color_int),
                        icon_id=955,
                    )
                )
            elif kind_upper == "CONTA":
                cur.execute(
                    """
                    INSERT INTO contas_cat (id, id_profile, descricao, cor, icon_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cat_id, str(profile_id), nome.strip(), color_int, icon_id),
                )
            else:
                raise ValueError(f"Tipo de categoria inválido: {kind}")

        return CategoryDTO(
            id=cat_id,
            id_profile=str(profile_id),
            nome=nome.strip(),
            kind=kind_upper,
            color_int=color_int,
            color_hex=argb_int_to_hex(color_int),
            icon_id=icon_id,
            subcategories=sub_dtos,
        )

    def update_category(
        self,
        kind: str,
        category_id: str,
        nome: str,
        color_hex: str,
        icon_id: int = 955,
    ) -> None:
        color_int = hex_to_argb_int(color_hex)
        kind_upper = kind.upper()
        if kind_upper == "DESPESA":
            self.db.execute_write(
                "UPDATE despesas_cat SET nome = ?, cor = ?, icon_id = ? WHERE id = ?",
                (nome.strip(), color_int, icon_id, str(category_id)),
            )
        elif kind_upper == "RECEITA":
            self.db.execute_write(
                "UPDATE receitas_cat SET descricao = ?, cor = ?, icon_id = ? WHERE id = ?",
                (nome.strip(), color_int, icon_id, str(category_id)),
            )
        elif kind_upper == "CONTA":
            self.db.execute_write(
                "UPDATE contas_cat SET descricao = ?, cor = ?, icon_id = ? WHERE id = ?",
                (nome.strip(), color_int, icon_id, str(category_id)),
            )

    def delete_category(self, kind: str, category_id: str, soft: bool = True) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kind_upper = kind.upper()
        with self.db.transaction() as cur:
            if kind_upper == "DESPESA":
                if soft:
                    cur.execute(
                        "UPDATE despesas_cat SET data_exclusao = ? WHERE id = ?",
                        (now_str, str(category_id)),
                    )
                    cur.execute(
                        "UPDATE despesas_subcat SET data_exclusao = ? WHERE id_categoria = ?",
                        (now_str, str(category_id)),
                    )
                else:
                    cur.execute(
                        "DELETE FROM despesas_subcat WHERE id_categoria = ?",
                        (str(category_id),),
                    )
                    cur.execute(
                        "DELETE FROM despesas_cat WHERE id = ?", (str(category_id),)
                    )
            elif kind_upper == "RECEITA":
                if soft:
                    cur.execute(
                        "UPDATE receitas_cat SET data_exclusao = ? WHERE id = ?",
                        (now_str, str(category_id)),
                    )
                    cur.execute(
                        "UPDATE receitas_subcat SET data_exclusao = ? WHERE id_categoria = ?",
                        (now_str, str(category_id)),
                    )
                else:
                    cur.execute(
                        "DELETE FROM receitas_subcat WHERE id_categoria = ?",
                        (str(category_id),),
                    )
                    cur.execute(
                        "DELETE FROM receitas_cat WHERE id = ?", (str(category_id),)
                    )
            elif kind_upper == "CONTA":
                cur.execute("DELETE FROM contas_cat WHERE id = ?", (str(category_id),))

    def create_subcategory(
        self,
        kind: str,
        category_id: str,
        nome: str,
        color_hex: str = "#2196F3",
        icon_id: int = 955,
        profile_id: str = "1",
    ) -> SubcategoryDTO:
        sub_id = str(uuid.uuid4())[:8]
        color_int = hex_to_argb_int(color_hex)
        table = (
            "despesas_subcat" if kind.upper() == "DESPESA" else "receitas_subcat"
        )
        self.db.execute_write(
            f"""
            INSERT INTO {table} (id, id_profile, id_categoria, nome, cor, icon_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sub_id, str(profile_id), str(category_id), nome.strip(), color_int, icon_id),
        )
        return SubcategoryDTO(
            id=sub_id,
            id_profile=str(profile_id),
            id_categoria=str(category_id),
            nome=nome.strip(),
            color_int=color_int,
            color_hex=argb_int_to_hex(color_int),
            icon_id=icon_id,
        )

    def update_subcategory(
        self,
        kind: str,
        subcategory_id: str,
        nome: str,
        color_hex: str,
        icon_id: int = 955,
    ) -> None:
        color_int = hex_to_argb_int(color_hex)
        table = (
            "despesas_subcat" if kind.upper() == "DESPESA" else "receitas_subcat"
        )
        self.db.execute_write(
            f"UPDATE {table} SET nome = ?, cor = ?, icon_id = ? WHERE id = ?",
            (nome.strip(), color_int, icon_id, str(subcategory_id)),
        )

    def delete_subcategory(
        self, kind: str, subcategory_id: str, soft: bool = True
    ) -> None:
        table = (
            "despesas_subcat" if kind.upper() == "DESPESA" else "receitas_subcat"
        )
        if soft:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute_write(
                f"UPDATE {table} SET data_exclusao = ? WHERE id = ?",
                (now_str, str(subcategory_id)),
            )
        else:
            self.db.execute_write(
                f"DELETE FROM {table} WHERE id = ?", (str(subcategory_id),)
            )
