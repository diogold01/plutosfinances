"""Repositório de Perfis Financeiros (`profiles`) e Segurança Local (`login`)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import List, Optional

from app.config.theme_palette import argb_int_to_hex, hex_to_argb_int
from app.database.connection_manager import ConnectionManager


@dataclass
class ProfileDTO:
    id: str
    name: str
    current: str
    color_int: int
    color_hex: str
    icon_id: int
    archived: str
    currency: str
    pin: Optional[str] = None


class ProfileRepository:
    """Gerencia os perfis financeiros isolados (ex.: Pessoal, Empresa, Família) e PIN local."""

    def __init__(self, db: ConnectionManager) -> None:
        self.db = db

    def list_profiles(self, include_archived: bool = False) -> List[ProfileDTO]:
        where_clause = "" if include_archived else "WHERE COALESCE(archived, 'N') != 'S'"
        rows = self.db.execute_query(
            f"""
            SELECT id, name, COALESCE(current, 'N') AS current,
                   COALESCE(color, -14575885) AS color,
                   COALESCE(icon, 0) AS icon,
                   COALESCE(archived, 'N') AS archived,
                   COALESCE(currency, 'BRL') AS currency,
                   pin
            FROM profiles
            {where_clause}
            ORDER BY CASE WHEN current = 'S' THEN 0 ELSE 1 END, name ASC
            """
        )
        return [
            ProfileDTO(
                id=str(r["id"]),
                name=str(r["name"] or "Pessoal"),
                current=str(r["current"]),
                color_int=int(r["color"]),
                color_hex=argb_int_to_hex(int(r["color"])),
                icon_id=int(r["icon"]),
                archived=str(r["archived"]),
                currency=str(r["currency"] or "BRL"),
                pin=r["pin"],
            )
            for r in rows
        ]

    def get_active_profile(self) -> ProfileDTO:
        profiles = self.list_profiles(include_archived=False)
        for p in profiles:
            if p.current == "S":
                return p
        if profiles:
            self.set_active_profile(profiles[0].id)
            return self.list_profiles(include_archived=False)[0]
        # Caso extremo de banco sem perfil, recria perfil padrão
        return self.create_profile("Pessoal", "#2196F3", currency="BRL", set_current=True)

    def set_active_profile(self, profile_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute("UPDATE profiles SET current = 'N'")
            cur.execute(
                "UPDATE profiles SET current = 'S' WHERE id = ?",
                (str(profile_id),),
            )
        self.db.settings.active_profile_id = str(profile_id)
        self.db.settings.save()

    def create_profile(
        self,
        name: str,
        color_hex: str = "#2196F3",
        icon_id: int = 0,
        currency: str = "BRL",
        set_current: bool = False,
        seed_default_categories: bool = True,
    ) -> ProfileDTO:
        new_id = str(uuid.uuid4())[:8]
        color_int = hex_to_argb_int(color_hex)
        current_flag = "S" if set_current else "N"

        with self.db.transaction() as cur:
            if set_current:
                cur.execute("UPDATE profiles SET current = 'N'")
            cur.execute(
                """
                INSERT INTO profiles (id, name, current, color, icon, archived, currency)
                VALUES (?, ?, ?, ?, ?, 'N', ?)
                """,
                (new_id, name.strip(), current_flag, color_int, icon_id, currency),
            )

            # Clona categorias padrão do perfil '1' para o novo perfil se solicitado
            if seed_default_categories and new_id != "1":
                self._clone_default_categories_to_profile(cur, new_id)

        if set_current:
            self.db.settings.active_profile_id = new_id
            self.db.settings.save()

        return ProfileDTO(
            id=new_id,
            name=name.strip(),
            current=current_flag,
            color_int=color_int,
            color_hex=argb_int_to_hex(color_int),
            icon_id=icon_id,
            archived="N",
            currency=currency,
        )

    def _clone_default_categories_to_profile(self, cur, target_profile_id: str) -> None:
        """Copia a taxonomia padrão (contas_cat, despesas_cat/subcat, receitas_cat/subcat) para o novo perfil."""
        # Categorias de Contas
        rows = cur.execute(
            "SELECT descricao, cor, padrao, icon_id FROM contas_cat WHERE id_profile = '1'"
        ).fetchall()
        for r in rows:
            cur.execute(
                """
                INSERT INTO contas_cat (id, id_profile, descricao, cor, padrao, icon_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4())[:8], target_profile_id, r[0], r[1], r[2], r[3]),
            )

        # Categorias e Subcategorias de Despesas
        d_cats = cur.execute(
            "SELECT id, nome, cor, icon_id FROM despesas_cat WHERE id_profile = '1' AND data_exclusao IS NULL"
        ).fetchall()
        for dc in d_cats:
            new_cat_id = str(uuid.uuid4())[:8]
            cur.execute(
                """
                INSERT INTO despesas_cat (id, id_profile, nome, cor, icon_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_cat_id, target_profile_id, dc[1], dc[2], dc[3]),
            )
            subs = cur.execute(
                "SELECT nome, cor, icon_id FROM despesas_subcat WHERE id_profile = '1' AND id_categoria = ? AND data_exclusao IS NULL",
                (dc[0],),
            ).fetchall()
            for sc in subs:
                cur.execute(
                    """
                    INSERT INTO despesas_subcat (id, id_profile, id_categoria, nome, cor, icon_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4())[:8], target_profile_id, new_cat_id, sc[0], sc[1], sc[2]),
                )

        # Categorias e Subcategorias de Receitas
        r_cats = cur.execute(
            "SELECT id, descricao, cor, icon_id FROM receitas_cat WHERE id_profile = '1' AND data_exclusao IS NULL"
        ).fetchall()
        for rc in r_cats:
            new_rc_id = str(uuid.uuid4())[:8]
            cur.execute(
                """
                INSERT INTO receitas_cat (id, id_profile, descricao, cor, icon_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_rc_id, target_profile_id, rc[1], rc[2], rc[3]),
            )
            r_subs = cur.execute(
                "SELECT nome, cor, icon_id FROM receitas_subcat WHERE id_profile = '1' AND id_categoria = ? AND data_exclusao IS NULL",
                (rc[0],),
            ).fetchall()
            for rsc in r_subs:
                cur.execute(
                    """
                    INSERT INTO receitas_subcat (id, id_profile, id_categoria, nome, cor, icon_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4())[:8], target_profile_id, new_rc_id, rsc[0], rsc[1], rsc[2]),
                )

    def update_profile(
        self,
        profile_id: str,
        name: str,
        color_hex: str,
        currency: str = "BRL",
        archived: str = "N",
    ) -> None:
        color_int = hex_to_argb_int(color_hex)
        self.db.execute_write(
            """
            UPDATE profiles
            SET name = ?, color = ?, currency = ?, archived = ?
            WHERE id = ?
            """,
            (name.strip(), color_int, currency, archived, str(profile_id)),
        )

    def set_local_pin(self, raw_pin: Optional[str]) -> None:
        """Define ou remove o PIN de bloqueio local na tabela `login`."""
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM login")
            if raw_pin and raw_pin.strip():
                digest = hashlib.sha256(raw_pin.strip().encode("utf-8")).hexdigest()
                cur.execute(
                    "INSERT INTO login (id, pwd) VALUES ('local_pin', ?)",
                    (digest,),
                )

    def verify_local_pin(self, raw_pin: str) -> bool:
        stored = self.db.fetch_scalar(
            "SELECT pwd FROM login WHERE id = 'local_pin'", default=None
        )
        if not stored:
            return True
        digest = hashlib.sha256(raw_pin.strip().encode("utf-8")).hexdigest()
        return stored == digest

    def has_local_pin(self) -> bool:
        stored = self.db.fetch_scalar(
            "SELECT pwd FROM login WHERE id = 'local_pin'", default=None
        )
        return bool(stored)
