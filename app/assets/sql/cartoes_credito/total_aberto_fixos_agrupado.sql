-- Calcula todos os cartões na mesma varredura. A consulta anterior era
-- repetida uma vez por cartão durante cada carga mensal.
SELECT
  id_cartao,
  SUM(total) AS total
FROM (
  SELECT
    ifnull(
      despesas_fixas_valor.id_cartao_credito,
      despesas.id_cartao_credito
    ) AS id_cartao,
    (
      SUM(catmap.valor) +
      COALESCE(despesas_fixas.juros, despesas.juros, 0)
    ) AS total,
    (
      datetime(
        strftime('%Y', :datainicio) || '-' ||
        strftime('%m', :datainicio) || '-' ||
        (
          CASE
            WHEN substr(
              '0' || ifnull(
                despesas_fixas_valor.dia_venc,
                strftime('%d', despesas.data)
              ),
              -2,
              2
            ) > strftime(
              '%d',
              date(:datainicio, 'start of month', '+1 month', '-1 day')
            )
            THEN strftime(
              '%d',
              date(:datainicio, 'start of month', '+1 month', '-1 day')
            )
            ELSE substr(
              '0' || ifnull(
                despesas_fixas_valor.dia_venc,
                strftime('%d', despesas.data)
              ),
              -2,
              2
            )
          END
        )
      )
    ) AS dt,
    despesas.data AS dtoriginal,
    (
      CASE
        WHEN despesas_fixas.status IS NULL THEN 'pd'
        WHEN despesas_fixas.status IS NOT NULL THEN despesas_fixas.status
      END
    ) AS st
  FROM despesas
  INNER JOIN despesas_cat_valor AS catmap
    ON catmap.id_despesa = despesas.id
    AND (
      despesas.recorrencia != 'F' OR
      (
        date(catmap.data) = date(
          (
            SELECT MAX(despesas_cat_valor.data)
            FROM despesas_cat_valor
            WHERE id_despesa = catmap.id_despesa
              AND id_categoria = catmap.id_categoria
              AND id_subcategoria = catmap.id_subcategoria
              AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs, ''))
              AND date(despesas_cat_valor.data) <=
                DATE(:datainicio, 'start of month')
          )
        )
        AND catmap.excluido != 'S'
      )
    )
  LEFT JOIN despesas_fixas
    ON despesas.id = despesas_fixas.id_despesa
    AND date(ifnull(despesas_fixas.data, despesas.data), 'start of month') =
      date(:datainicio, 'start of month')
  LEFT JOIN despesas_fixas AS despesas_fixas_valor
    ON despesas_fixas_valor.id_despesa = despesas.id
    AND date(despesas_fixas_valor.data, 'start of month') = (
      SELECT date(MAX(despesas_fixas.data), 'start of month')
      FROM despesas_fixas
      WHERE id_despesa = despesas.id
        AND date(despesas_fixas.data, 'start of month') <=
          date(:datainicio, 'start of month')
    )
  WHERE st = 'pd'
    AND despesas.recorrencia = 'F'
    AND ifnull(despesas_fixas.excluido_mes, 'N') = 'N'
    AND (
      despesas.recorrencia != 'F' OR
      date(despesas.data, 'start of month') <= date(dt, 'start of month')
    )
    AND date(dt) BETWEEN date(strftime('%Y-%m-01', :datainicio))
      AND date(
        :datainicio,
        'start of month',
        '+1 month',
        '-1 day',
        '23:59:59'
      )
    AND (
      despesas.data_exclusao IS NULL OR
      date(strftime('%Y-%m-01', :datainicio)) <=
        date(strftime('%Y-%m-01', despesas.data_exclusao))
    )
    AND ifnull(
      despesas_fixas_valor.id_cartao_credito,
      despesas.id_cartao_credito
    ) NOT IN ('', '-1')
  GROUP BY catmap.id_despesa
)
GROUP BY id_cartao
