SELECT
despesas.id as idgas,
despesas.id_profile as despesas_id_profile,
despesas.data_cadastro as dtcad,
COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta) as despesas_id_conta,
despesas.descricao as descr,
COALESCE(despesas_fixas.excluido_mes,'N') as excluido,
COALESCE(considerar_estatistica, 'S') as cons_est,
COALESCE(despesas.economia_mensal, 'S') as economia_mensal,
round(SUM(catmap.valor), 2) as val,
coalesce(adiantamento_fatura, 'N') as adiantamento_fatura,
COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1) cotacao,

despesas_fixas_valor.data as data_valor,
COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as card_id,
COALESCE(despesas_fixas.juros, despesas.juros, 0) as juros,
COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) as dt_pg,
despesas.recorrencia as rec,

{param_data_referencia} as dt,

 despesas.data as dtoriginal,
(case when despesas.recorrencia = 'F' and despesas_fixas.status is null
		then 'pd'
      when  despesas.recorrencia = 'F' and despesas_fixas.status is not null
		then despesas_fixas.status
	  when despesas.recorrencia != 'F'
		then despesas.status
	   end ) as st,
despesas.id_origem as idori,
despesas.num_parcela as numpar,
despesas.num_parcelas as numpars,
despesas.data_exclusao as data_exc,
COALESCE(despesas.somar_total,'S') as somar,
COALESCE(despesas_fixas.contabilizar, despesas.contabilizar) as contabilizar,
COALESCE(despesas.regra_efetivacao_parcial_open_finance, 'N') as regra_efetivacao_parcial_open_finance,
despesas.valor_parcial_open_finance as valor_parcial_open_finance,
COALESCE(despesas.reconhecer_valor_diferente, 'N') as reconhecer_valor_diferente,
COALESCE(despesas.reconhecer_data_diferente, 'N') as reconhecer_data_diferente,
COALESCE(despesas.lembrete_vencimento, 'N') as lembrete_vencimento,

/**{columns}**/

contas.id_item                  as conta_id_item,
contas.id_open_finance_account  as conta_id_open_finance_account,
coalesce(contas.image_url, ofi.image_url) as conta_image_url,
COALESCE(contas.image_id, 0) as conta_image_id,
COALESCE(contas.somar_total,'S') as conta_somar,
COALESCE(contas.currency, '') as conta_currency

FROM despesas
inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
   AND (despesas.recorrencia != 'F' OR
       (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
        AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(COALESCE(obs, '')) = LOWER(COALESCE(catmap.obs,''))
        AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
        AND catmap.excluido != 'S'))
left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
and (date(COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao), 'start of month') = date(:datainicio, 'start of month') OR date(despesas_fixas.data, 'start of month') = date(:datainicio, 'start of month'))
left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
    and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join contas on contas.id = despesas_id_conta
left join open_finance_items as ofi on ofi.id = contas.id_item
WHERE
despesas_id_profile = :id_profile
AND (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
AND (despesas.data_exclusao IS NULL OR date(strftime('%Y-%m-01',:datainicio)) <=
date(strftime('%Y-%m-01', despesas.data_exclusao)))
AND (:considerar_contas_arquivadas = 'S' OR contas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', contas.data_exclusao)))

{PARAMS}
GROUP BY catmap.id_despesa
ORDER BY card_id, st asc
