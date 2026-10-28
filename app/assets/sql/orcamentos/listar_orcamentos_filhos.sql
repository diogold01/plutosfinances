SELECT
o.id               AS id_orc,
o.descricao        AS descricao,
o.id_profile,
COALESCE(o.cor, 0) AS orc_cor,
COALESCE(o.icon_id, 955) AS orc_icon
FROM orcamentos_agrupamento rel
JOIN orcamentos o ON o.id = rel.id_filho
WHERE rel.id_pai = :id_pai
AND o.tipo = :tipo
AND o.data_inicial IS NULL
AND o.data_final  IS NULL
ORDER BY o.descricao
