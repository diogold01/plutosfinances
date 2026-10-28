"""
Gerador da Base de Dados Modelo Completa — "João Brasileiro (Renda R$ 5.000/mês)".

Popula todas as tabelas relacionais e módulos do aplicativo para oferecer uma visão
panorâmica imediata em todas as 13 telas da aplicação:
1. Perfil principal: "João Brasileiro" (BRL) + Segundo perfil "Viagem & Família"
2. 4 Contas Bancárias: Nubank (Principal), Itaú (Salário), Caixa (Poupança/Reserva), Carteira Física
3. 2 Cartões de Crédito: Nubank Mastercard Gold (Limite R$ 4.500) e Itaú Click Visa (Limite R$ 3.500)
4. Categorias, Subcategorias e 8 Tags coloridas (#essencial, #fixo-mensal, #lazer-familia, etc.)
5. Receitas de R$ 5.000,00/mês (Salário CLT R$ 4.450 + Vale Alimentação/Home Office R$ 550) + Rendas Extras
6. Despesas fixas, avulsas, parceladas, com rateio multi-categoria (`SplitDTO`) e compras no cartão
   distribuídas nos últimos 5 meses, no mês atual e nos próximos meses (parcelas futuras)
7. Transferências mensais entre contas (portabilidade Itaú -> Nubank e aporte em Reserva)
8. Faturas de cartão pagas nos meses anteriores + Fatura atual aberta com compras, parcelas,
   adiantamento parcial de fatura e estorno demonstrativo
9. 6 Orçamentos Mensais (Alimentação, Moradia, Transporte, Lazer, Saúde e Tag #essencial)
10. 3 Objetivos Financeiros com múltiplos depósitos/aportes históricos
11. 2 Empréstimos (1 concedido a receber e 1 tomado a pagar) com amortizações parciais
12. 4 Notas & Lembretes financeiros + 2 Modelos de Importação CSV (`modelos_csv`)
"""

from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.app_settings import (
    DEFAULT_DB_FILE,
    DEFAULT_USER_DATA_DIR,
    AppSettings,
)
from app.database.connection_manager import ConnectionManager
from app.database.repositories.account_repository import AccountRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.profile_repository import ProfileRepository
from app.database.repositories.tag_repository import TagRepository
from app.domain.date_utils import add_months, clamp_day
from app.domain.models import (
    KIND_DESPESA,
    KIND_RECEITA,
    REC_FIXA_DESPESA,
    REC_FIXA_MENSAL,
    REC_PARCELADA,
    REC_UNICA,
    SplitDTO,
)
from app.domain.services.analytics_service import AnalyticsService
from app.domain.services.budget_service import BudgetService
from app.domain.services.credit_card_service import CreditCardService
from app.domain.services.goal_service import GoalService
from app.domain.services.transaction_service import TransactionService
from app.io_module.contracts import CSVColumnMapping
from app.io_module.io_orchestrator import DataIOOrchestrator


def _ensure_cat_sub(
    cat_repo: CategoryRepository,
    kind: str,
    cat_name: str,
    sub_name: str,
    color_hex: str,
    profile_id: str = "1",
) -> Tuple[str, str]:
    cats = cat_repo.list_categories(kind, profile_id)
    cat = next(
        (c for c in cats if c.nome.strip().lower() == cat_name.strip().lower()),
        None,
    )
    if cat is None:
        cat = cat_repo.create_category(
            kind, cat_name, color_hex=color_hex, profile_id=profile_id
        )
    sub = next(
        (
            s
            for s in cat.subcategories
            if s.nome.strip().lower() == sub_name.strip().lower()
        ),
        None,
    )
    if sub is None:
        sub = cat_repo.create_subcategory(
            kind, cat.id, sub_name, color_hex=color_hex, profile_id=profile_id
        )
    return cat.id, sub.id


def build_joao_brasileiro_database(target_db_path: Path) -> Path:
    """Cria e popula integralmente a base modelo de João Brasileiro (R$ 5.000/mês)."""
    target_db_path = Path(target_db_path).resolve()
    target_db_path.parent.mkdir(parents=True, exist_ok=True)

    settings_path = target_db_path.parent / "app_settings.json"
    settings = AppSettings.load(settings_path)
    settings.active_db_path = str(target_db_path)
    settings.active_profile_id = "1"
    settings.save()

    db = ConnectionManager(settings=settings, auto_connect=False)
    db.create_new_database(target_db_path, overwrite=True)

    profile_repo = ProfileRepository(db)
    acc_repo = AccountRepository(db)
    cat_repo = CategoryRepository(db)
    tag_repo = TagRepository(db)
    tx_srv = TransactionService(db)
    card_srv = CreditCardService(db, tx_srv)
    budget_srv = BudgetService(db, tx_srv)
    goal_srv = GoalService(db)
    analytics_srv = AnalyticsService(db, tx_srv)
    io_orch = DataIOOrchestrator(db, tx_srv)

    today = date.today()
    cur_y, cur_m = today.year, today.month
    first_month_date = add_months(date(cur_y, cur_m, 1), -5)

    # 1. Atualiza o Perfil Principal para "João Brasileiro"
    with db.transaction() as cur:
        cur.execute(
            "UPDATE profiles SET name = ?, current = 'S', currency = 'BRL' WHERE id = '1'",
            ("João Brasileiro",),
        )
    profile_id = "1"

    # 2. Cria as 4 Contas Bancárias de João Brasileiro
    acc_nubank = acc_repo.create_account(
        descricao="Nubank (Conta Principal)",
        id_categoria="3",
        saldo_inicial=1850.00,
        cheque_especial=1000.00,
        padrao="S",
        fav=1,
        image_key="ic_nubank.png",
        profile_id=profile_id,
        mes_inicial=first_month_date.month,
        ano_inicial=first_month_date.year,
    )
    acc_itau = acc_repo.create_account(
        descricao="Itaú (Conta Salário)",
        id_categoria="3",
        saldo_inicial=420.00,
        cheque_especial=1500.00,
        padrao="N",
        fav=1,
        image_key="ic_itau.png",
        profile_id=profile_id,
        mes_inicial=first_month_date.month,
        ano_inicial=first_month_date.year,
    )
    acc_caixa = acc_repo.create_account(
        descricao="Caixa (Poupança Reserva)",
        id_categoria="4",
        saldo_inicial=5500.00,
        investimento="S",
        padrao="N",
        image_key="ic_caixa.png",
        profile_id=profile_id,
        mes_inicial=first_month_date.month,
        ano_inicial=first_month_date.year,
    )
    acc_carteira = acc_repo.create_account(
        descricao="Carteira Física (Dinheiro)",
        id_categoria="1",
        saldo_inicial=150.00,
        padrao="N",
        image_key="ic_carteira.png",
        profile_id=profile_id,
        mes_inicial=first_month_date.month,
        ano_inicial=first_month_date.year,
    )

    # 3. Cria os 2 Cartões de Crédito
    card_nubank = card_srv.create_card(
        nome="Nubank Mastercard Gold",
        limite=4500.00,
        dia_fecha=5,
        dia_venc=12,
        id_conta=acc_nubank,
        profile_id=profile_id,
        color_hex="#8A05BE",
        brand_key="mastercard",
        padrao=True,
    )
    card_itau = card_srv.create_card(
        nome="Itaú Click Visa Platinum",
        limite=3500.00,
        dia_fecha=18,
        dia_venc=25,
        id_conta=acc_itau,
        profile_id=profile_id,
        color_hex="#EC7000",
        brand_key="visa",
        padrao=False,
    )

    # 4. Cria Tags
    tags_spec = [
        ("essencial", "#1976D2"),
        ("fixo-mensal", "#00897B"),
        ("lazer-familia", "#8E24AA"),
        ("trabalho", "#43A047"),
        ("parcelado", "#F4511E"),
        ("reserva", "#3949AB"),
        ("mercado", "#FB8C00"),
        ("saude", "#E53935"),
    ]
    tags_map: Dict[str, str] = {}
    for t_name, t_color in tags_spec:
        tags_map[t_name] = tag_repo.create_tag(
            t_name, color_hex=t_color, profile_id=profile_id
        ).id

    # 5. Garante Categorias e Subcategorias detalhadas
    c_moradia, s_aluguel = _ensure_cat_sub(
        cat_repo, "DESPESA", "Moradia", "Aluguel & Condomínio", "#1E88E5"
    )
    _, s_energia = _ensure_cat_sub(
        cat_repo, "DESPESA", "Moradia", "Energia Elétrica & Água", "#1E88E5"
    )
    _, s_internet = _ensure_cat_sub(
        cat_repo, "DESPESA", "Moradia", "Internet Fibra & Celular", "#1E88E5"
    )
    _, s_limpeza = _ensure_cat_sub(
        cat_repo, "DESPESA", "Moradia", "Produtos de Limpeza", "#1E88E5"
    )

    c_alim, s_mercado = _ensure_cat_sub(
        cat_repo, "DESPESA", "Alimentação", "Supermercado & Atacadão", "#FB8C00"
    )
    _, s_restaurante = _ensure_cat_sub(
        cat_repo, "DESPESA", "Alimentação", "Restaurantes & iFood", "#FB8C00"
    )
    _, s_padaria = _ensure_cat_sub(
        cat_repo, "DESPESA", "Alimentação", "Padaria & Lanches", "#FB8C00"
    )

    c_transp, s_combustivel = _ensure_cat_sub(
        cat_repo, "DESPESA", "Transporte", "Combustível & Manutenção", "#546E7A"
    )
    _, s_uber = _ensure_cat_sub(
        cat_repo, "DESPESA", "Transporte", "Uber / 99 / Transporte App", "#546E7A"
    )
    _, s_seguro = _ensure_cat_sub(
        cat_repo, "DESPESA", "Transporte", "Seguro & IPVA", "#546E7A"
    )

    c_saude, s_plano = _ensure_cat_sub(
        cat_repo, "DESPESA", "Saúde", "Plano de Saúde", "#E53935"
    )
    _, s_farmacia = _ensure_cat_sub(
        cat_repo, "DESPESA", "Saúde", "Farmácia & Medicamentos", "#E53935"
    )
    _, s_academia = _ensure_cat_sub(
        cat_repo, "DESPESA", "Saúde", "Academia & Esportes", "#E53935"
    )

    c_lazer, s_streaming = _ensure_cat_sub(
        cat_repo, "DESPESA", "Lazer", "Streaming (Netflix / Spotify)", "#8E24AA"
    )
    _, s_passeios = _ensure_cat_sub(
        cat_repo, "DESPESA", "Lazer", "Cinema, Bares & Passeios", "#8E24AA"
    )

    c_educ, s_cursos = _ensure_cat_sub(
        cat_repo, "DESPESA", "Educação", "Cursos & Livros Técnicos", "#3949AB"
    )
    c_vest, s_roupas = _ensure_cat_sub(
        cat_repo, "DESPESA", "Vestuário", "Roupas & Calçados", "#00ACC1"
    )

    # Categorias de Receita
    c_sal, s_clt = _ensure_cat_sub(
        cat_repo, "RECEITA", "Salário", "Salário Mensal CLT", "#2E7D32"
    )
    _, s_benef = _ensure_cat_sub(
        cat_repo, "RECEITA", "Salário", "Vale Alimentação / Auxílio", "#2E7D32"
    )
    c_extra, s_freela = _ensure_cat_sub(
        cat_repo, "RECEITA", "Outras Receitas", "Freelance & Serviços", "#00897B"
    )
    c_rend, s_cdi = _ensure_cat_sub(
        cat_repo, "RECEITA", "Investimentos", "Rendimentos Poupança / CDI", "#1565C0"
    )

    # 6. Popula Histórico dos últimos 5 meses + Mês Atual (offset -5 até 0)
    extra_incomes = [180.0, 0.0, 350.0, 220.0, 400.0, 320.0]
    light_bills = [172.30, 168.90, 181.40, 194.20, 179.80, 188.50]
    fuel_costs = [310.00, 340.00, 295.00, 360.00, 330.00, 345.00]
    market_cash = [690.00, 740.00, 715.00, 760.00, 730.00, 780.00]

    for idx, offset in enumerate(range(-5, 1)):
        m_date = add_months(date(cur_y, cur_m, 1), offset)
        y, m = m_date.year, m_date.month
        is_past_or_current = offset <= 0
        is_current_month = offset == 0

        # --- RECEITAS DO MÊS (R$ 5.000,00 de renda base: R$ 4.450 CLT + R$ 550 Vale/Auxílio) ---
        tx_srv.create_income(
            descricao="Salário Mensal CLT — João Brasileiro",
            valor=4450.00,
            data=date(y, m, 5),
            id_conta=acc_itau,
            profile_id=profile_id,
            id_categoria=c_sal,
            id_subcategoria=s_clt,
            recebido=True,
            data_efetivacao=date(y, m, 5),
            obs="Salário líquido depositado no 5º dia útil",
            tag_ids=[tags_map["trabalho"], tags_map["fixo-mensal"]],
        )
        tx_srv.create_income(
            descricao="Vale Refeição / Auxílio Home Office",
            valor=550.00,
            data=date(y, m, 5),
            id_conta=acc_nubank,
            profile_id=profile_id,
            id_categoria=c_sal,
            id_subcategoria=s_benef,
            recebido=True,
            data_efetivacao=date(y, m, 5),
            obs="Compõe a renda mensal total de R$ 5.000,00",
            tag_ids=[tags_map["trabalho"], tags_map["essencial"]],
        )
        # Rendimento mensal da Reserva Caixa
        tx_srv.create_income(
            descricao="Rendimento Mensal Poupança / CDI",
            valor=round(48.50 + idx * 4.20, 2),
            data=date(y, m, 15),
            id_conta=acc_caixa,
            profile_id=profile_id,
            id_categoria=c_rend,
            id_subcategoria=s_cdi,
            recebido=True,
            data_efetivacao=date(y, m, 15),
            tag_ids=[tags_map["reserva"]],
        )
        if extra_incomes[idx] > 0:
            tx_srv.create_income(
                descricao="Manutenção / Consultoria TI Fim de Semana",
                valor=extra_incomes[idx],
                data=date(y, m, 22),
                id_conta=acc_nubank,
                profile_id=profile_id,
                id_categoria=c_extra,
                id_subcategoria=s_freela,
                recebido=not is_current_month,  # No mês atual fica pendente para aparecer "A Receber"
                data_efetivacao=date(y, m, 22) if not is_current_month else None,
                obs="Serviço extra por fora do salário de R$ 5.000",
                tag_ids=[tags_map["trabalho"]],
            )

        # --- TRANSFERÊNCIAS ENTRE CONTAS ---
        tx_srv.create_transfer(
            descricao="Portabilidade Salário Itaú → Nubank",
            valor=2800.00,
            data=date(y, m, 6),
            id_conta_origem=acc_itau,
            id_conta_destino=acc_nubank,
            profile_id=profile_id,
            efetivada=True,
            data_efetivacao=date(y, m, 6),
            obs="Transferência PIX automática após cair salário",
        )
        tx_srv.create_transfer(
            descricao="Aporte Mensal Reserva de Emergência",
            valor=500.00,
            data=date(y, m, 7),
            id_conta_origem=acc_itau,
            id_conta_destino=acc_caixa,
            profile_id=profile_id,
            efetivada=True,
            data_efetivacao=date(y, m, 7),
            obs="10% da renda de R$ 5.000 separados todo mês",
            tag_ids=[tags_map["reserva"]],
        )

        # --- DESPESAS EM CONTA CORRENTE ---
        # 1. Aluguel + Condomínio
        tx_srv.create_expense(
            descricao="Aluguel Apartamento + Condomínio",
            valor=1350.00,
            data_vencimento=date(y, m, 10),
            profile_id=profile_id,
            id_conta=acc_nubank,
            id_categoria=c_moradia,
            id_subcategoria=s_aluguel,
            pago=True,
            data_efetivacao=date(y, m, 10),
            obs="Boleto imobiliária",
            tag_ids=[tags_map["essencial"], tags_map["fixo-mensal"]],
        )
        # 2. Energia Elétrica & Água
        tx_srv.create_expense(
            descricao="Conta de Luz (Enel) + Água (Sabesp)",
            valor=light_bills[idx],
            data_vencimento=date(y, m, 14),
            profile_id=profile_id,
            id_conta=acc_nubank,
            id_categoria=c_moradia,
            id_subcategoria=s_energia,
            pago=True,
            data_efetivacao=date(y, m, 14),
            tag_ids=[tags_map["essencial"], tags_map["fixo-mensal"]],
        )
        # 3. Internet Fibra + Plano Celular
        tx_srv.create_expense(
            descricao="Vivo Fibra 500Mb + Plano Pós",
            valor=139.90,
            data_vencimento=date(y, m, 18),
            profile_id=profile_id,
            id_conta=acc_nubank,
            id_categoria=c_moradia,
            id_subcategoria=s_internet,
            pago=not is_current_month,
            data_efetivacao=date(y, m, 18) if not is_current_month else None,
            tag_ids=[tags_map["essencial"], tags_map["fixo-mensal"]],
        )
        # 4. Compra do Mês Atacadão (Com Rateio Multi-Categoria `SplitDTO`)
        total_mkt = market_cash[idx]
        tx_srv.create_expense(
            descricao="Compra do Mês Atacadão (Rateio Alimentação/Limpeza/Lazer)",
            valor=total_mkt,
            data_vencimento=date(y, m, 8),
            profile_id=profile_id,
            id_conta=acc_nubank,
            splits=[
                SplitDTO(
                    id_categoria=c_alim,
                    id_subcategoria=s_mercado,
                    valor=round(total_mkt - 190.0, 2),
                    obs="Mercearia, carnes e hortifruti",
                ),
                SplitDTO(
                    id_categoria=c_moradia,
                    id_subcategoria=s_limpeza,
                    valor=115.00,
                    obs="Sabão, detergente e higiene",
                ),
                SplitDTO(
                    id_categoria=c_lazer,
                    id_subcategoria=s_passeios,
                    valor=75.00,
                    obs="Churrasco e bebidas fim de semana",
                ),
            ],
            pago=True,
            data_efetivacao=date(y, m, 8),
            obs="Compra mensal dividida em 3 categorias",
            tag_ids=[tags_map["essencial"], tags_map["mercado"]],
        )
        # 5. Combustível
        tx_srv.create_expense(
            descricao="Abastecimento Posto Ipiranga / Shell",
            valor=fuel_costs[idx],
            data_vencimento=date(y, m, 16),
            profile_id=profile_id,
            id_conta=acc_itau,
            id_categoria=c_transp,
            id_subcategoria=s_combustivel,
            pago=True,
            data_efetivacao=date(y, m, 16),
            tag_ids=[tags_map["essencial"]],
        )
        # 6. Plano de Saúde + Academia
        tx_srv.create_expense(
            descricao="Plano de Saúde Unimed Coparticipação",
            valor=289.00,
            data_vencimento=date(y, m, 20),
            profile_id=profile_id,
            id_conta=acc_itau,
            id_categoria=c_saude,
            id_subcategoria=s_plano,
            pago=not is_current_month,
            data_efetivacao=date(y, m, 20) if not is_current_month else None,
            tag_ids=[tags_map["saude"], tags_map["fixo-mensal"]],
        )
        tx_srv.create_expense(
            descricao="Mensalidade Smart Fit",
            valor=119.90,
            data_vencimento=date(y, m, 24),
            profile_id=profile_id,
            id_conta=acc_nubank,
            id_categoria=c_saude,
            id_subcategoria=s_academia,
            pago=not is_current_month,
            data_efetivacao=date(y, m, 24) if not is_current_month else None,
            tag_ids=[tags_map["saude"]],
        )
        # 7. Padaria & Cafés em Dinheiro (Carteira Física)
        tx_srv.create_expense(
            descricao="Padaria, Feira Livre e Estacionamento",
            valor=95.00,
            data_vencimento=date(y, m, 12),
            profile_id=profile_id,
            id_conta=acc_carteira,
            id_categoria=c_alim,
            id_subcategoria=s_padaria,
            pago=True,
            data_efetivacao=date(y, m, 12),
            tag_ids=[tags_map["mercado"]],
        )

        # --- COMPRAS MENSAIS NOS CARTÕES DE CRÉDITO ---
        # A. Nubank Mastercard (fecha dia 5, vence dia 12 -> compra no dia 1 do mês cai na fatura do próprio mês)
        tx_srv.create_expense(
            descricao="Assinaturas Netflix + Spotify Duo + Prime",
            valor=79.70,
            data_vencimento=date(y, m, 1),
            data_evento=date(y, m, 1),
            profile_id=profile_id,
            id_cartao=card_nubank.id,
            id_categoria=c_lazer,
            id_subcategoria=s_streaming,
            tag_ids=[tags_map["lazer-familia"], tags_map["fixo-mensal"]],
        )
        tx_srv.create_expense(
            descricao="iFood & Pizzaria Fim de Semana",
            valor=168.50,
            data_vencimento=date(y, m, 2),
            data_evento=date(y, m, 2),
            profile_id=profile_id,
            id_cartao=card_nubank.id,
            id_categoria=c_alim,
            id_subcategoria=s_restaurante,
            tag_ids=[tags_map["lazer-familia"]],
        )
        tx_srv.create_expense(
            descricao="Supermercado Pão de Açúcar (Reposição Semanal)",
            valor=245.80,
            data_vencimento=date(y, m, 3),
            data_evento=date(y, m, 3),
            profile_id=profile_id,
            id_cartao=card_nubank.id,
            id_categoria=c_alim,
            id_subcategoria=s_mercado,
            tag_ids=[tags_map["essencial"], tags_map["mercado"]],
        )
        # B. Itaú Click Visa (fecha dia 18, vence dia 25 -> compra dia 10 cai na fatura do próprio mês)
        tx_srv.create_expense(
            descricao="Farmácia Droga Raia",
            valor=86.40,
            data_vencimento=date(y, m, 10),
            data_evento=date(y, m, 10),
            profile_id=profile_id,
            id_cartao=card_itau.id,
            id_categoria=c_saude,
            id_subcategoria=s_farmacia,
            tag_ids=[tags_map["saude"]],
        )
        tx_srv.create_expense(
            descricao="Uber Viagens Trabalho / Centro",
            valor=74.20,
            data_vencimento=date(y, m, 11),
            data_evento=date(y, m, 11),
            profile_id=profile_id,
            id_cartao=card_itau.id,
            id_categoria=c_transp,
            id_subcategoria=s_uber,
            tag_ids=[tags_map["trabalho"]],
        )

    # 7. Compras Parceladas nos Cartões (abrangendo meses passados, o mês atual e próximos meses!)
    # Parcelamento 1: Monitor + Upgrade SSD Trabalho (6x de R$ 220,00 = R$ 1.320,00) iniciado há 2 meses
    start_p1 = add_months(date(cur_y, cur_m, 2), -2)
    tx_srv.create_expense(
        descricao="Monitor Dell 27' + SSD NVMe Kabum",
        valor=1320.00,
        data_vencimento=start_p1,
        data_evento=start_p1,
        profile_id=profile_id,
        id_cartao=card_nubank.id,
        id_categoria=c_educ,
        id_subcategoria=s_cursos,
        recorrencia=REC_PARCELADA,
        num_parcelas=6,
        valor_por_parcela=False,
        obs="Equipamento para Home Office parcelado em 6x sem juros",
        tag_ids=[tags_map["parcelado"], tags_map["trabalho"]],
    )

    # Parcelamento 2: Seguro Auto Anual (5x de R$ 195,00) no Itaú Click Visa iniciado há 1 mês
    start_p2 = add_months(date(cur_y, cur_m, 9), -1)
    tx_srv.create_expense(
        descricao="Seguro Auto Porto Seguro (Parcelado 5x)",
        valor=195.00,
        data_vencimento=start_p2,
        data_evento=start_p2,
        profile_id=profile_id,
        id_cartao=card_itau.id,
        id_categoria=c_transp,
        id_subcategoria=s_seguro,
        recorrencia=REC_PARCELADA,
        num_parcelas=5,
        valor_por_parcela=True,
        obs="Renovação anual seguro veículo",
        tag_ids=[tags_map["parcelado"], tags_map["essencial"]],
    )

    # Parcelamento 3: Tênis de Corrida + Jaqueta (3x de R$ 140,00) no Nubank iniciado no mês atual
    tx_srv.create_expense(
        descricao="Tênis Corrida Olympikus + Agasalho Centauro",
        valor=420.00,
        data_vencimento=date(cur_y, cur_m, 3),
        data_evento=date(cur_y, cur_m, 3),
        profile_id=profile_id,
        id_cartao=card_nubank.id,
        id_categoria=c_vest,
        id_subcategoria=s_roupas,
        recorrencia=REC_PARCELADA,
        num_parcelas=3,
        valor_por_parcela=False,
        tag_ids=[tags_map["parcelado"]],
    )

    # 8. Paga as faturas dos 5 meses anteriores nos dois cartões e adiciona um adiantamento parcial no mês atual
    for offset in range(-5, 0):
        m_date = add_months(date(cur_y, cur_m, 1), offset)
        y, m = m_date.year, m_date.month
        card_srv.pay_invoice(
            card_nubank.id,
            y,
            m,
            id_conta=acc_nubank,
            data_pagamento=date(y, m, 12),
        )
        card_srv.pay_invoice(
            card_itau.id,
            y,
            m,
            id_conta=acc_itau,
            data_pagamento=date(y, m, 25),
        )

    # Registra um adiantamento parcial de R$ 150,00 na fatura atual do Nubank para demonstrar o recurso
    card_srv.add_invoice_advance(
        card_nubank.id,
        cur_y,
        cur_m,
        valor=150.00,
        id_conta=acc_nubank,
        data_pagamento=date(cur_y, cur_m, min(today.day, 10)),
        descricao="Adiantamento Parcial Fatura Nubank",
    )

    # 9. Cria Orçamentos Mensais realistas para uma renda de R$ 5.000/mês
    budget_srv.create_budget(
        meta=1680.00,
        id_categoria=c_moradia,
        perc_alerta=80.0,
        profile_id=profile_id,
    )
    budget_srv.create_budget(
        meta=1150.00,
        id_categoria=c_alim,
        perc_alerta=80.0,
        profile_id=profile_id,
    )
    budget_srv.create_budget(
        meta=650.00,
        id_categoria=c_transp,
        perc_alerta=80.0,
        profile_id=profile_id,
    )
    budget_srv.create_budget(
        meta=500.00,
        id_categoria=c_saude,
        perc_alerta=80.0,
        profile_id=profile_id,
    )
    budget_srv.create_budget(
        meta=320.00,
        id_categoria=c_lazer,
        perc_alerta=75.0,
        profile_id=profile_id,
    )
    budget_srv.create_budget(
        meta=3500.00,
        id_tag=tags_map["essencial"],
        perc_alerta=85.0,
        profile_id=profile_id,
    )

    # 10. Cria Objetivos Financeiros (Metas de Economia) com Aportes
    g_reserva = goal_srv.create_goal(
        descricao="Reserva de Emergência (6 Meses de Custo Fixo)",
        meta=18000.00,
        saldo_inicial=5500.00,
        data_expectativa=add_months(today, 14),
        motivacao="Segurança tranquila para a família em CDB 100% CDI / Poupança",
        color_hex="#1E88E5",
        profile_id=profile_id,
    )
    for m_off in range(-5, 1):
        dt_dep = add_months(date(cur_y, cur_m, 7), m_off)
        goal_srv.add_deposit(
            g_reserva.id,
            valor=500.00,
            data_deposito=dt_dep,
            obs=f"Aporte mensal programado ({dt_dep.strftime('%m/%Y')})",
        )

    g_viagem = goal_srv.create_goal(
        descricao="Viagem de Férias — Maceió / Porto de Galinhas",
        meta=4800.00,
        saldo_inicial=900.00,
        data_expectativa=add_months(today, 8),
        motivacao="Férias de 7 dias com passagens e hotel pagos à vista",
        color_hex="#00897B",
        profile_id=profile_id,
    )
    goal_srv.add_deposit(
        g_viagem.id,
        valor=450.00,
        data_deposito=add_months(today, -2),
        obs="Parte do serviço extra de TI",
    )
    goal_srv.add_deposit(
        g_viagem.id,
        valor=600.00,
        data_deposito=add_months(today, -1),
        obs="Economia de restituição IRPF",
    )

    g_notebook = goal_srv.create_goal(
        descricao="Fundo para Troca de Carro / Entrada Veículo",
        meta=20000.00,
        saldo_inicial=3200.00,
        data_expectativa=add_months(today, 24),
        motivacao="Trocar o carro sem precisar financiar com juros altos",
        color_hex="#8E24AA",
        profile_id=profile_id,
    )
    goal_srv.add_deposit(
        g_notebook.id,
        valor=800.00,
        data_deposito=add_months(today, -1),
        obs="Aporte extra semestral",
    )

    # 11. Empréstimos (1 A Receber e 1 A Pagar) com amortizações
    loan_irmao = analytics_srv.create_loan(
        descricao="Empréstimo p/ Conserto da Moto do Pedro (Irmão)",
        pessoa="Pedro Brasileiro (Irmão)",
        principal=1200.00,
        concedido=True,
        data_inicio=add_months(today, -2),
        id_conta=acc_nubank,
        observacao="Combinado pagar em 3x de R$ 400",
        profile_id=profile_id,
    )
    analytics_srv.register_loan_payment(
        loan_irmao.id,
        valor=400.00,
        data_pag=add_months(today, -1),
        profile_id=profile_id,
    )

    loan_curso = analytics_srv.create_loan(
        descricao="Parcelamento Pós-Graduação / Certificação Cloud",
        pessoa="Faculdade / Cooperativa",
        principal=1800.00,
        concedido=False,
        data_inicio=add_months(today, -3),
        id_conta=acc_itau,
        observacao="Investimento profissional sem juros",
        profile_id=profile_id,
    )
    analytics_srv.register_loan_payment(
        loan_curso.id,
        valor=600.00,
        data_pag=add_months(today, -1),
        profile_id=profile_id,
    )

    # 12. Notas & Lembretes Financeiros + Modelos CSV
    analytics_srv.create_note(
        titulo="Regra 70/20/10 do Salário de R$ 5.000",
        conteudo="Meta mensal: R$ 3.500 custos essenciais (70%), R$ 800 lazer/variáveis (16%) e R$ 700 investimentos/objetivos (14%).",
        profile_id=profile_id,
    )
    analytics_srv.create_note(
        titulo="Destino do 13º Salário (Novembro/Dezembro)",
        conteudo="Separar R$ 1.800 para IPVA/Licenciamento à vista com desconto e R$ 1.500 para a Reserva de Emergência.",
        profile_id=profile_id,
    )
    analytics_srv.create_note(
        titulo="Fechamento dos Cartões de Crédito",
        conteudo="Nubank fecha dia 05 (melhor dia de compra: 06). Itaú Click fecha dia 18 (melhor dia de compra: 19).",
        profile_id=profile_id,
    )

    io_orch.save_csv_mapping(
        CSVColumnMapping(
            descricao_modelo="Extrato Nubank CSV (;)",
            separador=";",
            possui_cabecalho=True,
            formato_data="dd/MM/yyyy",
            valor_negativo_despesas=True,
            id_conta=acc_nubank,
            col_data=0,
            col_descricao=1,
            col_valor=2,
            col_categoria=3,
        )
    )
    io_orch.save_csv_mapping(
        CSVColumnMapping(
            descricao_modelo="Extrato Itaú CSV (;)",
            separador=";",
            possui_cabecalho=True,
            formato_data="dd/MM/yyyy",
            valor_negativo_despesas=True,
            id_conta=acc_itau,
            col_data=0,
            col_descricao=1,
            col_valor=2,
        )
    )

    db.close()
    return target_db_path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # 1. Gera a base modelo dedicada e atualiza a base ativa do projeto
    demo_path = DEFAULT_USER_DATA_DIR / "joao_brasileiro_5000_modelo.sqlite"
    build_joao_brasileiro_database(demo_path)
    print(f"[OK] Base modelo gerada em: {demo_path}")

    # 2. Propaga para todos os destinos ativos (projeto local, AppData instalado e executável portátil)
    targets = [
        DEFAULT_DB_FILE,
        PROJECT_ROOT / "dist" / "MinhasFinancas" / "dados_usuario" / "minhas_financas.sqlite",
        Path.home() / "AppData" / "Local" / "MinhasFinancas" / "dados_usuario" / "minhas_financas.sqlite",
    ]
    for dst in targets:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(demo_path, dst)
            print(f"[OK] Base ativa atualizada em: {dst}")
        except OSError as exc:
            print(f"[AVISO] Não foi possível atualizar {dst}: {exc}")


if __name__ == "__main__":
    main()
