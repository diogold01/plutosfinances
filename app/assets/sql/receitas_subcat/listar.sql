select
receitas_subcat.id,
receitas_subcat.nome,
receitas_subcat.cor,
receitas_subcat.id_categoria,
receitas_subcat.id_profile,
receitas_subcat.icon_id,
receitas_subcat.data_exclusao as cat_data_exclusao,
(case when nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
ifnull(SUM(receitas.efetivadas * cotacao), 0) as efet,
ifnull(SUM(receitas.pendentes * cotacao), 0) as pend,
COUNT(receitas.efetivadas) as registros
FROM receitas_subcat LEFT JOIN
 (SELECT
   receitas.id_categoria,
   receitas.id_subcategoria,
   (CASE WHEN (CASE WHEN receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NULL
     THEN 'N'
    WHEN  receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NOT NULL
     THEN receitas_fixas.efetivado
   WHEN receitas.recorrencia != 'M'
     THEN receitas.efetivado
    END) = 'N' THEN 0 ELSE ifnull(receitas_fixas_valor.valor, receitas.valor) END) as efetivadas,

   (CASE WHEN (CASE WHEN receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NULL
     THEN 'N'
      WHEN  receitas.recorrencia = 'M' AND receitas_fixas.efetivado IS NOT NULL
     THEN receitas_fixas.efetivado
   WHEN receitas.recorrencia != 'M'
     THEN receitas.efetivado
    END) = 'S' THEN 0 ELSE ifnull(receitas_fixas_valor.valor, receitas.valor) END) as pendentes,

    COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,

  {param_data_referencia} as dt

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
   AND (:graficos = 'N' OR ifnull(receitas.considerar_estatistica, 'S') = 'S')
   AND (receitas.data_exclusao IS NULL OR
           date(strftime('%Y-%m-01',:datainicio)) <=
           date(strftime('%Y-%m-01', receitas.data_exclusao)))) as receitas ON receitas.id_categoria = :id_categoria
           AND receitas.id_subcategoria = receitas_subcat.id

WHERE receitas_subcat.id_categoria = :id_categoria
/**{params}**/
GROUP BY receitas_subcat.id
HAVING (:graficos = 'N' OR (efet > 0 OR pend > 0))