SELECT
despesas_subcat.id,
despesas_subcat.nome,
despesas_subcat.cor,
despesas_subcat.id_profile,
despesas_subcat.id_categoria,
despesas_subcat.icon_id,
coalesce(despesas_subcat.orcamento, 'N') as orcamento,
despesas_subcat.data_exclusao as cat_data_exclusao,
(case when nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
0 as efet,
0 as pend,
0 as registros
FROM
despesas_subcat
/**{INNER_JOIN}**/
WHERE (:id_categoria IS NULL OR despesas_subcat.id_categoria = :id_categoria)
/**{params}**/
ORDER BY ord, nome