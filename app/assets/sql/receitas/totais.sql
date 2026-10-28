select
receitas.id as idreceita,
receitas.id_profile,
COALESCE(receitas.recorrencia,'N')     as rec,
COALESCE(receitas.economia_mensal,'S') as economia_mensal,
round(COALESCE(receitas_fixas_valor.valor, receitas.valor),2) as val,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,

receitas_fixas_valor.data as data_valor,
COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao) as data_rec,

COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta) as receitas_id_conta,
receitas.descricao as descr,
COALESCE(receitas.local, receitas.descricao) as local,
receitas.id_orig_parcial as id_orig_parcial,
receitas.dt_orig_parcial as dt_orig_parcial,
COALESCE(receitas_fixas.obs, receitas_fixas_valor.obs_futura, receitas.obs, '') as obs,
COALESCE(receitas.ef_auto, 'S') as ef_auto,
receitas.data_exclusao  as dt_exclusao,
COALESCE(receitas.intervalo, 0)  as intervalo,

contas.id_item                  as conta_id_item,
contas.id_open_finance_account  as conta_id_open_finance_account,
coalesce(contas.image_url, ofi.image_url) as conta_image_url,
COALESCE(contas.image_id, 0) as conta_image_id,
COALESCE(contas.somar_total,'S') as conta_somar,
COALESCE(receitas.somar_total,'S') as somar,
COALESCE(receitas.considerar_estatistica, 'S') as considerar_estatistica,

(case when receitas.recorrencia != 'M' then receitas.efetivado
	  else COALESCE(receitas_fixas.efetivado,'N') end) as efetivado,
COALESCE(receitas_fixas.excluido_mes,'N') as excluido,
COALESCE(receitas.regra_efetivacao_parcial_open_finance, 'N') as regra_efetivacao_parcial_open_finance,
receitas.valor_parcial_open_finance as valor_parcial_open_finance,
COALESCE(receitas.reconhecer_valor_diferente, 'N') as reconhecer_valor_diferente,
COALESCE(receitas.reconhecer_data_diferente, 'N') as reconhecer_data_diferente,
COALESCE(receitas.lembrete_vencimento, 'N') as lembrete_vencimento,

{param_data_referencia} as dt,

/**{columns}**/

COALESCE(receitas.data_cadastro, receitas.data)  as dtcad

from receitas
left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')

left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join contas on contas.id = COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta)
left join open_finance_items as ofi on ofi.id = contas.id_item

/**{INNER_JOIN}**/

where (receitas.recorrencia != 'M' OR  date(receitas.data, 'start of month') <= date(dt, 'start of month'))
 AND (receitas.data_exclusao IS NULL OR
date(strftime('%Y-%m-01',:datainicio)) <=  date(strftime('%Y-%m-01', receitas.data_exclusao)))

AND (:considerar_contas_arquivadas = 'S' OR contas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', contas.data_exclusao)))
