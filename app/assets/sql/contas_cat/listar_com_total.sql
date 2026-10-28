SELECT
contas_cat.id as id,
contas_cat.descricao as descricao,
contas_cat.id_profile,
contas_cat.padrao as padrao,
ifnull(contas_cat.not_resume, 'N') as not_resume,
ifnull(contas_cat.not_balance, 'N') as not_balance,
ifnull(contas_cat.not_dash, 'N') as not_dash,
ifnull(contas_cat.icon_id, 252) as icon_id,
ifnull(contas_cat.cor, 0) as cor,

(

ifnull((CASE WHEN date(strftime('%Y-%m-01',:datainicio)) > date(strftime('%Y-%m-01','now')) THEN

(SUM(
(ifnull(contas_saldo.si, 0)
+ ifnull(receitas.efetivadas,0)
+ ifnull(receitas.pendentes,0)
+ ifnull(transfers_cred.transf_efet, 0)
+ ifnull(transfers_cred.transf_pend, 0)
- ifnull(despesas.estornos_efet, 0)
- ifnull(despesas.estornos_pend, 0)
- ifnull(transfers_deb.transf_efet, 0)
- ifnull(transfers_deb.transf_pend, 0)
- ifnull(despesas.pago,0)
- ifnull(despesas.pendente, 0)) * contas.cotacao))

ELSE

(SUM(
(ifnull(contas_saldo.si, 0)
+ ifnull(receitas.efetivadas,0)
+ ifnull(transfers_cred.transf_efet, 0)
- ifnull(despesas.estornos_efet, 0)
- ifnull(transfers_deb.transf_efet, 0)
- ifnull(despesas.pago,0)) * contas.cotacao))

END),0)

) as total,
COUNT(contas.id) as registros

FROM contas_cat

/* CONTAS */
LEFT JOIN (
SELECT *,
(CASE WHEN contas.currency = coalesce(cotacoes.base, last_cotacao.base)
THEN  coalesce(cotacoes.rate, last_cotacao.rate, 1)
WHEN  contas.currency = coalesce(cotacoes.symbol, last_cotacao.symbol)
THEN  (1 / coalesce(cotacoes.rate, last_cotacao.rate, 1))
ELSE 1 END) as cotacao
 FROM contas
inner join profiles on profiles.id = contas.id_profile
/* COTACAO DATA REF */
left join cotacoes ON date(cotacoes.date, 'start of month') = date(:datainicio, 'start of month')
AND ((cotacoes.base = profiles.currency AND cotacoes.symbol = contas.currency)
OR (cotacoes.base = contas.currency AND cotacoes.symbol = profiles.currency))
/* ULTIMA COTACAO */
left join cotacoes as last_cotacao ON last_cotacao.last = 'S'
AND ((last_cotacao.base = profiles.currency AND last_cotacao.symbol = contas.currency)
OR (last_cotacao.base = contas.currency AND last_cotacao.symbol = profiles.currency))
WHERE
(contas.data_exclusao IS NULL OR
  date(strftime('%Y-%m-01',:datainicio)) <=
  date(strftime('%Y-%m-01', contas.data_exclusao)))
  AND (:somadas = 'N' OR ifnull(contas.somar_total, 'S') = 'S')
  /**{params_contas}**/
) as contas on contas.id_categoria = contas_cat.id

/* CONTA SALDO */
left join contas_saldo on contas_saldo.id_conta = contas.id
                                and contas_saldo.mes = strftime('%m', :datainicio)
                                and contas_saldo.ano = strftime('%Y', :datainicio)

/* DESPESAS */
left join (SELECT
           id_conta,
           SUM((case when status = 'pd' OR val < 0 then 0 else (val + juros) end)) as pago,
           SUM((case when status = 'pg' OR val < 0 then 0 else (val + juros) end)) as pendente,
           SUM((case when status = 'pd' AND val < 0 then val else 0 end)) as estornos_pend,
           SUM((case when status = 'pg' AND val < 0 then val else 0 end)) as estornos_efet
           FROM (SELECT
           despesas.id,
           ifnull(despesas_fixas_valor.id_conta, despesas.id_conta) as id_conta,
           (case when despesas.recorrencia != 'F' then despesas.status
           else ifnull(despesas_fixas.status, 'pd') end ) as status,
           (round(SUM(catmap.valor), 2) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as val,
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
           GROUP BY id_conta) as despesas ON despesas.id_conta = contas.id

/* RECEITAS */
LEFT JOIN (SELECT
         ifnull(receitas_fixas_valor.id_conta, receitas.id_conta) as id_conta,
         SUM(CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                       	  else ifnull(receitas_fixas.efetivado,'N') end) = 'N' THEN 0 ELSE
                       	  round(COALESCE(receitas_fixas_valor.valor, receitas.valor), 2) END) as efetivadas,

         SUM(CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                       	  else ifnull(receitas_fixas.efetivado,'N') end) = 'S' THEN 0 ELSE
                       	  round(COALESCE(receitas_fixas_valor.valor, receitas.valor), 2) END) as pendentes,

         (CASE WHEN   COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao, '') != '' THEN
		   COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao)
		   ELSE
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
         GROUP BY ifnull(receitas_fixas_valor.id_conta, receitas.id_conta)) as receitas ON receitas.id_conta = contas.id


/* TRANSFERENCIAS CREDITO*/
LEFT JOIN (SELECT
    ifnull(transferencias_fixas_valor.id_conta_destino, transf.id_conta_destino) as id_conta_destino,

 SUM(round((CASE WHEN (CASE WHEN (ifnull(transf.recorrencia,'N') = 'N' OR transf.recorrencia = 'P') THEN transf.contabilizada
  WHEN transf.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
  THEN 'N'
  ELSE transferencias_fixas.contabilizada END) = 'N'
  THEN 0
  WHEN transf.id_profile = :id_profile
  THEN ifnull(transferencias_fixas_valor.valor, transf.valor)
  ELSE ifnull(transferencias_fixas_valor.valor, transf.valor) * COALESCE(transferencias_fixas_valor.cotacao, transf.cotacao, 1)
  END), 2)) as transf_efet,

 SUM(round((CASE WHEN (CASE WHEN (ifnull(transf.recorrencia,'N') = 'N' OR transf.recorrencia = 'P') THEN transf.contabilizada
  WHEN transf.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
  THEN 'N'
  ELSE transferencias_fixas.contabilizada END) = 'S'
  THEN 0
  WHEN transf.id_profile = :id_profile
  THEN ifnull(transferencias_fixas_valor.valor, transf.valor)
  ELSE ifnull(transferencias_fixas_valor.valor, transf.valor) * COALESCE(transferencias_fixas_valor.cotacao, transf.cotacao, 1)
  END), 2)) as transf_pend,

    (CASE WHEN transf.recorrencia = 'M'
    THEN
    COALESCE(transferencias_fixas.data_efetivacao, DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
    (CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
    THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
    ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2)
    END)))
    ELSE COALESCE(transf.data_efetivacao, transf.data)  END) as dt

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
    date(strftime('%Y-%m-01', :datainicio)) <=
    date(strftime('%Y-%m-01', transf.data_exclusao)))
    GROUP BY ifnull(transferencias_fixas_valor.id_conta_destino, transf.id_conta_destino)) as transfers_cred ON transfers_cred.id_conta_destino = contas.id


/* TRANSFERENCIAS DEBITO */
LEFT JOIN (SELECT
    ifnull(transferencias_fixas_valor.id_conta_origem, transf.id_conta_origem) as id_conta_origem,

 SUM(round((CASE WHEN (CASE WHEN (ifnull(transf.recorrencia,'N') = 'N' OR transf.recorrencia = 'P') THEN transf.contabilizada
  WHEN transf.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
  THEN 'N'
  ELSE transferencias_fixas.contabilizada END) = 'N'
  THEN 0
  WHEN transf.id_profile = :id_profile
  THEN ifnull(transferencias_fixas_valor.valor, transf.valor)
  ELSE ifnull(transferencias_fixas_valor.valor, transf.valor) * COALESCE(transferencias_fixas_valor.cotacao, transf.cotacao, 1)
  END), 2)) as transf_efet,

 SUM(round((CASE WHEN (CASE WHEN (ifnull(transf.recorrencia,'N') = 'N' OR transf.recorrencia = 'P') THEN transf.contabilizada
  WHEN transf.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
  THEN 'N'
  ELSE transferencias_fixas.contabilizada END) = 'S'
  THEN 0
  WHEN transf.id_profile = :id_profile
  THEN ifnull(transferencias_fixas_valor.valor, transf.valor)
  ELSE ifnull(transferencias_fixas_valor.valor, transf.valor) * COALESCE(transferencias_fixas_valor.cotacao, transf.cotacao, 1)
  END), 2)) as transf_pend,

    (CASE WHEN transf.recorrencia = 'M'
    THEN
    COALESCE(transferencias_fixas.data_efetivacao, DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
    (CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
    THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
    ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2)
    END)))
    ELSE COALESCE(transf.data_efetivacao, transf.data)  END) as dt

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
    date(strftime('%Y-%m-01', :datainicio)) <=
    date(strftime('%Y-%m-01', transf.data_exclusao)))
    GROUP BY ifnull(transferencias_fixas_valor.id_conta_origem, transf.id_conta_origem)) as transfers_deb ON transfers_deb.id_conta_origem = contas.id

GROUP BY contas_cat.id
HAVING contas_cat.id_profile = :id_profile
/**{params}**/
