SELECT o.*
FROM orcamentos o
WHERE
    o.tipo = :tipo  -- 'DESPESA' ou 'RECEITA'
AND (o.data_final IS NULL OR date(o.data_final) >= date('now'))
AND (o.data_exclusao IS NULL OR date(COALESCE(o.data_inicial, date('now'))) <= date(o.data_exclusao))

-- Pelo menos um filtro precisa estar informado
AND (
    COALESCE(:categorias_csv,     '') <> '' OR
    COALESCE(:subcategorias_csv,  '') <> '' OR
    COALESCE(:tags_csv,           '') <> '' OR
    COALESCE(:cartoes_csv,        '') <> ''
)

-- Cada filtro informado é obrigatório (AND condicional).
-- Ex.: se subcategoria for informada, o orçamento precisa casar com ela.
AND (
    COALESCE(:categorias_csv, '') = '' OR EXISTS (
        SELECT 1
        FROM orcamentos_categorias oc
        WHERE oc.id_orcamento = o.id
          AND INSTR(',' || :categorias_csv || ',', ',' || oc.id_categoria || ',') > 0
    )
)
AND (
    COALESCE(:subcategorias_csv, '') = '' OR EXISTS (
        SELECT 1
        FROM orcamentos_categorias oc
        WHERE oc.id_orcamento = o.id
          AND (
              INSTR(',' || :subcategorias_csv || ',', ',' || oc.id_subcategoria || ',') > 0
              OR (
                  COALESCE(:categorias_csv, '') <> ''
                  AND INSTR(',' || :categorias_csv || ',', ',' || oc.id_categoria || ',') > 0
                  AND (
                      oc.id_subcategoria IS NULL
                      OR oc.id_subcategoria = ''
                      OR oc.id_subcategoria = '-1'
                  )
              )
          )
    )
)
AND (
    COALESCE(:tags_csv, '') = ''
    OR NOT EXISTS (
        SELECT 1
        FROM orcamentos_tags ot
        WHERE ot.id_orcamento = o.id
    )
    OR (
        COALESCE(o.tipo_logica_tags, 'OR') = 'OR'
        AND EXISTS (
            SELECT 1
            FROM orcamentos_tags ot
            WHERE ot.id_orcamento = o.id
              AND INSTR(',' || :tags_csv || ',', ',' || ot.id_tag || ',') > 0
        )
    )
    OR (
        COALESCE(o.tipo_logica_tags, 'OR') = 'AND'
        AND (
            SELECT COUNT(DISTINCT ot.id_tag)
            FROM orcamentos_tags ot
            WHERE ot.id_orcamento = o.id
              AND INSTR(',' || :tags_csv || ',', ',' || ot.id_tag || ',') > 0
        ) = (
            SELECT COUNT(DISTINCT ot.id_tag)
            FROM orcamentos_tags ot
            WHERE ot.id_orcamento = o.id
        )
    )
    OR (
        COALESCE(o.tipo_logica_tags, 'OR') IN ('NONE', 'XOR')
        AND NOT EXISTS (
            SELECT 1
            FROM orcamentos_tags ot
            WHERE ot.id_orcamento = o.id
              AND INSTR(',' || :tags_csv || ',', ',' || ot.id_tag || ',') > 0
        )
    )
)
AND (
    COALESCE(:cartoes_csv, '') = '' OR EXISTS (
        SELECT 1
        FROM orcamentos_cartoes oct
        WHERE oct.id_orcamento = o.id
          AND INSTR(',' || :cartoes_csv || ',', ',' || oct.id_cartao || ',') > 0
    )
)
-- Ordenação: prioriza quem casa com SUBCATEGORIA, depois CATEGORIA,
-- depois TAG, depois CARTÃO. No fim desempata por data.
ORDER BY
    CASE WHEN (COALESCE(:subcategorias_csv, '') <> '' AND EXISTS (
        SELECT 1
        FROM orcamentos_categorias oc
        WHERE oc.id_orcamento = o.id
          AND INSTR(',' || :subcategorias_csv || ',', ',' || oc.id_subcategoria || ',') > 0
    )) THEN 1 ELSE 0 END DESC,

    CASE WHEN (COALESCE(:categorias_csv, '') <> '' AND EXISTS (
        SELECT 1
        FROM orcamentos_categorias oc
        WHERE oc.id_orcamento = o.id
          AND INSTR(',' || :categorias_csv || ',', ',' || oc.id_categoria || ',') > 0
    )) THEN 1 ELSE 0 END DESC,

    CASE WHEN (COALESCE(:tags_csv, '') <> '' AND (
        (
            COALESCE(o.tipo_logica_tags, 'OR') = 'OR'
            AND EXISTS (
                SELECT 1
                FROM orcamentos_tags ot
                WHERE ot.id_orcamento = o.id
                  AND INSTR(',' || :tags_csv || ',', ',' || ot.id_tag || ',') > 0
            )
        )
        OR (
            COALESCE(o.tipo_logica_tags, 'OR') = 'AND'
            AND (
                SELECT COUNT(DISTINCT ot.id_tag)
                FROM orcamentos_tags ot
                WHERE ot.id_orcamento = o.id
                  AND INSTR(',' || :tags_csv || ',', ',' || ot.id_tag || ',') > 0
            ) = (
                SELECT COUNT(DISTINCT ot.id_tag)
                FROM orcamentos_tags ot
                WHERE ot.id_orcamento = o.id
            )
        )
        OR (
            COALESCE(o.tipo_logica_tags, 'OR') IN ('NONE', 'XOR')
            AND NOT EXISTS (
                SELECT 1
                FROM orcamentos_tags ot
                WHERE ot.id_orcamento = o.id
                  AND INSTR(',' || :tags_csv || ',', ',' || ot.id_tag || ',') > 0
            )
        )
    )) THEN 1 ELSE 0 END DESC,

    CASE WHEN (COALESCE(:cartoes_csv, '') <> '' AND EXISTS (
        SELECT 1
        FROM orcamentos_cartoes oct
        WHERE oct.id_orcamento = o.id
          AND INSTR(',' || :cartoes_csv || ',', ',' || oct.id_cartao || ',') > 0
    )) THEN 1 ELSE 0 END DESC,

    date(COALESCE(o.data_inicial, date('now'))) DESC,
    o.id DESC;
