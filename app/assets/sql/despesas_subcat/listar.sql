select
despesas_subcat.id,
despesas_subcat.nome,
despesas_subcat.cor,
despesas_subcat.icon_id,
despesas_subcat.id_profile,
despesas_subcat.id_categoria,
despesas_subcat.data_exclusao as cat_data_exclusao,
(case when nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
ifnull(SUM(despesas.pago), 0) as efet,
ifnull(SUM(despesas.pendente), 0) as pend,
COUNT(despesas.pago) as registros

FROM despesas_subcat LEFT JOIN
                          (SELECT id_categoria,
                             id_subcategoria,
                            SUM(pago * cotacao) as pago,
                            SUM(pendente * cotacao) as pendente
                            FROM (SELECT
                                   catmap.id_categoria,
                                   catmap.id_subcategoria,
                               (case when (
                                     case when recorrencia = 'F'
                                        then COALESCE(despesas_fixas.status, 'pd')
                                        ELSE despesas.status end) = 'pd'
                                        then 0
                                        else (SUM(catmap.valor) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) end) as pago,

                                 (case when (case when recorrencia = 'F'
                                        then COALESCE(despesas_fixas.status, 'pd')
                                        ELSE despesas.status end) = 'pg'
                                        then 0
                                        else (SUM(catmap.valor) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) end) as pendente,

                                 COALESCE(despesas_fixas.cotacao, despesas.cotacao, 1) cotacao,

                                 {param_data_referencia} as dt

                                  FROM despesas
                                  left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
                                   and date(ifnull(despesas_fixas.data, despesas.data), 'start of month') = date(:datainicio, 'start of month')

                                   inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
                                   AND (despesas.recorrencia != 'F' OR
                                          (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                                           AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
                                           AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
                                           AND catmap.excluido != 'S'))

                                   left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
                                        and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
                                        and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))


                                 WHERE
                                 (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
                                    and ifnull(despesas_fixas.excluido_mes,'N') = 'N'
                                    and (:graficos = 'N' OR ifnull(despesas.considerar_estatistica, 'S') = 'S')
                                    and (:filtro_cartao = 'N' OR ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) = :id_cartao_credito)
                                    and (:apenas_cartao = 'N' OR ifnull(ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito), '-1') NOT IN ('', '-1'))
                                    AND (despesas.data_exclusao IS NULL OR
                                       date(strftime('%Y-%m-01',:datainicio)) <=
                                       date(strftime('%Y-%m-01', despesas.data_exclusao)))
                               AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
                               AND date(:datainicio,'start of month','+1 month','-1 day')
                               GROUP BY despesas.id, catmap.id_categoria, catmap.id_subcategoria)
                               GROUP BY id_categoria, id_subcategoria) as  despesas ON despesas.id_categoria =  :id_categoria
                                    AND despesas.id_subcategoria = despesas_subcat.id

WHERE despesas_subcat.id_categoria = :id_categoria
/**{params}**/
GROUP BY despesas_subcat.id
HAVING (:graficos = 'N' OR (efet > 0 OR pend > 0))