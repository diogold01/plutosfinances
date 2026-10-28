        - (select ifnull(SUM(total),0) from (SELECT


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
        from transferencias as transf left join transferencias_fixas on transf.id = transferencias_fixas.id_transferencia
                                             and date(ifnull(transferencias_fixas.data, transf.data), 'start of month') = date(:datainicio, 'start of month')
      left join transferencias_fixas as transferencias_fixas_valor on transferencias_fixas_valor.id_transferencia = transf.id
      and date(transferencias_fixas_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month') from transferencias_fixas where transferencias_fixas.id_transferencia = transf.id
                                       and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
       WHERE
        ifnull(transferencias_fixas.excluido_mes,'N') = 'N'
        AND (transf.recorrencia != 'M' OR date(transf.data, 'start of month') <= date(dt, 'start of month'))
        AND date(dt) between date(strftime('%Y-%m-01', :datainicio))
        AND date(:datainicio,'start of month','+1 month','-1 day')
        AND (transf.data_exclusao IS NULL OR
        date(strftime('%Y-%m-01',:datainicio)) <=
        date(strftime('%Y-%m-01', transf.data_exclusao)))
        AND ifnull(transferencias_fixas_valor.id_conta_origem, transf.id_conta_origem) = contas.id))
          - ((SELECT ifnull(SUM(total),0)
          FROM (SELECT
         (round(SUM(catmap.valor), 2) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as total,
         (CASE WHEN COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito,'-1') IN ('', '-1') AND
         COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao,'') != '' THEN
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
         and (:obedecer_estatistcas = 'N' OR ifnull(despesas.considerar_estatistica, 'S') = 'S')
        AND ifnull(despesas_fixas.excluido_mes,'N') = 'N'
        AND (despesas.data_exclusao IS NULL OR
                date(strftime('%Y-%m-01',:datainicio)) <=
                date(strftime('%Y-%m-01', despesas.data_exclusao)))
         AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
         and date(:datainicio,'start of month','+1 month','-1 day')
         AND ifnull(despesas_fixas.id_conta, despesas.id_conta) = contas.id
         GROUP BY catmap.id_despesa))
         *   (case WHEN contas.currency = coalesce(cotacoes.base, last_cotacao.base)
             THEN  coalesce(cotacoes.rate, last_cotacao.rate, 1)
             WHEN  contas.currency = coalesce(cotacoes.symbol, last_cotacao.symbol)
             THEN  (1 / coalesce(cotacoes.rate, last_cotacao.rate, 1))
             ELSE 1 END))