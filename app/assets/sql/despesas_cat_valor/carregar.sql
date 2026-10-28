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
id = :id