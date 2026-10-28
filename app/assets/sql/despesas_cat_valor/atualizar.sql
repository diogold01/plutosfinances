UPDATE despesas_cat_valor SET
valor = :valor,
id_categoria = :id_categoria,
id_subcategoria = :id_subcategoria,
obs = :obs,
data = :data
WHERE id = :id