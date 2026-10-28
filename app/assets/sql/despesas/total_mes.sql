SELECT ifnull(SUM(total),0) FROM (SELECT
             ((round(SUM(catmap.valor), 2) + COALESCE(despesas_fixas.juros, despesas.juros, 0))
              * COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1)) as total,
             {param_data_referencia} as dt,

             (case when despesas.recorrencia = 'F' and despesas_fixas.status is null
               		then 'pd'
                     when  despesas.recorrencia = 'F' and despesas_fixas.status is not null
               		then despesas_fixas.status
               	  when despesas.recorrencia != 'F'
               		then despesas.status
               	   end ) as st

               FROM despesas
               inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
               AND (despesas.recorrencia != 'F' OR
                   (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                    AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
                    AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
                    AND catmap.excluido != 'S'))
                left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
               and (date(COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao), 'start of month') = date(:datainicio, 'start of month') OR date(despesas_fixas.data, 'start of month') = date(:datainicio, 'start of month'))
                left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
                    and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
                    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

               left join contas on contas.id = COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta)
               left JOIN profiles on profiles.id = contas.id_profile

               /* COTACAO DATA REF */
               left join cotacoes ON date(cotacoes.date, 'start of month') = date(:datainicio, 'start of month')
               AND ((cotacoes.base = profiles.currency AND cotacoes.symbol = contas.currency)
               OR (cotacoes.base = contas.currency AND cotacoes.symbol = profiles.currency))

               /* ULTIMA COTACAO */
               left join cotacoes as last_cotacao ON last_cotacao.last = 'S'
               AND ((last_cotacao.base = profiles.currency AND last_cotacao.symbol = contas.currency)
               OR (last_cotacao.base = contas.currency AND last_cotacao.symbol = profiles.currency))

              WHERE
              (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
              AND despesas.id_profile = :id_profile
              AND ifnull(despesas_fixas.excluido_mes,'N') = 'N'
              AND ifnull(despesas.economia_mensal,'S') = 'S'
              AND (:considerar_nao_somadas = 'S' OR ifnull(despesas.somar_total,'S') = 'S')
              AND (:obedecer_estatistcas = 'N' OR ifnull(despesas.considerar_estatistica, 'S') = 'S')
              AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
              AND date(:datainicio,'start of month','+1 month','-1 day')
              AND (despesas.data_exclusao IS NULL OR
                                   date(strftime('%Y-%m-01',:datainicio)) <=
                                   date(strftime('%Y-%m-01', despesas.data_exclusao)))
              /**{params}**/
              GROUP BY catmap.id_despesa
              )