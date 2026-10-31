# Plutos — Redesign do "Lançamento Inteligente" (pacote para o agente)

Este arquivo é autossuficiente: instruções, valores de design, ícones e o código de referência em PySide6.

## 1. O que anexar junto (do mockup)

| Anexo | Mandar? | Motivo |
|---|---|---|
| **PNG das 2 telas** (exportar do canvas: "Prévia" e "Entrada") | **Sim** | O agente vê o resultado esperado. Modelos leem imagem bem. |
| **Este .md** | **Sim** | Traz os números exatos e o código. É o que ele realmente usa. |
| HTML do mockup | Não precisa | É CSS de navegador, e o app é Qt/QSS. Este .md já traz as medidas. |
| PDF | Não | Imagem achatada: sem valores, sem vantagem sobre o PNG. |

Aviso importante: as cores do mockup eram aproximadas. **Em Qt, use só os tokens do `ThemePalette`** (tabela da seção 3). O mockup vale para layout, hierarquia e comportamento.

## 2. Prompt para o agente (Argon High ou 3.8 Flash Medium)

```
TAREFA: redesenhar SOMENTE a interface do diálogo "Lançamento Inteligente (Gemini)" (Ctrl+K).
NÃO alterar lógica: worker, AIService, validação, persistência, atalhos e testes de
comportamento continuam como estão.

CONTEXTO
App PySide6 "Plutos". Há um diálogo atual que funciona, mas o visual está ruim:
checkboxes laranja sólidos sem ícone, caixas de formulário sempre abertas, chip do modelo
parecendo botão, tudo na cor primária, campos cortados ("Minha Conta Corr…"), altura fixa com
espaço morto, emojis nas sugestões.
Anexos: 2 PNGs do resultado esperado + este arquivo (código de referência na seção 6).

ANTES DE EDITAR, LEIA SÓ ISTO
- o arquivo do diálogo atual (procure por "Lançamento Inteligente" em app/ui/dialogs/) e quem o
  instancia na MainWindow
- app/ui/components.py (BaseModalDialog, Badge), app/ui/icons.py, app/config/theme_palette.py
- app/ui/style_manager.py: só os trechos de QPushButton#PrimaryButton/SecondaryButton/GhostButton
  e dos inputs
- tests/ que instanciam o diálogo

O QUE FAZER
1. Adicionar os 4 ícones da seção 5 em app/ui/icons.py (SVG_PATHS).
2. Criar app/ui/dialogs/ai_entry_widgets.py com o código da seção 6, ajustando imports se
   algum caminho for diferente no repo.
3. Trocar o layout do diálogo atual pelo AIQuickEntryDialogView (ou herdar dele),
   religando os SINAIS/MÉTODOS à lógica que já existe:
   - interpret_requested(str)  -> o que hoje dispara o AIWorker
   - set_loading(bool), show_error(str), set_model_name(str)
   - show_preview(list[EntryViewModel], EntryOptions) -> chamado quando a IA responde
   - confirmed(list[EntryViewModel]) -> copiar as edições de volta para os AIParsedEntry e
     chamar o commit existente; ao terminar com sucesso, chamar done_ok()
   - manual_requested -> abre o lançamento manual que já existe
4. Escrever a função de mapeamento AIParsedEntry <-> EntryViewModel (exemplo na seção 7).
   Os nomes dos campos do AIParsedEntry podem diferir; use os reais.
5. EntryOptions: montar a partir dos mesmos repositórios que o diálogo atual já usa
   (contas, cartões, categorias de despesa e de receita do perfil ativo).
6. Transferência: o código de referência só mostra a conta de ORIGEM. Adicionar uma segunda
   pílula "Destino" (id_conta_destino) quando kind == KIND_TRANSFERENCIA.
7. Manter: Enter interpreta, Shift+Enter quebra linha, Esc volta da prévia para a entrada,
   Enter na prévia confirma, campos de fallback destacados, spinner/estado de carregamento
   durante a chamada.
8. Não usar cores hardcoded. Tudo via ThemePalette. Testar nos temas light e dark.

CRITÉRIOS DE ACEITE
- `pytest -v tests` íntegro (corrigir apenas testes que dependiam de widgets antigos).
- O diálogo cresce com o número de lançamentos e rola a partir de ~380 px.
- Nenhum texto truncado nas pílulas em 600 px de largura (se necessário, elide o texto e
  mostre o nome completo no tooltip).
- Sem emojis; só ícones de linha do app.
- Resposta final: resumo curto e o resultado do pytest.

A referência NÃO foi executada em Qt (foi só validada sintaticamente). Se algo não renderizar
como no PNG, corrija o QSS/layout em vez de insistir no código copiado.
```

## 3. Valores de design (mockup → tokens reais do Plutos)

| Elemento | Mockup (aprox.) | Usar em Qt |
|---|---|---|
| Fundo do diálogo | cinza claro | `p.app_background` |
| Cards, campo de entrada | branco | `p.surface_card` |
| Bordas | cinza claro | `p.border_subtle` |
| Texto principal | quase preto | `p.text_primary` |
| Texto secundário, ícones das pílulas | cinza | `p.text_secondary` |
| Botão principal | terracotta | `QPushButton#PrimaryButton` (já existe) |
| Foco do campo | terracotta | `p.primary`, borda de 1 px |
| Valor de despesa / receita / transferência | vermelho / verde / azul | `p.expense_red` / `p.income_green` / `p.transfer_indigo` |
| Pílula "Pago/Recebido" | verde suave | `p.income_badge_bg` + `p.income_green` |
| Campo preenchido por fallback | âmbar suave + pontinho | `p.warning_badge_bg` + `p.warning_orange` |
| Tile do ícone de brilho | rosa claro | `p.primary_active_pill` + ícone `p.primary` |

Medidas: diálogo 600 px de largura mínima; margens 24; espaço entre blocos 12–18; card com raio `RADIUS_MD` (12) e margens 18/14/14/12; pílulas com 34 px de altura e raio `RADIUS_PILL`; título do diálogo 18 px bold; descrição do card 15 px semibold; valor 17 px semibold; rótulo de tipo 11 px semibold em maiúsculas; botões 40 px (os do app).

Hierarquia (o que o mockup resolve): só o botão de confirmar e o foco usam a cor primária; vermelho/verde só no valor; modelo e dicas de teclado em texto discreto no rodapé; sem checkbox solto; o "x" remove o card.

## 4. Comportamento

- **Entrada:** campo de 3 linhas + "Interpretar" + 4 sugestões clicáveis (texto, sem emoji). Confirmar desabilitado.
- **Prévia:** o campo continua visível (o botão vira "Reinterpretar"); aparece "N lançamentos encontrados · revise e confirme", a legenda do pontinho âmbar (só se houver fallback) e os cards. O botão vira "Confirmar N lançamentos".
- **Card:** descrição e valor editáveis no lugar (sem caixa até passar o mouse/focar); pílulas de conta (ou cartão), categoria, data e status abrem seletor/calendário; "x" remove. Remover o último card volta à entrada.
- **Erro:** mensagem específica + botão "Lançar manualmente".

## 5. Ícones novos (adicionar em `SVG_PATHS` de `app/ui/icons.py`)

```python
    "sparkle": "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM19 16v4M17 18h4",
    "x": "M6 6l12 12M18 6L6 18",
    "chev": "M6 9l6 6 6-6",
    "clock": "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2",
```

Os outros ícones usados (`bank`, `card`, `tag`, `cal`, `check`) já existem.

## 6. Código de referência — `app/ui/dialogs/ai_entry_widgets.py`

```python
"""Widgets de UI do Lançamento Inteligente (Ctrl+K) — referência de design.

Somente interface: nenhuma chamada à IA, ao banco ou aos serviços. A lógica
(worker, validação, persistência) continua onde já está; aqui só mudam
os widgets que a exibem.

Destino sugerido: app/ui/dialogs/ai_entry_widgets.py
Pré-requisito: adicionar os ícones "sparkle", "x", "chev" e "clock" em
app/ui/icons.py (SVG_PATHS) — ver o arquivo de instruções.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from PySide6.QtCore import QDate, QEvent, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCalendarWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.config.theme_palette import RADIUS_MD, RADIUS_PILL, RADIUS_SM, ThemePalette
from app.domain.models import KIND_DESPESA, KIND_RECEITA, KIND_TRANSFERENCIA
from app.ui.components import BaseModalDialog
from app.ui.icons import get_line_icon, get_line_pixmap
from app.ui.style_manager import format_currency

Option = Tuple[str, str]  # (id, rótulo)


# --------------------------------------------------------------------------- #
# QSS — todas as cores vêm do ThemePalette (nada de hex solto)
# --------------------------------------------------------------------------- #
def build_ai_entry_qss(p: ThemePalette) -> str:
    return f"""
    QWidget#EntryList {{ background: transparent; }}
    QScrollArea#EntryScroll {{ background: transparent; border: none; }}

    QFrame#AIInputBox {{
        background: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: {RADIUS_MD}px;
    }}
    QFrame#AIInputBox[focused="true"] {{ border: 1px solid {p.primary}; }}
    QPlainTextEdit#AIInput {{
        background: transparent; border: none; color: {p.text_primary};
        font-size: 14px; selection-background-color: {p.primary}; selection-color: #FFFFFF;
    }}

    QFrame#EntryCard {{
        background: {p.surface_card};
        border: 1px solid {p.border_subtle};
        border-radius: {RADIUS_MD}px;
    }}
    QLabel#EntryKind {{ color: {p.text_secondary}; font-size: 11px; font-weight: 600; }}
    QLabel#EntryDot[kind="expense"] {{ background: {p.expense_red}; border-radius: 3px; }}
    QLabel#EntryDot[kind="income"] {{ background: {p.income_green}; border-radius: 3px; }}
    QLabel#EntryDot[kind="transfer"] {{ background: {p.transfer_indigo}; border-radius: 3px; }}

    QLineEdit#EntryTitleEdit, QLineEdit#EntryAmountEdit {{
        background: transparent; border: 1px solid transparent;
        border-radius: {RADIUS_SM}px; padding: 2px 6px;
        font-weight: 600; color: {p.text_primary};
    }}
    QLineEdit#EntryTitleEdit {{ font-size: 15px; }}
    QLineEdit#EntryAmountEdit {{ font-size: 17px; }}
    QLineEdit#EntryTitleEdit:hover, QLineEdit#EntryAmountEdit:hover {{ border: 1px solid {p.border_subtle}; }}
    QLineEdit#EntryTitleEdit:focus, QLineEdit#EntryAmountEdit:focus {{
        border: 1px solid {p.primary}; background: {p.surface_card};
    }}
    QLineEdit#EntryAmountEdit[kind="expense"] {{ color: {p.expense_red}; }}
    QLineEdit#EntryAmountEdit[kind="income"] {{ color: {p.income_green}; }}
    QLineEdit#EntryAmountEdit[kind="transfer"] {{ color: {p.transfer_indigo}; }}

    QPushButton#EntryPill {{
        background: {p.app_background}; border: 1px solid {p.border_subtle};
        border-radius: {RADIUS_PILL}px; padding: 0 28px 0 12px;
        color: {p.text_primary}; font-size: 13px; font-weight: 500;
        text-align: left; min-height: 34px; max-height: 34px;
    }}
    QPushButton#EntryPill:hover {{ border: 1px solid {p.primary}; }}
    QPushButton#EntryPill[variant="fallback"] {{
        background: {p.warning_badge_bg}; border: 1px solid {p.warning_orange};
    }}
    QPushButton#EntryPill[variant="success"] {{
        background: {p.income_badge_bg}; border: 1px solid {p.income_green};
        color: {p.income_green}; font-weight: 600; padding: 0 12px;
    }}
    QPushButton#EntryPill[variant="outline"] {{
        background: {p.surface_card}; padding: 0 12px;
    }}

    QPushButton#EntryRemove {{
        background: transparent; border: none; border-radius: {RADIUS_SM}px;
        min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
    }}
    QPushButton#EntryRemove:hover {{ background: {p.app_background}; }}

    QPushButton#AISuggestion {{
        background: {p.surface_card}; border: 1px solid {p.border_subtle};
        border-radius: {RADIUS_PILL}px; padding: 0 12px; min-height: 30px;
        max-height: 30px; font-size: 12px; color: {p.text_primary};
    }}
    QPushButton#AISuggestion:hover {{ border: 1px solid {p.primary}; }}

    QLabel#AIStatusOk {{ color: {p.income_green}; font-size: 13px; font-weight: 600; }}
    QLabel#AIHint {{ color: {p.text_secondary}; font-size: 12px; }}
    QLabel#AIError {{ color: {p.expense_red}; font-size: 13px; }}
    QLabel#AIIconTile {{ background: {p.primary_active_pill}; border-radius: {RADIUS_MD}px; }}
    QLabel#AIFallbackDot {{ background: {p.warning_orange}; border-radius: 4px; }}
    """


def _repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


# --------------------------------------------------------------------------- #
# Modelo de visualização (a UI não conhece o AIParsedEntry; faça o mapeamento)
# --------------------------------------------------------------------------- #
@dataclass
class EntryViewModel:
    kind: str                       # KIND_DESPESA | KIND_RECEITA | KIND_TRANSFERENCIA
    description: str
    amount: float                   # sempre positivo
    when: date
    effective: bool                 # pago / recebido / efetivada
    account_id: Optional[str] = None
    card_id: Optional[str] = None   # se preenchido, é despesa no cartão
    category_id: Optional[str] = None
    fallback_fields: Set[str] = field(default_factory=set)  # {"account","category"}


@dataclass
class EntryOptions:
    """Listas reais do perfil ativo para as pílulas."""
    accounts: List[Option]
    cards: List[Option]
    categories: Dict[str, List[Option]]  # chave = KIND_*


def parse_brl(text: str) -> Optional[float]:
    t = (
        text.replace("R$", "").replace("−", "").replace("-", "")
        .replace("+", "").replace(" ", "").strip()
    )
    if not t:
        return None
    if "," not in t and t.count(".") == 1 and len(t.split(".")[1]) != 3:
        t = t.replace(".", ",")  # "12.5" digitado com ponto decimal
    t = t.replace(".", "").replace(",", ".")
    try:
        value = float(t)
    except ValueError:
        return None
    return value if value > 0 else None


# --------------------------------------------------------------------------- #
# Pílula clicável: ícone + texto + chevron
# --------------------------------------------------------------------------- #
class PillButton(QPushButton):
    def __init__(
        self,
        text: str,
        icon_name: Optional[str],
        palette: ThemePalette,
        *,
        chevron: bool = True,
        variant: str = "default",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("EntryPill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_name = icon_name
        self._with_chevron = chevron
        self._p = palette
        self._chev_pm = None
        self._variant = variant
        self.setProperty("variant", variant)
        self.apply_palette(palette)

    def apply_palette(self, p: ThemePalette) -> None:
        self._p = p
        color = p.income_green if self._variant == "success" else p.text_secondary
        if self._icon_name:
            self.setIcon(get_line_icon(self._icon_name, color=color, size=15))
        self._chev_pm = (
            get_line_pixmap("chev", color=p.text_secondary, size=12)
            if self._with_chevron
            else None
        )
        self.update()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self.setProperty("variant", variant)
        self.apply_palette(self._p)
        _repolish(self)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().paintEvent(event)
        if self._chev_pm is not None and self._variant not in ("success", "outline"):
            painter = QPainter(self)
            painter.drawPixmap(self.width() - 24, (self.height() - 12) // 2, self._chev_pm)
            painter.end()


# --------------------------------------------------------------------------- #
# Card de um lançamento
# --------------------------------------------------------------------------- #
class EntryCard(QFrame):
    changed = Signal()
    removed = Signal(object)  # emite o próprio card

    def __init__(
        self,
        vm: EntryViewModel,
        options: EntryOptions,
        palette: ThemePalette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EntryCard")
        self.vm = vm
        self._options = options
        self._p = palette
        self._build()

    # -- helpers de rótulo -------------------------------------------------- #
    def _kind_text(self) -> str:
        if self.vm.kind == KIND_RECEITA:
            return "RECEITA"
        if self.vm.kind == KIND_TRANSFERENCIA:
            return "TRANSFERÊNCIA"
        return "DESPESA NO CARTÃO" if self.vm.card_id else "DESPESA"

    def _kind_key(self) -> str:
        return {KIND_RECEITA: "income", KIND_TRANSFERENCIA: "transfer"}.get(self.vm.kind, "expense")

    def _status_text(self) -> str:
        if self.vm.card_id:
            return "Na fatura"
        if self.vm.kind == KIND_RECEITA:
            return "Recebido" if self.vm.effective else "Pendente"
        return "Pago" if self.vm.effective else "Pendente"

    def _label_of(self, options: Sequence[Option], opt_id: Optional[str], fallback: str) -> str:
        for oid, label in options:
            if oid == opt_id:
                return label
        return fallback

    def _amount_text(self) -> str:
        sign = {KIND_DESPESA: "− ", KIND_RECEITA: "+ "}.get(self.vm.kind, "")
        return f"{sign}{format_currency(self.vm.amount)}"

    # -- construção ---------------------------------------------------------- #
    def _build(self) -> None:
        p = self._p
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 14, 12)
        root.setSpacing(10)

        # Linha 1: tipo + descrição | valor
        top = QHBoxLayout()
        top.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(2)

        kind_row = QHBoxLayout()
        kind_row.setSpacing(6)
        self.dot = QLabel()
        self.dot.setObjectName("EntryDot")
        self.dot.setFixedSize(6, 6)
        self.dot.setProperty("kind", self._kind_key())
        self.lbl_kind = QLabel(self._kind_text())
        self.lbl_kind.setObjectName("EntryKind")
        kind_row.addWidget(self.dot)
        kind_row.addWidget(self.lbl_kind)
        kind_row.addStretch()
        left.addLayout(kind_row)

        self.ed_title = QLineEdit(self.vm.description)
        self.ed_title.setObjectName("EntryTitleEdit")
        self.ed_title.editingFinished.connect(self._on_title)
        left.addWidget(self.ed_title)
        top.addLayout(left, stretch=1)

        self.ed_amount = QLineEdit(self._amount_text())
        self.ed_amount.setObjectName("EntryAmountEdit")
        self.ed_amount.setProperty("kind", self._kind_key())
        self.ed_amount.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.ed_amount.setFixedWidth(150)
        self.ed_amount.editingFinished.connect(self._on_amount)
        top.addWidget(self.ed_amount, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)

        # Linha 2: pílulas editáveis
        row = QHBoxLayout()
        row.setSpacing(8)

        if self.vm.card_id:
            src_label = self._label_of(self._options.cards, self.vm.card_id, "Cartão")
            src_icon, src_opts = "card", self._options.cards
        else:
            src_label = self._label_of(self._options.accounts, self.vm.account_id, "Conta")
            src_icon, src_opts = "bank", self._options.accounts
        self.pill_source = PillButton(
            src_label, src_icon, p,
            variant="fallback" if "account" in self.vm.fallback_fields else "default",
        )
        self.pill_source.clicked.connect(lambda: self._pick(self.pill_source, src_opts, self._set_source))
        row.addWidget(self.pill_source)

        if self.vm.kind != KIND_TRANSFERENCIA:  # transferência não tem categoria
            cat_opts = self._options.categories.get(self.vm.kind, [])
            self.pill_cat = PillButton(
                self._label_of(cat_opts, self.vm.category_id, "Categoria"), "tag", p,
                variant="fallback" if "category" in self.vm.fallback_fields else "default",
            )
            self.pill_cat.clicked.connect(lambda: self._pick(self.pill_cat, cat_opts, self._set_category))
            row.addWidget(self.pill_cat)

        self.pill_date = PillButton(self.vm.when.strftime("%d/%m/%Y"), "cal", p)
        self.pill_date.clicked.connect(self._pick_date)
        row.addWidget(self.pill_date)

        self.pill_status = PillButton(
            self._status_text(), "check", p, chevron=False,
            variant="success" if self.vm.effective else "outline",
        )
        self.pill_status.clicked.connect(self._toggle_status)
        row.addWidget(self.pill_status)
        row.addStretch()

        btn_rm = QPushButton()
        btn_rm.setObjectName("EntryRemove")
        btn_rm.setIcon(get_line_icon("x", color=p.text_secondary, size=16))
        btn_rm.setToolTip("Remover este lançamento")
        btn_rm.setAccessibleName("Remover lançamento")
        btn_rm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_rm.clicked.connect(lambda: self.removed.emit(self))
        row.addWidget(btn_rm)
        root.addLayout(row)

    # -- interações ---------------------------------------------------------- #
    def _pick(self, pill: PillButton, options: Sequence[Option], on_pick: Callable[[str, str], None]) -> None:
        menu = QMenu(pill)
        current = {self.vm.account_id, self.vm.card_id, self.vm.category_id}
        for opt_id, label in options:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(opt_id in current)
            act.triggered.connect(lambda _=False, i=opt_id, l=label: on_pick(i, l))
        menu.exec(pill.mapToGlobal(pill.rect().bottomLeft()))

    def _set_source(self, opt_id: str, label: str) -> None:
        if self.vm.card_id:
            self.vm.card_id = opt_id
        else:
            self.vm.account_id = opt_id
            self.vm.fallback_fields.discard("account")
            self.pill_source.set_variant("default")
        self.pill_source.setText(label)
        self.changed.emit()

    def _set_category(self, opt_id: str, label: str) -> None:
        self.vm.category_id = opt_id
        self.vm.fallback_fields.discard("category")
        self.pill_cat.set_variant("default")
        self.pill_cat.setText(label)
        self.changed.emit()

    def _pick_date(self) -> None:
        menu = QMenu(self.pill_date)
        cal = QCalendarWidget()
        cal.setSelectedDate(QDate(self.vm.when.year, self.vm.when.month, self.vm.when.day))

        def picked(qd: QDate) -> None:
            self.vm.when = date(qd.year(), qd.month(), qd.day())
            self.pill_date.setText(self.vm.when.strftime("%d/%m/%Y"))
            menu.close()
            self.changed.emit()

        cal.clicked.connect(picked)
        action = QWidgetAction(menu)
        action.setDefaultWidget(cal)
        menu.addAction(action)
        menu.exec(self.pill_date.mapToGlobal(self.pill_date.rect().bottomLeft()))

    def _toggle_status(self) -> None:
        self.vm.effective = not self.vm.effective
        self.pill_status.setText(self._status_text())
        self.pill_status.set_variant("success" if self.vm.effective else "outline")
        self.changed.emit()

    def _on_title(self) -> None:
        text = self.ed_title.text().strip()
        if text:
            self.vm.description = text
            self.changed.emit()
        else:
            self.ed_title.setText(self.vm.description)

    def _on_amount(self) -> None:
        value = parse_brl(self.ed_amount.text())
        if value is not None:
            self.vm.amount = value
            self.changed.emit()
        self.ed_amount.setText(self._amount_text())  # reformata ou restaura


# --------------------------------------------------------------------------- #
# Diálogo (somente a casca de UI; ligue os sinais à lógica existente)
# --------------------------------------------------------------------------- #
class AIQuickEntryDialogView(BaseModalDialog):
    """Substitui o layout do diálogo atual mantendo a lógica.

    Estados: "input" (campo + sugestões) e "preview" (campo + cards).
      - Enter no campo = interpretar; Shift+Enter = nova linha.
      - Em "preview": Enter confirma (botão padrão), Esc volta para "input".
    """

    interpret_requested = Signal(str)
    confirmed = Signal(list)         # list[EntryViewModel] (já editados)
    manual_requested = Signal()      # abre o lançamento manual existente

    SUGGESTIONS = ["Pão 10 cartão", "Almoço 45,90", "Luz 180 conta", "Salário 3500"]

    def __init__(self, palette: ThemePalette, parent: Optional[QWidget] = None) -> None:
        super().__init__("", "", min_width=600, parent=parent)
        self.setWindowTitle("Lançamento inteligente")
        self._p = palette
        self._state = "input"
        self._cards: List[EntryCard] = []
        self.setStyleSheet(build_ai_entry_qss(palette))
        self._build()
        self.show_input_state()

    # -- construção ---------------------------------------------------------- #
    def _build(self) -> None:
        p = self._p

        # Cabeçalho: ícone em tile + título + subtítulo
        head = QHBoxLayout()
        head.setSpacing(12)
        tile = QLabel()
        tile.setObjectName("AIIconTile")
        tile.setFixedSize(40, 40)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setPixmap(get_line_pixmap("sparkle", color=p.primary, size=20))
        head.addWidget(tile)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        lbl_t = QLabel("Lançamento inteligente")
        lbl_t.setObjectName("SectionTitle")
        lbl_t.setStyleSheet("font-size: 18px; font-weight: 700;")
        lbl_s = QLabel("Descreva um ou vários lançamentos, do jeito que você falaria.")
        lbl_s.setObjectName("SubTitle")
        titles.addWidget(lbl_t)
        titles.addWidget(lbl_s)
        head.addLayout(titles, stretch=1)
        self._root_lay.insertLayout(0, head)

        # Campo de entrada + botão
        self.input_box = QFrame()
        self.input_box.setObjectName("AIInputBox")
        box = QHBoxLayout(self.input_box)
        box.setContentsMargins(14, 10, 10, 10)
        box.setSpacing(10)
        self.txt_input = QPlainTextEdit()
        self.txt_input.setObjectName("AIInput")
        self.txt_input.setPlaceholderText(
            "Ex.: almoço 45,90 no nubank\nuber 23 cartão\nrecebi 3500 de salário"
        )
        self.txt_input.setFixedHeight(70)
        self.txt_input.installEventFilter(self)
        box.addWidget(self.txt_input, stretch=1)
        self.btn_interpret = QPushButton("Interpretar")
        self.btn_interpret.setObjectName("PrimaryButton")
        self.btn_interpret.clicked.connect(self._emit_interpret)
        box.addWidget(self.btn_interpret, alignment=Qt.AlignmentFlag.AlignBottom)
        self.content_layout.addWidget(self.input_box)

        # Sugestões (só no estado "input")
        self.suggestions = QWidget()
        sug = QHBoxLayout(self.suggestions)
        sug.setContentsMargins(0, 0, 0, 0)
        sug.setSpacing(8)
        lbl = QLabel("Experimente")
        lbl.setObjectName("AIHint")
        sug.addWidget(lbl)
        for text in self.SUGGESTIONS:
            b = QPushButton(text)
            b.setObjectName("AISuggestion")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, t=text: self._use_suggestion(t))
            sug.addWidget(b)
        sug.addStretch()
        self.content_layout.addWidget(self.suggestions)

        # Erro (oculto)
        self.lbl_error = QLabel()
        self.lbl_error.setObjectName("AIError")
        self.lbl_error.setWordWrap(True)
        self.btn_manual = QPushButton("Lançar manualmente")
        self.btn_manual.setObjectName("GhostButton")
        self.btn_manual.clicked.connect(self.manual_requested.emit)
        self.error_row = QWidget()
        er = QHBoxLayout(self.error_row)
        er.setContentsMargins(0, 0, 0, 0)
        er.addWidget(self.lbl_error, stretch=1)
        er.addWidget(self.btn_manual)
        self.content_layout.addWidget(self.error_row)

        # Status da prévia
        self.status_row = QWidget()
        sr = QHBoxLayout(self.status_row)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(get_line_pixmap("check", color=p.income_green, size=16))
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("AIStatusOk")
        hint = QLabel("· revise e confirme")
        hint.setObjectName("AIHint")
        sr.addWidget(ic)
        sr.addWidget(self.lbl_status)
        sr.addWidget(hint)
        sr.addStretch()
        self.fallback_legend = QWidget()
        fl = QHBoxLayout(self.fallback_legend)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        dot = QLabel()
        dot.setObjectName("AIFallbackDot")
        dot.setFixedSize(8, 8)
        txt = QLabel("preenchido automaticamente")
        txt.setObjectName("AIHint")
        fl.addWidget(dot)
        fl.addWidget(txt)
        sr.addWidget(self.fallback_legend)
        self.content_layout.addWidget(self.status_row)

        # Lista de cards (rola se passar da altura máxima)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("EntryScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.scroll.setMaximumHeight(380)
        holder = QWidget()
        holder.setObjectName("EntryList")
        self.list_lay = QVBoxLayout(holder)
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(12)
        self.list_lay.addStretch()
        self.scroll.setWidget(holder)
        self.content_layout.addWidget(self.scroll)

        # Rodapé: dicas de teclado + modelo, à esquerda dos botões existentes
        foot = QVBoxLayout()
        foot.setSpacing(2)
        self.lbl_keys = QLabel()
        self.lbl_keys.setObjectName("AIHint")
        self.lbl_model = QLabel("")
        self.lbl_model.setObjectName("AIHint")
        foot.addWidget(self.lbl_keys)
        foot.addWidget(self.lbl_model)
        self.btn_row.insertLayout(0, foot)

    # -- API pública para a lógica existente --------------------------------- #
    def set_model_name(self, name: str) -> None:
        self.lbl_model.setText(f"via {name}" if name else "")

    def set_loading(self, loading: bool) -> None:
        self.btn_interpret.setEnabled(not loading)
        self.txt_input.setReadOnly(loading)
        self.btn_interpret.setText("Interpretando…" if loading else self._interpret_label())

    def show_error(self, message: str) -> None:
        self.lbl_error.setText(message)
        self.error_row.setVisible(True)
        self.set_loading(False)

    def show_input_state(self) -> None:
        self._state = "input"
        self.suggestions.setVisible(True)
        self.status_row.setVisible(False)
        self.scroll.setVisible(False)
        self.error_row.setVisible(False)
        self.btn_confirm.setEnabled(False)
        self.btn_confirm.setText("Confirmar")
        self.lbl_keys.setText("Enter interpreta · Shift+Enter nova linha")
        self.btn_interpret.setText("Interpretar")
        self.btn_interpret.setObjectName("PrimaryButton")
        _repolish(self.btn_interpret)
        self.txt_input.setFocus()

    def show_preview(self, entries: List[EntryViewModel], options: EntryOptions) -> None:
        self._state = "preview"
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        for vm in entries:
            card = EntryCard(vm, options, self._p)
            card.removed.connect(self._remove_card)
            card.changed.connect(self._refresh_footer)
            self.list_lay.insertWidget(self.list_lay.count() - 1, card)
            self._cards.append(card)
        self.suggestions.setVisible(False)
        self.error_row.setVisible(False)
        self.status_row.setVisible(True)
        self.scroll.setVisible(True)
        self.lbl_keys.setText("Enter confirma · Esc volta")
        self.btn_interpret.setText("Reinterpretar")
        self.btn_interpret.setObjectName("SecondaryButton")
        _repolish(self.btn_interpret)
        self.set_loading(False)
        self._refresh_footer()
        self.btn_confirm.setFocus()

    def collect_entries(self) -> List[EntryViewModel]:
        return [c.vm for c in self._cards]

    def done_ok(self) -> None:
        """Chame depois de gravar com sucesso; fecha o diálogo."""
        super().accept()

    # -- internos ------------------------------------------------------------ #
    def _interpret_label(self) -> str:
        return "Reinterpretar" if self._state == "preview" else "Interpretar"

    def _use_suggestion(self, text: str) -> None:
        self.txt_input.setPlainText(text)
        self._emit_interpret()

    def _emit_interpret(self) -> None:
        text = self.txt_input.toPlainText().strip()
        if text:
            self.interpret_requested.emit(text)

    def _remove_card(self, card: EntryCard) -> None:
        self._cards.remove(card)
        card.setParent(None)
        card.deleteLater()
        if not self._cards:
            self.show_input_state()
        else:
            self._refresh_footer()

    def _refresh_footer(self) -> None:
        n = len(self._cards)
        self.lbl_status.setText(f"{n} lançamento{'s' if n != 1 else ''} encontrado{'s' if n != 1 else ''}")
        self.btn_confirm.setEnabled(n > 0)
        self.btn_confirm.setText(f"Confirmar {n} lançamento{'s' if n != 1 else ''}")
        self.fallback_legend.setVisible(any(c.vm.fallback_fields for c in self._cards))

    def accept(self) -> None:  # noqa: D401
        if self._state == "preview" and self._cards:
            self.confirmed.emit(self.collect_entries())
        # não fecha aqui: a lógica existente chama done_ok() após gravar

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.key() == Qt.Key.Key_Escape and self._state == "preview":
            self.show_input_state()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802 (Qt)
        if obj is self.txt_input:
            if ev.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self.input_box.setProperty("focused", ev.type() == QEvent.Type.FocusIn)
                _repolish(self.input_box)
            elif ev.type() == QEvent.Type.KeyPress and ev.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
            ):
                if not (ev.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._emit_interpret()
                    return True
        return super().eventFilter(obj, ev)
```

## 7. Ligação com a lógica existente (exemplo; ajuste aos nomes reais)

```python
def to_view_model(e) -> EntryViewModel:
    """AIParsedEntry (Etapa 1) -> EntryViewModel. Use os nomes reais dos campos."""
    fb = set(getattr(e, "campos_fallback", []) or [])
    return EntryViewModel(
        kind=e.tipo,
        description=e.descricao,
        amount=e.valor,
        when=e.data,
        effective=e.efetivada,
        account_id=e.id_conta,
        card_id=e.id_cartao,
        category_id=e.id_categoria,
        fallback_fields={
            "account" if ("id_conta" in fb or "conta" in fb) else None,
            "category" if ("id_categoria" in fb or "categoria" in fb) else None,
        } - {None},
    )


def apply_view_model(e, vm: EntryViewModel) -> None:
    """Copia as edições do usuário de volta antes de gravar."""
    e.descricao, e.valor, e.data, e.efetivada = vm.description, vm.amount, vm.when, vm.effective
    e.id_conta, e.id_cartao, e.id_categoria = vm.account_id, vm.card_id, vm.category_id
```

## 8. Limitações conhecidas (para o agente verificar)

- O código foi validado só sintaticamente; não foi executado em Qt. Ajuste o que não renderizar como no PNG.
- Transferência: falta a pílula de conta de destino (item 6 do prompt). Subcategoria também não aparece (a pílula de categoria deve escolher a categoria padrão da subcategoria, como o diálogo atual já faz).
- A seta do chevron é desenhada em `paintEvent`; se a pílula parecer sem folga à direita, aumente o `padding-right` no QSS.
- `text_secondary` do app (#7B8190) tem contraste baixo sobre branco em textos de 11–12 px. É uma decisão do design system existente; se quiser, use `text_primary` nos textos de dica menores.
