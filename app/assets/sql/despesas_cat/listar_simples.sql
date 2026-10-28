SELECT
id,
nome,
cor,
icon_id,
id_profile,
ifnull(despesas_cat.orcamento, 'N') as orcamento,
ifnull(despesas_cat.not_dash, 'N') as not_dash,
despesas_cat.data_exclusao as cat_data_exclusao,
(case when nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
0 as efet,
0 as pend,
0 as registros
FROM  despesas_cat
/**{INNER_JOIN}**/
WHERE 0=0
/**{params}**/