SELECT
contas_saldo.id_conta,
contas_saldo.mes,
contas_saldo.ano,
contas_saldo.si,
ifnull(contas_saldo.si_custom, 'N') as si_custom,
ifnull(receitas.efetivadas, 0) as dp_ef,
ifnull(receitas.pendentes, 0) as dp_pd,
ifnull(despesas.pago, 0) as gas_pg,
ifnull(despesas.pendente, 0) as gas_pd,
ifnull(despesas.estornos_efet, 0) as estornos_efet,
ifnull(despesas.estornos_pend, 0) as estornos_pend,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas_saldo.id_conta THEN 0 ELSE transfers.transf_efet END)),0) as tc_ef,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas_saldo.id_conta THEN 0 ELSE transfers.transf_pend END)),0) as tc_pd,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas_saldo.id_conta THEN transfers.transf_efet ELSE 0 END)),0) as td_ef,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas_saldo.id_conta THEN transfers.transf_pend ELSE 0 END)),0) as td_pd,
ifnull(contas_saldo.cheque_especial,0)   as cheque_especial,
contas_saldo.obs
FROM contas_saldo

/* DESPESAS */
LEFT JOIN (SELECT
                      id_conta,
                      SUM((case when status = 'pd' OR val < 0 then 0 else (val + juros) end)) as pago,
                      SUM((case when status = 'pg' OR val < 0 then 0 else (val + juros) end)) as pendente,
                      SUM((case when status = 'pd' AND val < 0 then (val + juros) else 0 end)) as estornos_pend,
                      SUM((case when status = 'pg' AND val < 0 then (val + juros) else 0 end)) as estornos_efet
                      FROM (SELECT
                      despesas.id,
                      ifnull(despesas_fixas_valor.id_conta, despesas.id_conta) as id_conta,
                      (case when despesas.recorrencia != 'F' then despesas.status
                      else ifnull(despesas_fixas.status, 'pd') end ) as status,
                      SUM(catmap.valor) as val,
                      COALESCE(despesas_fixas.juros, despesas.juros, 0) as juros,
                      (CASE WHEN COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito, '-1') IN ('', '-1') AND
                      COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao, '') != '' THEN
                      COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) ELSE
                      (CASE despesas.recorrencia WHEN 'F' THEN
                      datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
                      (CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                       THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                       ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
                       END))
                       ELSE despesas.data END) END) as dt

                      FROM despesas
                      inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
                          AND (despesas.recorrencia != 'F' OR
                                 (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                                  AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
                                  AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
                                  AND catmap.excluido != 'S'))
                      left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(ifnull(despesas_fixas.data, despesas.data), 'start of month') = date(:datainicio, 'start of month')
                      left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
                             and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
                            and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
                      WHERE
                      (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
                      and ifnull(despesas_fixas.excluido_mes,'N') = 'N'
                      AND (despesas.data_exclusao IS NULL OR
                        date(strftime('%Y-%m-01',:datainicio)) <=
                        date(strftime('%Y-%m-01', despesas.data_exclusao)))
                      AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
                      and date(:datainicio,'start of month','+1 month','-1 day')
                      GROUP BY catmap.id_despesa)
                      GROUP BY id_conta) as despesas ON despesas.id_conta = contas_saldo.id_conta


/* RECEITAS */
LEFT JOIN (SELECT
  ifnull(receitas_fixas_valor.id_conta, receitas.id_conta) as id_conta,

  SUM(CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                	  else ifnull(receitas_fixas.efetivado,'N') end) = 'N' THEN 0 ELSE ifnull(receitas_fixas_valor.valor, receitas.valor) END) as efetivadas,

  SUM(CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                	  else ifnull(receitas_fixas.efetivado,'N') end) = 'S' THEN 0 ELSE ifnull(receitas_fixas_valor.valor, receitas.valor) END) as pendentes,

(CASE WHEN COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao, '') != '' THEN
         COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao) ELSE
         (CASE receitas.recorrencia WHEN 'M' THEN
         datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
         (CASE WHEN  substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
         THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
         ELSE   substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
         END))
         ELSE receitas.data  END) END) as dt

  from receitas left join receitas_fixas on receitas.id = receitas_fixas.id_receita
                                       and date(ifnull(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
  where
  ifnull(receitas_fixas.excluido_mes,'N') = 'N'
  AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
  AND date(dt) between date(strftime('%Y-%m-01', :datainicio))
  AND date(:datainicio,'start of month','+1 month','-1 day')
  AND (receitas.data_exclusao IS NULL OR
  date(strftime('%Y-%m-01',:datainicio)) <=
  date(strftime('%Y-%m-01', receitas.data_exclusao)))
  GROUP BY ifnull(receitas_fixas_valor.id_conta, receitas.id_conta)) as receitas ON receitas.id_conta = contas_saldo.id_conta

/* TRANSFERENCIAS */
LEFT JOIN (SELECT
    ifnull(transferencias_fixas_valor.id_conta_origem, transf.id_conta_origem) as id_conta_origem,
    ifnull(transferencias_fixas_valor.id_conta_destino, transf.id_conta_destino) as id_conta_destino,

    round((CASE WHEN (CASE WHEN (ifnull(transf.recorrencia,'N') = 'N' OR transf.recorrencia = 'P') THEN transf.contabilizada
     WHEN transf.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
     THEN 'N'
     ELSE transferencias_fixas.contabilizada END) = 'N'
     THEN 0
     WHEN transf.id_profile = :id_profile
     THEN ifnull(transf_fixa_valor.valor, transf.valor)
     ELSE ifnull(transf_fixa_valor.valor, transf.valor) * COALESCE(transf_fixa_valor.cotacao, transf.cotacao, 1)
     END), 2) as transf_efet,

    round((CASE WHEN (CASE WHEN (ifnull(transf.recorrencia,'N') = 'N' OR transf.recorrencia = 'P') THEN transf.contabilizada
     WHEN transf.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
     THEN 'N'
     ELSE transferencias_fixas.contabilizada END) = 'S'
     THEN 0
     WHEN transf.id_profile = :id_profile
     THEN ifnull(transf_fixa_valor.valor, transf.valor)
     ELSE ifnull(transf_fixa_valor.valor, transf.valor) * COALESCE(transf_fixa_valor.cotacao, transf.cotacao, 1)
     END), 2) as transf_pend,

     (CASE WHEN COALESCE(transferencias_fixas.data_efetivacao, transf.data_efetivacao, '') != '' THEN
     COALESCE(transferencias_fixas.data_efetivacao, transf.data_efetivacao) ELSE
     (CASE transf.recorrencia WHEN 'M' THEN
     datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
     (CASE WHEN  substr('0'|| ifnull(transf_fixa_valor.dia_venc, strftime('%d', transf.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
     THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
     ELSE   substr('0'|| ifnull(transf_fixa_valor.dia_venc, strftime('%d', transf.data)), -2, 2)
     END))
     ELSE transf.data  END) END) as dt

    from transferencias as transf left join transferencias_fixas on transf.id = transferencias_fixas.id_transferencia
                                         and date(ifnull(transferencias_fixas.data, transf.data), 'start of month') = date(:datainicio, 'start of month')
  left join transferencias_fixas as transferencias_fixas_valor on transferencias_fixas_valor.id_transferencia = transf.id
  and date(transferencias_fixas_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month') from transferencias_fixas where transferencias_fixas.id_transferencia = transf.id
                                   and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
    where
    ifnull(transferencias_fixas.excluido_mes,'N') = 'N'
    AND (transf.recorrencia != 'M' OR date(transf.data, 'start of month') <= date(dt, 'start of month'))
    AND date(dt) between date(strftime('%Y-%m-01', :datainicio))
    AND date(:datainicio,'start of month','+1 month','-1 day')
    AND (transf.data_exclusao IS NULL OR
    date(strftime('%Y-%m-01',:datainicio)) <=
    date(strftime('%Y-%m-01', transf.data_exclusao)))) as transfers ON (transfers.id_conta_origem = contas_saldo.id_conta OR transfers.id_conta_destino =   contas_saldo.id_conta)

WHERE
contas_saldo.id_conta = :id_conta
and mes = :mes
and ano = :ano
GROUP BY contas_saldo.id_conta