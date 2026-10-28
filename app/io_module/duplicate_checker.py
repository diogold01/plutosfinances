"""
Motor determinístico de prevenção de duplicidades em importações (`DuplicateChecker`).

Calcula uma assinatura SHA-256 canônica para cada linha importada a partir de:
- Tipo de lançamento (`despesa`, `receita`, `transferencia`)
- Data de vencimento em formato ISO (`YYYY-MM-DD`)
- Valor absoluto arredondado em 2 casas decimais
- Descrição normalizada (minúsculas, sem acentos redundantes ou espaços múltiplos)
- Identificador de conta ou cartão alvo (quando aplicável)
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime
from typing import Iterable, Optional, Set

from app.database.connection_manager import ConnectionManager
from app.io_module.contracts import CanonicalTransactionRow


def normalize_text_for_hash(text: str) -> str:
    """Remove acentos, converte para minúsculas e colapsa espaços em branco."""
    raw = (text or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_only).strip()


def compute_row_fingerprint(
    row: CanonicalTransactionRow,
    *,
    target_account_id: str = "",
    target_card_id: str = "",
    profile_id: str = "1",
) -> str:
    """Gera o hash SHA-256 determinístico de 32 caracteres para uma linha canônica."""
    kind_norm = (row.kind or "despesa").strip().lower()
    date_iso = row.data_vencimento.isoformat()
    val_norm = f"{abs(round(float(row.valor or 0.0), 2)):.2f}"
    desc_norm = normalize_text_for_hash(row.descricao)
    target_norm = f"acc:{target_account_id or row.conta}|card:{target_card_id or row.cartao}"
    payload = f"p:{profile_id}|k:{kind_norm}|d:{date_iso}|v:{val_norm}|t:{desc_norm}|{target_norm}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    row.fingerprint = digest
    return digest


class DuplicateChecker:
    """
    Verificador de duplicidade com suporte a registro em memória e persistência
    na tabela `import_fingerprints` + verificação cruzada nas tabelas de domínio.
    """

    def __init__(self, db: Optional[ConnectionManager] = None) -> None:
        self.db = db
        self._memory_seen: Set[str] = set()

    def is_duplicate(
        self,
        row: CanonicalTransactionRow,
        *,
        target_account_id: str = "",
        target_card_id: str = "",
        profile_id: str = "1",
    ) -> bool:
        """Retorna True se a linha já tiver sido importada no lote atual ou no banco."""
        fp = row.fingerprint or compute_row_fingerprint(
            row,
            target_account_id=target_account_id,
            target_card_id=target_card_id,
            profile_id=profile_id,
        )
        if fp in self._memory_seen:
            return True

        if self.db is None:
            return False

        existing_rows = self.db.execute_query(
            "SELECT id_transacao, kind FROM import_fingerprints WHERE fingerprint = ?",
            (fp,),
        )
        if not existing_rows:
            return False

        # Verifica se alguma transação vinculada ao fingerprint ainda está ativa no banco
        for r in existing_rows:
            tx_id = r["id_transacao"]
            kind = (r["kind"] or row.kind).upper()
            table = "despesas" if kind == "DESPESA" else ("receitas" if kind == "RECEITA" else "transferencias")
            active = self.db.fetch_scalar(
                f"SELECT 1 FROM {table} WHERE id = ? AND (data_exclusao IS NULL OR data_exclusao = '') LIMIT 1",
                (str(tx_id),),
            )
            if active is not None:
                return True

        # Se todas as transações vinculadas foram excluídas ou não existem mais, expurga o fingerprint órfão
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM import_fingerprints WHERE fingerprint = ?", (fp,))
        return False

    def clear_memory(self) -> None:
        """Limpa o cache de fingerprints em memória para um novo lote."""
        self._memory_seen.clear()

    def register_imported(
        self,
        row: CanonicalTransactionRow,
        transaction_id: str,
        *,
        profile_id: str = "1",
        source_file: str = "",
    ) -> str:
        """Registra o fingerprint na memória e na tabela `import_fingerprints`."""
        fp = row.fingerprint or compute_row_fingerprint(row, profile_id=profile_id)
        self._memory_seen.add(fp)
        if self.db is not None:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.db.transaction() as cur:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO import_fingerprints (
                        fingerprint, id_profile, kind, id_transacao, source_file, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fp,
                        str(profile_id),
                        row.kind,
                        str(transaction_id),
                        str(source_file),
                        now_str,
                    ),
                )
        return fp

    def register_batch(
        self,
        items: Iterable[tuple[CanonicalTransactionRow, str]],
        *,
        profile_id: str = "1",
        source_file: str = "",
    ) -> None:
        """Registra múltiplos fingerprints em uma única transação atômica."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows_to_insert = []
        for row, tx_id in items:
            fp = row.fingerprint or compute_row_fingerprint(row, profile_id=profile_id)
            self._memory_seen.add(fp)
            rows_to_insert.append(
                (fp, str(profile_id), row.kind, str(tx_id), str(source_file), now_str)
            )
        if self.db is not None and rows_to_insert:
            with self.db.transaction() as cur:
                cur.executemany(
                    """
                    INSERT OR REPLACE INTO import_fingerprints (
                        fingerprint, id_profile, kind, id_transacao, source_file, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    rows_to_insert,
                )
