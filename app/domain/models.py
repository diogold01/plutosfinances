"""Modelos de domínio (DTOs) do motor de transações e cartões de crédito."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

KIND_DESPESA = "DESPESA"
KIND_RECEITA = "RECEITA"
KIND_TRANSFERENCIA = "TRANSFERENCIA"
ALL_KINDS = (KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA)

# Códigos de recorrência (compatíveis com a base de referência)
REC_UNICA = "U"
REC_PARCELADA = "P"
REC_FIXA_DESPESA = "F"  # despesas fixas usam 'F'
REC_FIXA_MENSAL = "M"  # receitas e transferências fixas usam 'M'

FIXED_CODES = {
    KIND_DESPESA: ("F",),
    KIND_RECEITA: ("M", "F"),
    KIND_TRANSFERENCIA: ("M", "F"),
}


def fixed_code_for(kind: str) -> str:
    return REC_FIXA_DESPESA if kind == KIND_DESPESA else REC_FIXA_MENSAL


@dataclass
class SplitDTO:
    """Item de rateio multi-categoria (`despesas_cat_valor`)."""

    id_categoria: str
    id_subcategoria: str
    valor: float
    obs: str = ""
    categoria_nome: str = ""
    subcategoria_nome: str = ""
    categoria_cor: str = "#5C6BC0"


@dataclass
class Occurrence:
    """Ocorrência de uma transação em um mês (única, parcela ou instância de recorrência fixa)."""

    kind: str
    id: str
    origin_id: str
    id_profile: str
    descricao: str
    valor: float
    juros: float
    efetivada: bool
    data_vencimento: date
    data_evento: Optional[date]
    data_efetivacao: Optional[date]
    ref_date: date
    recorrencia: str
    num_parcela: int
    num_parcelas: int
    intervalo: int
    id_conta: Optional[str]
    id_conta_destino: Optional[str]
    id_cartao: Optional[str]
    id_categoria: Optional[str]
    id_subcategoria: Optional[str]
    categoria_nome: str
    categoria_cor: str
    subcategoria_nome: str
    obs: str
    is_fixed: bool
    occ_year: int
    occ_month: int
    contabilizar: bool = True
    id_despesa_estornada: Optional[str] = None
    splits: List[SplitDTO] = field(default_factory=list)
    tags: List[Tuple[str, str, str]] = field(default_factory=list)  # (id, nome, cor_hex)
    conta_nome: str = ""
    conta_destino_nome: str = ""
    cartao_nome: str = ""

    @property
    def total(self) -> float:
        return round(self.valor + self.juros, 2)

    @property
    def is_card(self) -> bool:
        return bool(self.id_cartao)

    @property
    def is_expense(self) -> bool:
        return self.kind == KIND_DESPESA

    @property
    def is_income(self) -> bool:
        return self.kind == KIND_RECEITA

    @property
    def is_installment(self) -> bool:
        return self.num_parcelas > 1 and not self.is_fixed

    @property
    def is_recurring(self) -> bool:
        return self.is_fixed or self.is_installment

    @property
    def parcela_label(self) -> str:
        if self.is_fixed:
            return "Fixa"
        if self.num_parcelas > 1:
            return f"{self.num_parcela}/{self.num_parcelas}"
        return ""

    @property
    def signed_total(self) -> float:
        """Valor com sinal para o extrato consolidado (receita +, despesa -, transferência 0)."""
        if self.kind == KIND_RECEITA:
            return self.total
        if self.kind == KIND_DESPESA:
            return -self.total
        return 0.0

    @property
    def status_label(self) -> str:
        if self.kind == KIND_RECEITA:
            return "Recebido" if self.efetivada else "Pendente"
        if self.kind == KIND_TRANSFERENCIA:
            return "Efetivada" if self.efetivada else "Pendente"
        return "Pago" if self.efetivada else "Pendente"


@dataclass
class CardDTO:
    id: str
    id_profile: str
    nome: str
    limite: float
    dia_fecha: int
    dia_venc: int
    id_conta: Optional[str]
    conta_nome: str
    color_int: int
    color_hex: str
    brand_key: str
    padrao: str
    archived: bool = False


@dataclass
class InvoiceDTO:
    card: CardDTO
    ano: int
    mes: int
    data_fechamento: date
    data_vencimento: date
    limite: float
    items: List[Occurrence]
    total: float
    paga: bool
    status: str  # 'Aberta', 'Fechada', 'Vencida', 'Paga'
    id_conta_pagamento: Optional[str]
    usado: float
    disponivel: float
