SELECT COALESCE(SUM(ROUND(receitas.valor, 2) *
       CASE WHEN contas.currency = :moeda_base THEN 1
            ELSE COALESCE(receitas.cotacao, 1) END), 0)
FROM receitas
LEFT JOIN contas ON contas.id = receitas.id_conta
WHERE receitas.id_orig_parcial = :id_original
  /* O vínculo guarda o vencimento original, independente da data do recebimento. */
  AND (:apenas_mes_original = 'N' OR
       DATE(receitas.dt_orig_parcial, 'start of month') = DATE(:data_original, 'start of month'))
