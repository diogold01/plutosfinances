SELECT
COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta) as receitas_id_conta,
receitas.id as idreceita,
receitas.id_origem as id_ori,
receitas.id_profile,
receitas.id_provider,
receitas.descricao as descr,
COALESCE(receitas.regra_efetivacao_parcial_open_finance, 'N') as regra_efetivacao_parcial_open_finance,
receitas.valor_parcial_open_finance as valor_parcial_open_finance,
COALESCE(receitas.reconhecer_valor_diferente, 'N') as reconhecer_valor_diferente,
COALESCE(receitas.reconhecer_data_diferente, 'N') as reconhecer_data_diferente,
COALESCE(receitas.lembrete_vencimento, 'N') as lembrete_vencimento,
CASE WHEN receitas.recorrencia = 'M' THEN
  COALESCE(
    receitas_fixas.id_open_finance_transaction,
    CASE WHEN NOT EXISTS (
      SELECT 1
      FROM receitas_fixas receitas_fixas_id_of
      WHERE receitas_fixas_id_of.id_receita = receitas.id
        AND COALESCE(receitas_fixas_id_of.id_open_finance_transaction, '') != ''
    ) THEN receitas.id_open_finance_transaction END
  )
ELSE receitas.id_open_finance_transaction END as id_open_finance_transaction,
receitas.descricao_open_finance as descricao_open_finance,
receitas.category_open_finance as category_open_finance,
receitas.possivel_transferencia_of as possivel_transferencia_of,
receitas.possivel_fixa_mensal as possivel_fixa_mensal,
COALESCE(receitas.buscar_similares, 'S') as buscar_similares,
COALESCE(receitas.sugerir_descricao, 'S') as sugerir_descricao,
COALESCE(receitas.data_cadastro, receitas.data) as datacadastro,
datetime(COALESCE(receitas_fixas.data, receitas.data)) as data_ref,
{param_data_referencia} as dt,
COALESCE(receitas.somar_total,'S') as somar,
COALESCE(receitas_fixas.obs, receitas_fixas_valor.obs_futura, receitas.obs, '') as obs,
COALESCE(receitas.ignore_orc,'N') as ignore_orc,
COALESCE(receitas.recorrencia,'N') as recorrencia,
COALESCE(receitas.num_parcela, 1) as num_parcela,
COALESCE(receitas.num_parcelas, 0) as num_parcelas,
(case when receitas.recorrencia != 'M' then receitas.efetivado
else COALESCE(receitas_fixas.efetivado,'N') end) as efetivado,
COALESCE(receitas_fixas_valor.valor, receitas.valor) as val,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
COALESCE(contas.currency, '') as conta_currency,
contas.descricao as conta_desc,
contas.id_item                  as conta_id_item,
contas.id_open_finance_account  as conta_id_open_finance_account,
coalesce(contas.image_url, ofi.image_url) as conta_image_url,
COALESCE(contas.image_id, 0) as conta_image_id,

contas_cat.descricao as conta_cat_descricao,
COALESCE(contas_cat.cor, 0) as conta_cat_cor,
contas_cat.id as conta_id_categoria,

COALESCE(contas.somar_total,'S') as conta_somar,

COALESCE(receitas.id_categoria, '-1') as cat_id,
receitas_cat.descricao as cat_nome,
receitas_cat.cor as cat_cor,
receitas_cat.icon_id as cat_icon,

receitas_subcat.id as subcat_id,
receitas_subcat.nome as subcat_nome,
receitas_subcat.cor as subcat_cor,
receitas_subcat.icon_id as subcat_icon

from receitas left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join receitas_cat on receitas_cat.id = receitas.id_categoria
left join receitas_subcat on receitas.id_subcategoria = receitas_subcat.id
left join contas on contas.id = COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta)
left join open_finance_items as ofi on ofi.id = contas.id_item
left join contas_cat on contas_cat.id = contas.id_categoria
{params}
