SELECT
receitas_subcat.id,
receitas_subcat.nome,
receitas_subcat.cor,
receitas_subcat.id_categoria,
receitas_subcat.icon_id,
receitas_subcat.id_profile,
ifnull(receitas_subcat.orcamento, 'N') as orcamento,
receitas_subcat.data_exclusao as cat_data_exclusao,
(case when nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
0 as efet,
0 as pend,
0 as registros
FROM receitas_subcat
/**{INNER_JOIN}**/
WHERE (:id_categoria IS NULL OR receitas_subcat.id_categoria = :id_categoria)
/**{params}**/
ORDER BY ord, nome