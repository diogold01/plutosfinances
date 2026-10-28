"""Telas modulares da interface gráfica nativa (PySide6)."""

from .calendario_view import CalendarioView
from .cartoes_view import CardFormDialog, CartoesView
from .categorias_view import CategoriasView, CategoryItemDialog
from .configuracoes_view import ConfiguracoesView
from .contas_view import AccountFormDialog, BalanceReconcileDialog, ContasView
from .dashboard_view import DashboardView
from .ferramentas_view import FerramentasView
from .graficos_view import GraficosView
from .objetivos_view import DepositDialog, GoalFormDialog, ObjetivosView
from .orcamentos_view import BudgetFormDialog, OrcamentosView
from .relatorios_view import RelatoriosView
from .tags_view import TagsView
from .transacoes_view import (
    ExpenseDialog,
    IncomeDialog,
    SplitEditorDialog,
    TransacoesView,
    TransferDialog,
)

__all__ = [
    "AccountFormDialog",
    "BalanceReconcileDialog",
    "BudgetFormDialog",
    "CalendarioView",
    "CardFormDialog",
    "CartoesView",
    "CategoriasView",
    "CategoryItemDialog",
    "ConfiguracoesView",
    "ContasView",
    "DashboardView",
    "DepositDialog",
    "ExpenseDialog",
    "FerramentasView",
    "GoalFormDialog",
    "GraficosView",
    "IncomeDialog",
    "ObjetivosView",
    "OrcamentosView",
    "RelatoriosView",
    "SplitEditorDialog",
    "TagsView",
    "TransacoesView",
    "TransferDialog",
]
