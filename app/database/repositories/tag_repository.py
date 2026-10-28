"""Repositório de Tags (`tags` e `tags_transacoes`)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import List, Optional

from app.config.theme_palette import argb_int_to_hex, hex_to_argb_int
from app.database.connection_manager import ConnectionManager


@dataclass
class TagDTO:
    id: str
    id_profile: str
    nome: str
    color_int: int
    color_hex: str
    arquivada: str
    utilizacoes: int = 0

    @property
    def name(self) -> str:
        return self.nome



class TagRepository:
    """Gerencia o cadastro, arquivamento, exclusão e vinculação de tags a transações."""

    def __init__(self, db: ConnectionManager) -> None:
        self.db = db

    def list_tags(
        self,
        profile_id: str = "1",
        include_archived: bool = False,
        search_text: str = "",
    ) -> List[TagDTO]:
        clauses = ["t.id_profile = ?"]
        params: list[object] = [str(profile_id)]
        if not include_archived:
            clauses.append("COALESCE(t.arquivada, 'N') != 'S'")
        if search_text.strip():
            clauses.append("LOWER(t.nome) LIKE ?")
            params.append(f"%{search_text.strip().lower()}%")

        where_sql = " AND ".join(clauses)
        rows = self.db.execute_query(
            f"""
            SELECT t.id, t.id_profile, t.nome,
                   COALESCE(t.cor, -14575885) AS cor,
                   COALESCE(t.arquivada, 'N') AS arquivada,
                   COUNT(tt.id_tag) AS utilizacoes
            FROM tags t
            LEFT JOIN tags_transacoes tt ON t.id = tt.id_tag
            WHERE {where_sql}
            GROUP BY t.id
            ORDER BY CASE WHEN COALESCE(t.arquivada, 'N') = 'S' THEN 1 ELSE 0 END,
                     utilizacoes DESC,
                     t.nome ASC
            """,
            params,
        )
        return [
            TagDTO(
                id=str(r["id"]),
                id_profile=str(r["id_profile"]),
                nome=str(r["nome"] or ""),
                color_int=int(r["cor"]),
                color_hex=argb_int_to_hex(int(r["cor"])),
                arquivada=str(r["arquivada"]),
                utilizacoes=int(r["utilizacoes"] or 0),
            )
            for r in rows
        ]

    def create_tag(
        self,
        nome: str,
        color_hex: str = "#2196F3",
        profile_id: str = "1",
    ) -> TagDTO:
        clean_name = nome.strip().lstrip("#")
        if not clean_name:
            raise ValueError("O nome da tag não pode ser vazio.")
        tag_id = str(uuid.uuid4())[:8]
        color_int = hex_to_argb_int(color_hex)

        self.db.execute_write(
            """
            INSERT INTO tags (id, id_profile, nome, cor, arquivada)
            VALUES (?, ?, ?, ?, 'N')
            """,
            (tag_id, str(profile_id), clean_name, color_int),
        )
        return TagDTO(
            id=tag_id,
            id_profile=str(profile_id),
            nome=clean_name,
            color_int=color_int,
            color_hex=argb_int_to_hex(color_int),
            arquivada="N",
            utilizacoes=0,
        )

    def update_tag(
        self,
        tag_id: str,
        nome: str,
        color_hex: str,
        arquivada: str = "N",
    ) -> None:
        clean_name = nome.strip().lstrip("#")
        color_int = hex_to_argb_int(color_hex)
        self.db.execute_write(
            """
            UPDATE tags
            SET nome = ?, cor = ?, arquivada = ?
            WHERE id = ?
            """,
            (clean_name, color_int, arquivada, str(tag_id)),
        )

    def delete_tag(self, tag_id: str) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM tags_transacoes WHERE id_tag = ?", (str(tag_id),))
            cur.execute("DELETE FROM orcamentos_tags WHERE id_tag = ?", (str(tag_id),))
            cur.execute("DELETE FROM filtros_tags WHERE id_tag = ?", (str(tag_id),))
            cur.execute("DELETE FROM tags WHERE id = ?", (str(tag_id),))

    def set_transaction_tags(
        self,
        transaction_id: str,
        transaction_type: str,
        tag_ids: List[str],
        origin_transaction_id: Optional[str] = None,
    ) -> None:
        """Vincula a lista de tags a uma transação ('DESPESA', 'RECEITA', 'TRANSFERENCIA')."""
        tx_type = transaction_type.upper()
        with self.db.transaction() as cur:
            cur.execute(
                "DELETE FROM tags_transacoes WHERE id_transacao = ? AND tipo_transacao = ?",
                (str(transaction_id), tx_type),
            )
            for tid in dict.fromkeys(tag_ids):
                cur.execute(
                    """
                    INSERT INTO tags_transacoes (id_transacao, tipo_transacao, id_tag, id_transacao_origem)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(transaction_id),
                        tx_type,
                        str(tid),
                        str(origin_transaction_id) if origin_transaction_id else None,
                    ),
                )
