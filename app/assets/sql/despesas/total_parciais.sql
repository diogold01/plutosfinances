/* Cada parcial é avulsa. Agrupar os rateios antes de somar evita repetir encargos. */
SELECT COALESCE(SUM(parciais.valor), 0)
FROM (
    SELECT (ROUND(SUM(catmap.valor), 2) + COALESCE(despesas.juros, 0)) *
           CASE WHEN contas.currency = :moeda_base THEN 1
                ELSE COALESCE(despesas.cotacao, 1) END AS valor
    FROM despesas
    INNER JOIN despesas_cat_valor AS catmap ON catmap.id_despesa = despesas.id
    LEFT JOIN contas ON contas.id = despesas.id_conta
    WHERE despesas.id_orig_parcial = :id_original
      /* O vínculo guarda o vencimento original, independente da data do pagamento. */
      AND (:apenas_mes_original = 'N' OR
           DATE(despesas.dt_orig_parcial, 'start of month') = DATE(:data_original, 'start of month'))
    GROUP BY despesas.id
) AS parciais
