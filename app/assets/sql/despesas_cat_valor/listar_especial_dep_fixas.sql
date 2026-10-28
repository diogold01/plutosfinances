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
AND date(data) > date(:data)
AND (id_categoria != :id_categoria OR id_subcategoria != :id_subcategoria)