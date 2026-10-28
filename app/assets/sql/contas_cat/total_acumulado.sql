SELECT
     ifnull(sum(ifnull((select

       sum(

       (CASE WHEN date(strftime('%Y-%m-01',:datainicio)) > date(strftime('%Y-%m-01','now')) THEN

       (
       ifnull(contas_saldo.si, 0)

       /* TRANSFERENCIAS CREDITO TOTAL */
       + (select ifnull(SUM(total),0) from (SELECT

          round((CASE WHEN transf.id_profile = :id_profile
          THEN ifnull(transferencias_fixas_valor.valor, transf.valor)
          ELSE ifnull(transferencias_fixas_valor.valor, transf.valor) * COALESCE(transferencias_fixas_valor.cotacao, transf.cotacao, 1)
          END), 2) as total,

           (CASE WHEN transf.recorrencia = 'M'
           THEN
           COALESCE(transferencias_fixas.data_efetivacao, DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
           (CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
           THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
           ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2)
           END)))
           ELSE COALESCE(transf.data_efetivacao, transf.data)  END) as dt
           from transferencias as transf
           left join transferencias_fixas on transf.id = transferencias_fixas.id_transferencia
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
           date(strftime('%Y-%m-01', transf.data_exclusao)))
           AND ifnull(transferencias_fixas_valor.id_conta_destino, transf.id_conta_destino) = contas.id))

       /* RECEITAS TOTAL */
       + ((select ifnull(SUM(total),0) from (select
                                  round(COALESCE(receitas_fixas_valor.valor, receitas.valor), 2) as total,
                                  (CASE WHEN ifnull(receitas.recorrencia,'N') = 'M' THEN
                                  datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
                                  (CASE WHEN  substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                                  THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                                  ELSE   substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
                                  END))
                                  ELSE receitas.data  END) as dt
                                  from receitas left join receitas_fixas on receitas.id = receitas_fixas.id_receita
                                                  and date(ifnull(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
                                                  left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
                                                  and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                                                                   and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
                                  where
                                  ifnull(receitas_fixas.excluido_mes,'N') = 'N'
                                  and (:obedecer_estatistcas = 'N' OR ifnull(receitas.considerar_estatistica, 'S') = 'S')
                                  AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
                                    AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
                                          and date(:datainicio,'start of month','+1 month','-1 day')
                                 AND (receitas.data_exclusao IS NULL OR
                                                           date(strftime('%Y-%m-01',:datainicio)) <=
                                                           date(strftime('%Y-%m-01', receitas.data_exclusao)))
                                 AND ifnull(receitas_fixas.id_conta, receitas.id_conta) = contas.id))
                                 * (case WHEN contas.currency = coalesce(cotacoes.base, last_cotacao.base)
                                    THEN  coalesce(cotacoes.rate, last_cotacao.rate, 1)
                                    WHEN  contas.currency = coalesce(cotacoes.symbol, last_cotacao.symbol)
                                    THEN  (1 / coalesce(cotacoes.rate, last_cotacao.rate, 1))
                                    ELSE 1 END))
         {debito_part1}
         )

       ELSE

       ( ifnull(contas_saldo.si, 0)

        /* TRANSFERENCIAS CREDITO EFETIVADAS */
        + (select ifnull(SUM(total),0) from (SELECT

                round((CASE WHEN transf.id_profile = :id_profile
                          THEN ifnull(transferencias_fixas_valor.valor, transf.valor)
                          ELSE ifnull(transferencias_fixas_valor.valor, transf.valor) * COALESCE(transferencias_fixas_valor.cotacao, transf.cotacao, 1)
                          END), 2) as total,

                   (CASE WHEN transf.recorrencia = 'M'
                   THEN
                   COALESCE(transferencias_fixas.data_efetivacao, DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
                   (CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                   THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                   ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transf.data)), -2, 2)
                   END)))
                   ELSE COALESCE(transf.data_efetivacao, transf.data)  END) as dt,
                   (CASE WHEN (ifnull(transf.recorrencia,'N') = 'N' OR transf.recorrencia = 'P')
                   THEN transf.contabilizada
                   WHEN transf.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
                   THEN 'N'
                   ELSE transferencias_fixas.contabilizada END) as contada
                   from transferencias as transf left join transferencias_fixas on transf.id = transferencias_fixas.id_transferencia
                                                        and date(ifnull(transferencias_fixas.data, transf.data), 'start of month') = date(:datainicio, 'start of month')
                 left join transferencias_fixas as transferencias_fixas_valor on transferencias_fixas_valor.id_transferencia = transf.id
                 and date(transferencias_fixas_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month') from transferencias_fixas where transferencias_fixas.id_transferencia = transf.id
                                                  and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
                   where
                   contada = 'S'
                   AND ifnull(transferencias_fixas.excluido_mes,'N') = 'N'
                   AND (transf.recorrencia != 'M' OR date(transf.data, 'start of month') <= date(dt, 'start of month'))
                   AND date(dt) between date(strftime('%Y-%m-01', :datainicio))
                   AND date(:datainicio,'start of month','+1 month','-1 day')
                   AND (transf.data_exclusao IS NULL OR
                   date(strftime('%Y-%m-01',:datainicio)) <=
                   date(strftime('%Y-%m-01', transf.data_exclusao)))
                   AND ifnull(transferencias_fixas_valor.id_conta_destino, transf.id_conta_destino) = contas.id))

       /* RECEITAS EFETIVADAS */
        + ((select ifnull(SUM(total),0) from (select
                                   ifnull(receitas_fixas_valor.valor, receitas.valor) as total,
                                   (CASE WHEN ifnull(receitas.recorrencia,'N') = 'M' THEN
                                   datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
                                   (CASE WHEN  substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                                   THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
                                   ELSE   substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
                                   END))
                                   ELSE receitas.data  END) as dt,
                                   (case when receitas.recorrencia = 'M' and receitas_fixas.efetivado is null
                                   		then 'N'
                                         when  receitas.recorrencia = 'M' and receitas_fixas.efetivado is not null
                                   		then receitas_fixas.efetivado
                                   	  when receitas.recorrencia != 'M'
                                   		then receitas.efetivado
                                   	   end ) as st
                                   from receitas left join receitas_fixas on receitas.id = receitas_fixas.id_receita
                                                   and date(ifnull(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
                                                   left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
                                                   and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                                                                    and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
                                   where
                                   st = 'S'
                                   and (:obedecer_estatistcas = 'N' OR ifnull(receitas.considerar_estatistica, 'S') = 'S')
                                   AND ifnull(receitas_fixas.excluido_mes,'N') = 'N'
                                   AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
                                     AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
                                           and date(:datainicio,'start of month','+1 month','-1 day','23:59:59')
                                  AND (receitas.data_exclusao IS NULL OR
                                                            date(strftime('%Y-%m-01',:datainicio)) <=
                                                            date(strftime('%Y-%m-01', receitas.data_exclusao)))
                                  AND ifnull(receitas_fixas.id_conta, receitas.id_conta) = contas.id))
                                  * (case WHEN contas.currency = coalesce(cotacoes.base, last_cotacao.base)
                                    THEN  coalesce(cotacoes.rate, last_cotacao.rate, 1)
                                    WHEN  contas.currency = coalesce(cotacoes.symbol, last_cotacao.symbol)
                                    THEN  (1 / coalesce(cotacoes.rate, last_cotacao.rate, 1))
                                    ELSE 1 END))
          {debito_part2})

       END))

       from contas
       inner join profiles on profiles.id = contas.id_profile
       left join contas_saldo on contas_saldo.id_conta = contas.id
               and contas_saldo.mes = strftime('%m', :datainicio)
               and contas_saldo.ano = strftime('%Y', :datainicio)

       /* COTACAO DATA REF */
       left join cotacoes ON date(cotacoes.date, 'start of month') = date(:datainicio, 'start of month')
       AND ((cotacoes.base = profiles.currency AND cotacoes.symbol = contas.currency)
       OR (cotacoes.base = contas.currency AND cotacoes.symbol = profiles.currency))

       /* ULTIMA COTACAO */
       left join cotacoes as last_cotacao ON last_cotacao.last = 'S'
       AND ((last_cotacao.base = profiles.currency AND last_cotacao.symbol = contas.currency)
       OR (last_cotacao.base = contas.currency AND last_cotacao.symbol = profiles.currency))

       where contas.id_categoria = contas_cat.id
       AND (contas.data_exclusao IS NULL OR
               date(strftime('%Y-%m-01',:datainicio)) <=
               date(strftime('%Y-%m-01', contas.data_exclusao)))
       /**{params_contas}**/
       ),0)),0) as total
FROM contas_cat
where contas_cat.id_profile = :id_profile
and (:id_categoria = '' or contas_cat.id = :id_categoria)
