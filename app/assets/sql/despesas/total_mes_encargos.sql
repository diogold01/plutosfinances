SELECT ifnull(total,0) FROM (SELECT
              SUM(ifnull(despesas_fixas.juros,despesas.juros)) as total,
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
               left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
               and (date(COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao), 'start of month') = date(:datainicio, 'start of month') OR date(despesas_fixas.data, 'start of month') = date(:datainicio, 'start of month'))
               left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
                               and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
                               and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
              WHERE
              (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
              and despesas.id_profile = :id_profile
              and ifnull(despesas_fixas.excluido_mes,'N') = 'N'
              and (:obedecer_estatistcas = 'N' OR ifnull(despesas.considerar_estatistica, 'S') = 'S')
              AND (despesas.data_exclusao IS NULL OR date(strftime('%Y-%m-01',:datainicio)) <= date(strftime('%Y-%m-01', despesas.data_exclusao)))
              AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
              and date(:datainicio,'start of month','+1 month','-1 day')
              )