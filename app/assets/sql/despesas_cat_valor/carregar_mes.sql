SELECT
 id,
 id_despesa,
 id_categoria,
 id_subcategoria,
 valor,
 data,
 obs,
 excluido
FROM
 despesas_cat_valor
WHERE
id_despesa = :id_despesa
AND DATE(data, 'start of month') = DATE(:data, 'start of month')