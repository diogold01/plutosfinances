SELECT
       receitas_cat.descricao as descr,
       ifnull(receitas_cat.cor, 0) as cor,
       receitas_cat.id as cat_id,
       id_profile,
       ifnull(receitas_cat.orcamento, 'N') as orcamento,
       ifnull(receitas_cat.not_dash, 'N') as not_dash,
       receitas_cat.data_exclusao as cat_data_exclusao,
       receitas_cat.icon_id,
       (case when descricao in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
       0 as efet,
       0 as pend,
       0 registros
FROM receitas_cat
/**{INNER_JOIN}**/
WHERE 0=0
/**{params}**/
