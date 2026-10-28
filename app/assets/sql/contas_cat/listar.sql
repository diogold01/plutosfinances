SELECT
       contas_cat.descricao as descricao,
       contas_cat.padrao as padrao,
       contas_cat.id_profile as id_profile,
       ifnull(contas_cat.cor, 0) as cor,
       ifnull(not_resume, 'N') as not_resume,
       ifnull(not_balance, 'N') as not_balance,
       ifnull(contas_cat.not_dash, 'N') as not_dash,
       ifnull(contas_cat.icon_id, 252) as icon_id,
       contas_cat.id as id,
        0 as total,
        0 as registros,
        (case when descricao in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord
FROM contas_cat
{PARAMS}
ORDER BY ord, descricao
