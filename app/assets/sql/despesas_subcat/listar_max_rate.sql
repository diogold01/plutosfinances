SELECT
    s.id,
    s.id_profile,
    s.nome,
    s.cor,
    s.id_categoria,
    s.icon_id,
    s.data_exclusao AS cat_data_exclusao,
    0 AS efet,
    0 AS pend,
    0 AS registros
FROM despesas_subcat s
LEFT JOIN (
    SELECT
        dcv.id_subcategoria AS id_subcategoria,
        COUNT(1)            AS qt
FROM despesas_cat_valor dcv
JOIN despesas d ON dcv.id_despesa = d.id
WHERE dcv.id_categoria = :id_categoria
  AND DATE(COALESCE(d.data_cadastro, dcv.data)) >= DATE('now', '-30 days')
GROUP BY dcv.id_subcategoria
) u ON u.id_subcategoria = s.id
WHERE s.id_categoria = :id_categoria
  AND IFNULL(s.rate, 0) != 0
  AND s.data_exclusao IS NULL
ORDER BY
    CASE WHEN u.qt IS NULL THEN 0 ELSE 1 END DESC,  -- primeiro quem tem uso recente
    u.qt DESC,                                      -- mais usada nos últimos 30 dias
    IFNULL(s.rate, 0) DESC,                         -- fallback: rate
    s.nome ASC
LIMIT 1