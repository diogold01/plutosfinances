SELECT
       contas_cat.id,
       contas_cat.descricao as descricao,
       contas_cat.padrao as padrao,
       contas_cat.id_profile as id_profile,
       ifnull(contas_cat.cor, 0) as cor,
       contas_cat.id as tipo_id,
       ifnull(contas_cat.icon_id, 252) as icon_id,
       ifnull(contas_cat.not_dash, 'N') as not_dash,
       ifnull(contas_cat.not_resume, 'N') as not_resume,
       ifnull(contas_cat.not_balance, 'N') as not_balance,
        0 as total,
        0 as registros
FROM contas_cat
WHERE
 ifnull(rate, 0) != 0
 and id_profile = :id_profile
ORDER BY ifnull(rate,0) DESC, descricao ASC
