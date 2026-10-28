SELECT
  o.id                    AS id_orc,
  o.descricao             AS descricao,
  o.id_profile,
  COALESCE(o.cor, 0)      AS orc_cor,
  COALESCE(o.icon_id,955) AS orc_icon
FROM orcamentos o
/* Marca se JÁ é filho do pai em edição */
LEFT JOIN orcamentos_agrupamento rel
  ON rel.id_filho = o.id
 AND rel.id_pai   = :id_pai
WHERE
  o.id_profile = :id_profile
  /* não listar o próprio pai */
  AND (:id_pai IS NULL OR o.id <> :id_pai)

  /* filtros padrão do seu app */
  AND o.tipo = :tipo
  AND (o.data_exclusao IS NULL OR DATE(:datainicio) <= DATE(o.data_exclusao))
  AND DATE(:datainicio) >= DATE(COALESCE(o.data_criacao, :datainicio))
  AND o.data_inicial IS NULL
  AND o.data_final  IS NULL
  {params}

  AND NOT EXISTS (
    SELECT 1
    FROM orcamentos_agrupamento r_pai
    WHERE r_pai.id_pai = o.id
  )

  AND (
    (:id_pai IS NULL AND NOT EXISTS (
        SELECT 1 FROM orcamentos_agrupamento r0 WHERE r0.id_filho = o.id
    ))
    OR
    (:id_pai IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM orcamentos_agrupamento r1
        WHERE r1.id_filho = o.id AND r1.id_pai <> :id_pai
    ))
  )
ORDER BY o.descricao;
