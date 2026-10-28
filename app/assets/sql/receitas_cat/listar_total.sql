SELECT
receitas_cat.descricao as descr,
COALESCE(receitas_cat.cor, 0) as cor,
receitas_cat.id as cat_id,
receitas_cat.id_profile,
COALESCE(receitas_cat.orcamento, 'S') as orcamento,
receitas_cat.icon_id,
COALESCE(receitas_cat.not_dash, 'N') as not_dash,
receitas_cat.data_exclusao as cat_data_exclusao,
(case when descricao in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
COALESCE(SUM(receitas.efetivadas * receitas.cotacao), 0) as efet,
COALESCE(SUM(receitas.pendentes * receitas.cotacao), 0) as pend,
COUNT(receitas.efetivadas) as registros
FROM receitas_cat LEFT JOIN
                (SELECT
                  COALESCE(receitas.id_categoria, '-1') as id_categoria,
                (CASE WHEN ifnull((CASE WHEN receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NULL
                  THEN 'N'
                 WHEN  receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NOT NULL
                  THEN receitas_fixas.efetivado
                WHEN receitas.recorrencia != 'M'
                  THEN receitas.efetivado
                 END), 'N') = 'N' THEN 0 ELSE ifnull(receitas_fixas_valor.valor, receitas.valor) END) as efetivadas,

                (CASE WHEN ifnull((CASE WHEN receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NULL
                 THEN 'N'
                 WHEN  receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NOT NULL
                 THEN receitas_fixas.efetivado
                 WHEN receitas.recorrencia != 'M'
                 THEN receitas.efetivado
                 END), 'N') = 'S' THEN 0 ELSE ifnull(receitas_fixas_valor.valor, receitas.valor) END) as pendentes,

                  COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
                  {param_data_referencia} as dt
                 from receitas left join receitas_fixas on receitas.id = receitas_fixas.id_receita
                   and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
                 left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
                 and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                                  and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

                  where
                  COALESCE(receitas_fixas.excluido_mes,'N') = 'N'
                  AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
                  AND (:filtro_conta = 'N' OR COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta) = :id_conta)
                  AND date(dt) between date(strftime('%Y-%m-01', :datainicio))
                  AND date(:datainicio,'start of month','+1 month','-1 day')
                  AND (:graficos = 'N' OR COALESCE(receitas.considerar_estatistica, 'S') = 'S')
                  AND (receitas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', receitas.data_exclusao)))) as receitas ON receitas.id_categoria = receitas_cat.id
/**{INNER_JOIN}**/
WHERE 0=0
/**{params}**/
GROUP BY receitas_cat.id
HAVING (:graficos = 'N' OR (efet != 0 OR pend != 0))
