SELECT
despesas_cat.id,
despesas_cat.nome,
despesas_cat.cor,
despesas_cat.icon_id,
despesas_cat.id_profile,
despesas_cat.data_exclusao as cat_data_exclusao,
COALESCE(despesas_cat.orcamento, 'S') as orcamento,
COALESCE(despesas_cat.not_dash, 'N') as not_dash,
(case when despesas_cat.nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
COALESCE(SUM(despesas.pago), 0) as efet,
COALESCE(SUM(despesas.pendente), 0) as pend,
COUNT(despesas.pago) as registros

FROM
   despesas_cat
   LEFT JOIN (SELECT id_categoria,
              SUM(pago * cotacao) as pago,
              SUM(pendente * cotacao) as pendente
              FROM (SELECT catmap.id_categoria,
                               (case when (
                                 case when recorrencia = 'F'
                            		then COALESCE(despesas_fixas.status, 'pd')
                            		ELSE despesas.status end) = 'pd'
                            		then 0
                            		else (round(SUM(catmap.valor), 2) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) end) as pago,

                             (case when (case when recorrencia = 'F'
                            		then COALESCE(despesas_fixas.status, 'pd')
                            		ELSE despesas.status end) = 'pg'
                            		then 0
                            		else (round(SUM(catmap.valor), 2) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) end) as pendente,

                              COALESCE(despesas_fixas.cotacao, despesas.cotacao, 1) cotacao,
                              {param_data_referencia} as dt
                              FROM despesas
                              left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(COALESCE(despesas_fixas.data, despesas.data), 'start of month') = date(:datainicio, 'start of month')

                               inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
                               AND (despesas.recorrencia != 'F' OR
                                      (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                                       AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(COALESCE(obs, '')) = LOWER(COALESCE(catmap.obs,''))
                                       AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
                                       AND catmap.excluido != 'S'))

                               left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
                                    and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
                                    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
                             WHERE
                             (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
                                and COALESCE(despesas_fixas.excluido_mes,'N') = 'N'
                                and (:graficos = 'N' OR COALESCE(despesas.considerar_estatistica, 'S') = 'S')
                                and (:filtro_cartao = 'N' OR COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) = :id_cartao_credito)
                                and (:filtro_conta = 'N' OR COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta) = :id_conta)
                                and (:apenas_cartao = 'N' OR COALESCE(COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito), '-1') !='-1')
                                AND (despesas.data_exclusao IS NULL OR
                                   date(strftime('%Y-%m-01',:datainicio)) <=
                                   date(strftime('%Y-%m-01', despesas.data_exclusao)))
                           AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
                           AND date(:datainicio,'start of month','+1 month','-1 day')
                           GROUP BY despesas.id, catmap.id_categoria
                           ) GROUP BY id_categoria) as  despesas ON despesas.id_categoria = despesas_cat.id
/**{INNER_JOIN}**/
WHERE 0=0
/**{params}**/
GROUP BY despesas_cat.id
HAVING (:graficos = 'N' OR (efet != 0 OR pend != 0))
