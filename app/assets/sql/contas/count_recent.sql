SELECT COUNT(0)
FROM contas
WHERE
id_profile = :id_profile
AND (contas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', contas.data_exclusao)))
