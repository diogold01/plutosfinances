SELECT ifnull(count(0),0) as num
FROM cartoes_credito
WHERE
     (cartoes_credito.data_exclusao IS NULL OR
           date(strftime('%Y-%m-01',:datainicio)) <=
           date(strftime('%Y-%m-01',cartoes_credito.data_exclusao)))
 and id_profile = :id_profile