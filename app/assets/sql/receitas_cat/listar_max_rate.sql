SELECT
    c.descricao                AS descr,
    IFNULL(c.cor, 0)           AS cor,
    c.id                       AS cat_id,
    c.id_profile,
    IFNULL(c.orcamento, 'S')   AS orcamento,
    IFNULL(c.not_dash, 'N')    AS not_dash,
    c.data_exclusao            AS cat_data_exclusao,
    c.icon_id,
    0 AS efet,
    0 AS pend,
    0 AS registros
FROM receitas_cat c
LEFT JOIN (
    SELECT
        r.id_categoria      AS id_categoria,
        COUNT(1)            AS qt
    FROM receitas r
    JOIN receitas_cat c2 ON c2.id = r.id_categoria
    WHERE c2.id_profile = :id_profile
      AND DATE(COALESCE(r.data_cadastro, r.data)) >= DATE('now', '-30 days') -- ajuste o período aqui
    GROUP BY r.id_categoria
) u ON u.id_categoria = c.id
WHERE IFNULL(c.rate, 0) != 0
  AND c.id_profile = :id_profile
  AND c.data_exclusao IS NULL
ORDER BY
    CASE WHEN u.qt IS NULL THEN 0 ELSE 1 END DESC,  -- primeiro quem tem uso recente
    u.qt DESC,                                      -- mais usada nos últimos 30 dias
    IFNULL(c.rate, 0) DESC,                         -- fallback: seu contador antigo
    c.descricao ASC
LIMIT 1;
