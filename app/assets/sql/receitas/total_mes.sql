select ifnull(SUM(total * cotacao),0) from (select
             round(COALESCE(receitas_fixas_valor.valor, receitas.valor),2) as total,
             COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
                  {param_data_referencia} as dt,
                  ifnull((case when receitas.recorrencia = 'M' and receitas_fixas.efetivado is null
                  		then 'N'
                        when  receitas.recorrencia = 'M' and receitas_fixas.efetivado is not null
                  		then receitas_fixas.efetivado
                  	  when receitas.recorrencia != 'M'
                  		then receitas.efetivado
                  	   end ), 'N') as st
                 from receitas
                 left join receitas_fixas on receitas.id = receitas_fixas.id_receita
                 and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
                 left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
                 and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                                  and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
                  WHERE
                  (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
                  ANd receitas.id_profile = :id_profile
                  AND ifnull(receitas_fixas.excluido_mes,'N') = 'N'
                  AND ifnull(receitas.economia_mensal,'S') = 'S'
                  AND (:considerar_nao_somadas = 'S' OR ifnull(receitas.somar_total,'S') = 'S')
                  AND (:obedecer_estatistcas = 'N' OR ifnull(receitas.considerar_estatistica, 'S') = 'S')
                  AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
                  AND date(:datainicio,'start of month','+1 month','-1 day')
                  AND (receitas.data_exclusao IS NULL OR
                  date(strftime('%Y-%m-01',:datainicio)) <= date(strftime('%Y-%m-01', receitas.data_exclusao)))
                 /**{params}**/
                 )
