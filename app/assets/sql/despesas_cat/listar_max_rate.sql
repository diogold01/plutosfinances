SELECT
    c.id,
    c.id_profile,
    c.nome,
    IFNULL(c.orcamento, 'S')    AS orcamento,
    IFNULL(c.not_dash, 'N')     AS not_dash,
    c.data_exclusao             AS cat_data_exclusao,
    c.cor,
    c.icon_id,
    0 AS efet,
    0 AS pend,
    0 AS registros
FROM despesas_cat c
LEFT JOIN (
    SELECT
        dcv.id_categoria AS id_categoria,
        COUNT(1)         AS qt
    FROM despesas_cat_valor dcv
    JOIN despesas d ON dcv.id_despesa = d.id
    WHERE d.id_profile = :id_profile
      AND DATE(COALESCE(d.data_cadastro, dcv.data)) >= DATE('now', '-30 days')
    GROUP BY dcv.id_categoria
) u ON u.id_categoria = c.id
WHERE IFNULL(c.rate, 0) != 0
  AND c.id_profile = :id_profile
  AND c.data_exclusao IS NULL
ORDER BY
    CASE WHEN u.qt IS NULL THEN 0 ELSE 1 END DESC,  -- primeiro quem tem uso recente
    u.qt DESC,                                      -- mais usada nos últimos 30 dias
    IFNULL(c.rate, 0) DESC,                         -- fallback: rate
    c.nome ASC
LIMIT 1