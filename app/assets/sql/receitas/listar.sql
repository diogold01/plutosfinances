select
receitas.id as idreceita,
COALESCE(receitas.id_origem,receitas.id) as idori,
receitas.id_profile as id_profile,
receitas.origem_ajuste as origem_ajuste,
receitas.id_provider as id_provider,
COALESCE(receitas.num_parcela,1) as numpar,
COALESCE(receitas.num_parcelas,0) as numpars,
COALESCE(receitas.recorrencia,'N') as rec,
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
receitas.data_registro_of as dt_registro_of,
receitas.ultima_modificacao as ultima_modificacao,
receitas.possivel_fixa_mensal as possivel_fixa_mensal,
COALESCE(receitas.buscar_similares, 'S') as buscar_similares,
COALESCE(receitas.sugerir_descricao, 'S') as sugerir_descricao,
COALESCE(receitas.regra_efetivacao_parcial_open_finance, 'N') as regra_efetivacao_parcial_open_finance,
receitas.valor_parcial_open_finance as valor_parcial_open_finance,
COALESCE(receitas.reconhecer_valor_diferente, 'N') as reconhecer_valor_diferente,
COALESCE(receitas.reconhecer_data_diferente, 'N') as reconhecer_data_diferente,
COALESCE(receitas.lembrete_vencimento, 'N') as lembrete_vencimento,
COALESCE(receitas_fixas.attach_id, receitas.attach_id) as attach_id,
COALESCE(receitas_fixas.attach_path, receitas.attach_path) as attach_path,
COALESCE(receitas_fixas.attach_size, receitas.attach_size, 0) as attach_size,
COALESCE(receitas.economia_mensal,'S') as economia_mensal,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
round(COALESCE(receitas_fixas_valor.valor, receitas.valor),2) as val,
receitas_fixas_valor.data as data_valor,
COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao) as data_rec,

COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta) as receitas_id_conta,
receitas.descricao as descr,
COALESCE(receitas.local, receitas.descricao_open_finance, receitas.descricao) as local,
receitas.id_orig_parcial as id_orig_parcial,
receitas.dt_orig_parcial as dt_orig_parcial,
COALESCE(receitas_fixas.obs, receitas_fixas_valor.obs_futura, receitas.obs, '') as obs,
COALESCE(receitas.ef_auto, 'N') as ef_auto,
COALESCE(receitas.ignore_orc,'N') as ignore_orc,
COALESCE(receitas.ef_inicio_dia, 'N') as ef_inicio_dia,
receitas.data_exclusao  as dt_exclusao,
COALESCE(receitas.intervalo, 0)  as intervalo,

contas.descricao as conta_desc,
contas.id_item                  as conta_id_item,
contas.id_open_finance_account  as conta_id_open_finance_account,
coalesce(contas.image_url, ofi.image_url) as conta_image_url,
COALESCE(contas.image_id, 0) as conta_image_id,
COALESCE(contas.somar_total,'S') as conta_somar,
COALESCE(contas.currency, '') as conta_currency,

contas_cat.id as conta_id_categoria,
contas_cat.descricao as conta_cat_descricao,
COALESCE(contas_cat.cor, 0) as conta_cat_cor,
COALESCE(contas_cat.icon_id, 252) as conta_cat_icon_id,

COALESCE(receitas.somar_total,'S') as somar,
COALESCE(receitas.considerar_estatistica, 'S') as considerar_estatistica,
COALESCE(receitas.id_categoria, '-1') as id_categoria,
receitas_cat.descricao as cat_nome,
receitas_cat.cor as cor_cat,
receitas_cat.icon_id as cat_icon_id,

receitas_subcat.id as subcat_id,
receitas_subcat.nome as subcat_nome,
receitas_subcat.cor as subcat_cor,
receitas_subcat.icon_id as subcat_icon_id,

/**{columns}**/

COALESCE(receitas_fixas.efetivado, receitas.efetivado, 'N')  as efetivado,
COALESCE(receitas_fixas.excluido_mes,'N') as excluido,

(CASE receitas.recorrencia WHEN 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d', date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
END))
ELSE receitas.data  END) as data_venc,

{param_data_referencia} as dt,

COALESCE(receitas.data_cadastro, receitas.data)  as dtcad,
receitas.data as dtori
from receitas
/**{INNER_JOIN}**/
left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')

left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month')
                                 from receitas_fixas where id_receita = receitas.id
                                 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join receitas_cat on receitas_cat.id = receitas.id_categoria
left join receitas_subcat on receitas.id_subcategoria = receitas_subcat.id
left join contas on contas.id = receitas_id_conta
left join open_finance_items as ofi on ofi.id = contas.id_item
left join contas_cat on contas_cat.id = contas.id_categoria
