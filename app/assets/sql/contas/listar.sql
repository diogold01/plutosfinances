SELECT
contas.id as conta_id,
contas.descricao as conta_desc,
coalesce(contas.currency, profiles.currency) as currency,
contas.id_conta_pai as id_conta_pai,
ifnull(contas.conta_pai, 'N') as conta_pai,

-- OPEN FINANCE
id_item,
id_open_finance_account,
subtype,
number,
routing_number,
last_successful_sync_at,
coalesce(ofi.name_connector, '') as nome_instituicao,
-- A imagem local definida no item Open Finance deve substituir a URL remota
-- da instituição também nas contas vinculadas.
case when ofi.image_id is not null and ofi.image_id >= 0
then null
else coalesce(contas.image_url, ofi.image_url) end as image_url,
coalesce(ofi.status, '')        as status_conexao,
coalesce(ofi.primary_color, '') as primary_color,

(case WHEN contas.currency = coalesce(cotacoes.base, last_cotacao.base)
THEN  coalesce(cotacoes.rate, last_cotacao.rate, 1)
WHEN  contas.currency = coalesce(cotacoes.symbol, last_cotacao.symbol)
THEN  (1 / coalesce(cotacoes.rate, last_cotacao.rate, 1))
ELSE 1 END) cotacao,

contas.dados_adicionais as dados,
contas.fav as favorita_count,
contas.id_profile as id_profile,
case when ofi.image_id is not null
then ofi.image_id
else ifnull(contas.image_id, 0) end as image_id,
ifnull(contas.liquidacao, 'N') as liquidacao,
ifnull(contas.exibir_saldo, 'N') as exibir_saldo,
ifnull(contas.exibir_resumo, 'N') as exibir_resumo,
ifnull(contas.investimento, 'N') as investimento,
ifnull(contas.somar_todas_contas_agrupadas, 'N') as somar_todas_contas_agrupadas,
ifnull(contas.padrao_importacao, 'S') as padrao_importacao,
ifnull(contas.pendente_primeira_reconciliacao_saldo_tempo_real, 'N') as pendente_primeira_reconciliacao_saldo_tempo_real,
ifnull(contas.sequence, 0) as sequence,
contas.data_cadastro as conta_data_cad,
contas.somar_total as conta_somar,
contas.padrao as conta_padrao,
contas.data_exclusao as conta_data_ex,

contas.id_categoria as conta_id_categoria,
contas_cat.descricao as categoria_desc,
contas_cat.padrao as categoria_padrao,
ifnull(contas_cat.not_resume, 'N') as categoria_not_resume,
ifnull(contas_cat.not_balance, 'N') as categoria_not_balance,
ifnull(contas_cat.icon_id, 252) as categoria_icon_id,
ifnull(contas_cat.cor, 0) as categoria_cor,

ifnull(contas_saldo.mes, strftime('%m', :datainicio)) as saldo_mes,
ifnull(contas_saldo.ano, strftime('%Y', :datainicio)) as saldo_ano,
ifnull(contas_saldo.si, 0) as saldo_ini,
ifnull(contas_saldo.si_custom, 'N') as saldo_ini_custom,
ifnull(receitas.efetivadas,0) as dep_efet,
ifnull(receitas.pendentes,0) as dep_pend,
ifnull(despesas.pago,0) as gast_pg,
ifnull(despesas.pendente, 0) as gast_pend,
ifnull(despesas.estornos_efet, 0) as estornos_efet,
ifnull(despesas.estornos_pend, 0) as estornos_pend,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas.id THEN 0 ELSE transfers.transf_efet END)),0) as transf_cred_efet,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas.id THEN 0 ELSE transfers.transf_pend END)),0) as transf_cred_pend,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas.id THEN transfers.transf_efet ELSE 0 END)),0) as transf_deb_efet,
ifnull(SUM((CASE WHEN transfers.id_conta_origem = contas.id THEN transfers.transf_pend ELSE 0 END)),0) as transf_deb_pend,
(case when contas_saldo.cheque_especial is null
 then ifnull(contas.cheque_especial, 0)
 else contas_saldo.cheque_especial end) as cheque_especial,
ifnull(contas_saldo.obs, '')   as observ

FROM contas

/* PROFILE */
inner join profiles on contas.id_profile = profiles.id

/* OPN FINANCE ITEMS */
left join open_finance_items as ofi on ofi.id = contas.id_item

/* COTACAO DATA REF */
left join cotacoes ON date(cotacoes.date, 'start of month') = date(:datainicio, 'start of month')
AND ((cotacoes.base = profiles.currency AND cotacoes.symbol = contas.currency)
OR (cotacoes.base = contas.currency AND cotacoes.symbol = profiles.currency))

/* ULTIMA COTACAO */
left join cotacoes as last_cotacao ON last_cotacao.last = 'S'
AND ((last_cotacao.base = profiles.currency AND last_cotacao.symbol = contas.currency)
OR (last_cotacao.base = contas.currency AND last_cotacao.symbol = profiles.currency))


/* CONTA SALDO */
left join contas_saldo on contas_saldo.id_conta = contas.id
                                and contas_saldo.mes = strftime('%m', :datainicio)
                                and contas_saldo.ano = strftime('%Y', :datainicio)

/* CATEGORIA */
left join contas_cat on contas_cat.id = contas.id_categoria


/* DESPESAS */
left join (SELECT
           id_conta,
           SUM((case when status = 'pd' OR val < 0 then 0 else round(val + juros,2) end)) as pago,
           SUM((case when status = 'pg' OR val < 0 then 0 else round(val + juros, 2) end)) as pendente,
           SUM((case when status = 'pd' AND val < 0 then round(val + juros, 2) else 0 end)) as estornos_pend,
           SUM((case when status = 'pg' AND val < 0 then round(val + juros, 2) else 0 end)) as estornos_efet
           FROM (SELECT
           despesas.id,
           ifnull(despesas_fixas_valor.id_conta, despesas.id_conta) as id_conta,
           (case when despesas.recorrencia != 'F' then despesas.status
           else ifnull(despesas_fixas.status, 'pd') end ) as status,
           round(SUM(catmap.valor), 2) as val,
           COALESCE(despesas_fixas.juros, despesas.juros, 0) as juros,
           (CASE WHEN COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito, '-1') IN ('', '-1') AND
           COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao,  '') != '' THEN
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
           GROUP BY id_conta) as despesas ON despesas.id_conta = contas.id

/* RECEITAS */
LEFT JOIN (SELECT
         COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta) as id_conta,
         SUM(CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                       	  else ifnull(receitas_fixas.efetivado,'N') end) = 'N' THEN 0 ELSE
                       	  round(COALESCE(receitas_fixas_valor.valor, receitas.valor), 2) END) as efetivadas,

        SUM(CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                       	  else ifnull(receitas_fixas.efetivado,'N') end) = 'S' THEN 0 ELSE
                       	  round(COALESCE(receitas_fixas_valor.valor, receitas.valor), 2) END) as pendentes,

         (CASE WHEN COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao, '') != '' THEN
         COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao) ELSE
         (CASE receitas.recorrencia WHEN 'M' THEN
         datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
         (CASE WHEN  substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
         THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
         ELSE   substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
         END))
         ELSE receitas.data  END) END) as dt

         from receitas
         left join receitas_fixas on receitas.id = receitas_fixas.id_receita
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
         GROUP BY ifnull(receitas_fixas_valor.id_conta, receitas.id_conta)) as receitas ON receitas.id_conta = contas.id


/* TRANSFERENCIAS */
LEFT JOIN (SELECT
    ifnull(transf_fixa_valor.id_conta_origem, transf.id_conta_origem) as id_conta_origem,
    ifnull(transf_fixa_valor.id_conta_destino, transf.id_conta_destino) as id_conta_destino,

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

    from transferencias as transf
    left join transferencias_fixas on transf.id = transferencias_fixas.id_transferencia
               and date(ifnull(transferencias_fixas.data, transf.data), 'start of month') = date(:datainicio, 'start of month')
  left join transferencias_fixas as transf_fixa_valor on transf_fixa_valor.id_transferencia = transf.id
  and date(transf_fixa_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month') from transferencias_fixas where transferencias_fixas.id_transferencia = transf.id
                                   and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
    where
    ifnull(transferencias_fixas.excluido_mes,'N') = 'N'
    AND (transf.recorrencia != 'M' OR date(transf.data, 'start of month') <= date(dt, 'start of month'))
    AND date(dt) between date(strftime('%Y-%m-01', :datainicio))
    AND date(:datainicio,'start of month','+1 month','-1 day')
    AND (transf.data_exclusao IS NULL OR
    date(strftime('%Y-%m-01',:datainicio)) <=
    date(strftime('%Y-%m-01', transf.data_exclusao)))) as transfers ON (transfers.id_conta_origem = contas.id OR transfers.id_conta_destino = contas.id)


WHERE
((coalesce(:APENAS_ARQUIVADAS, 'N') = 'S' AND contas.data_exclusao IS NOT NULL) OR
 (coalesce(:APENAS_ARQUIVADAS, 'N') = 'N' AND (contas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', contas.data_exclusao)))))
/**{params}**/
GROUP BY contas.id
/**{order_by}**/
