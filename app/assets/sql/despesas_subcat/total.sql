SELECT SUM(ifnull(total * cotacao,0)) FROM (SELECT
              (SUM(catmap.valor) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as total,
              despesas.id_profile,
              COALESCE(despesas_fixas.cotacao, despesas.cotacao, 1) cotacao,
              {param_data_referencia} as dt
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
                and ifnull(despesas_fixas.excluido_mes,'N') = 'N'
              AND (despesas.data_exclusao IS NULL OR
                                        date(strftime('%Y-%m-01',:datainicio)) <=
                                        date(strftime('%Y-%m-01', despesas.data_exclusao)))
              AND date(dt) between date(:datainicio) and date(:datafim)
              and catmap.id_categoria = :id_categoria
              and catmap.id_subcategoria = :id_subcategoria
              and despesas.id_profile = :id_profile
              GROUP BY despesas.id, catmap.id_categoria, catmap.id_subcategoria
              )
