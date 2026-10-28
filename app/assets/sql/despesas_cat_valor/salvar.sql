INSERT INTO despesas_cat_valor (
id,
id_despesa,
id_categoria,
id_subcategoria,
valor,
obs,
excluido,
data)
VALUES(
:id,
:id_despesa,
:id_categoria,
:id_subcategoria,
:valor,
:obs,
:excluido,
date(:data, 'start of month'));