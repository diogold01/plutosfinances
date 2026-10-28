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
FROM receitas_subcat s
LEFT JOIN (
    SELECT
        r.id_subcategoria AS id_subcategoria,
        COUNT(1)          AS qt
    FROM receitas r
    JOIN receitas_cat c ON c.id = r.id_categoria
    WHERE r.id_categoria = :id_categoria
      AND DATE(COALESCE(r.data_cadastro, r.data)) >= DATE('now', '-30 days')
      AND r.id_subcategoria IS NOT NULL
    GROUP BY r.id_subcategoria
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
