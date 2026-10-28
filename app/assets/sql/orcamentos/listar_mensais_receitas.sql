WITH
/* Quem é pai/filho na relação */
parents AS (
  SELECT DISTINCT id_pai AS id FROM orcamentos_agrupamento
),
children AS (
  SELECT DISTINCT id_filho AS id FROM orcamentos_agrupamento
),

/* 1) Cálculo por orçamento (base RECEITAS, igual à sua query) */
calc AS (
  SELECT
           orcamentos.id                                    as id_orc,
           orcamentos.id_profile                            as id_profile,
           coalesce(orcamentos.notify_over, 'N')            as notify_over,
           coalesce(orcamentos.data_criacao, :datainicio)   as orc_data_criacao,
           orcamentos.data_exclusao                         as data_exclusao,
           coalesce(orcamentos.nao_somadas, 'S')            as nao_somadas,
           coalesce(orcamentos.saldo_previsto, 'N')         as saldo_previsto,
           null                                             as id_orcamento_receita_referencia,
           coalesce(orc_meta.meta, orcamentos.meta)         as orc_meta_val,
           orcamentos.tipo                                  as tipo,
           orcamentos.data_inicial                          as orc_data_inicial,
           orcamentos.data_final                            as orc_data_final,
           coalesce(orcamentos.perc_alerta, 80)             as perc_alerta,
           0                                                as perc_receitas,
           null                                             as descricao_orcamento_receita_referencia,
           descricao                                        as descricao,
           coalesce(cor, 0)                                 as orc_cor,
           COALESCE(icon_id, 955)                           as orc_icon,
           coalesce(orcamentos.exibir_resumo, 'N') 		    as orc_exibir_resumo,
           coalesce(orc_meta.data, :datainicio)             as orc_data,

           coalesce(SUM(receitas.efet * cotacao),0)         as efet,
           coalesce(SUM(receitas.pend * cotacao),0)         as pend
     FROM
        orcamentos
        left join orcamentos_mensal as orc_meta
          on orcamentos.id = orc_meta.id_orcamento
         and date(orc_meta.data, 'start of month') = (
              select date(max(orcamentos_mensal.data),'start of month')
              from orcamentos_mensal
              where id_orcamento = orcamentos.id
                and date(orcamentos_mensal.data, 'start of month') <= date(:datainicio, 'start of month')
         )
        left join (
          SELECT
              receitas.id_origem,
              receitas.id_profile,
              COALESCE(receitas.id_categoria, '-1')     as id_categoria,
              COALESCE(receitas.id_subcategoria, '-1')  as id_subcategoria,
              receitas.somar_total,
              (CASE WHEN (CASE WHEN receitas.recorrencia != 'M' THEN receitas.efetivado
                               ELSE COALESCE(receitas_fixas.efetivado,'N') END) = 'N'
                    THEN 0
                    ELSE COALESCE(receitas_fixas_valor.valor, receitas.valor) END) as efet,
              (CASE WHEN (CASE WHEN receitas.recorrencia != 'M' THEN receitas.efetivado
                               ELSE COALESCE(receitas_fixas.efetivado,'N') END) = 'S'
                    THEN 0
                    ELSE COALESCE(receitas_fixas_valor.valor, receitas.valor) END) as pend,
              COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
              {param_data_ref} as dt,
              COALESCE(contas.somar_total,'S') as conta_somar_total
          FROM receitas
          LEFT JOIN receitas_fixas
                 ON receitas.id = receitas_fixas.id_receita
                AND date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
          LEFT JOIN receitas_fixas AS receitas_fixas_valor
                 ON receitas_fixas_valor.id_receita = receitas.id
                AND date(receitas_fixas_valor.data, 'start of month') = (
                      select date(max(receitas_fixas.data),'start of month')
                      from receitas_fixas
                      where id_receita = receitas.id
                        and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month')
                )
          LEFT JOIN contas ON contas.id = COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta)
          WHERE
              COALESCE(receitas_fixas.excluido_mes,'N') = 'N'
              AND coalesce(receitas.ignore_orc, 'N') = 'N'
          AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
          AND date(dt) BETWEEN date(strftime('%Y-%m-01',:datainicio))
                           AND date(:datainicio,'start of month','+1 month','-1 day')
          AND (receitas.data_exclusao IS NULL OR
               datetime(strftime('%Y-%m-01',:datainicio)) <= datetime(strftime('%Y-%m-01', receitas.data_exclusao)))
        ) as receitas
          ON receitas.id_profile = orcamentos.id_profile
         AND (coalesce(orcamentos.nao_somadas, 'S') = 'S'
              OR (coalesce(receitas.somar_total, 'S') = 'S' AND conta_somar_total = 'S'))
         AND (
            /* ===== TAGS ===== */
            (
              NOT EXISTS (SELECT 1 FROM orcamentos_tags ot WHERE ot.id_orcamento = orcamentos.id)
              OR (coalesce(orcamentos.tipo_logica_tags, 'OR') = 'OR' AND EXISTS (
                SELECT 1
                FROM tags_transacoes tt
                WHERE tt.id_transacao = receitas.id_origem
                  AND EXISTS (
                    SELECT 1 FROM orcamentos_tags ot
                    WHERE ot.id_orcamento = orcamentos.id AND ot.id_tag = tt.id_tag
                  )
              ))
              OR (coalesce(orcamentos.tipo_logica_tags, 'OR') = 'AND'
                AND (
                  SELECT COUNT(DISTINCT tt.id_tag)
                  FROM tags_transacoes tt
                  WHERE tt.id_transacao = receitas.id_origem
                    AND EXISTS (
                      SELECT 1 FROM orcamentos_tags ot
                      WHERE ot.id_orcamento = orcamentos.id AND ot.id_tag = tt.id_tag
                    )
                ) = (
                  SELECT COUNT(DISTINCT ot.id_tag)
                  FROM orcamentos_tags ot
                  WHERE ot.id_orcamento = orcamentos.id
                )
              )
              OR (coalesce(orcamentos.tipo_logica_tags, 'OR') IN ('NONE','XOR')
                AND NOT EXISTS (
                  SELECT 1
                  FROM tags_transacoes tt
                  WHERE tt.id_transacao = receitas.id_origem
                    AND EXISTS (
                      SELECT 1 FROM orcamentos_tags ot
                      WHERE ot.id_orcamento = orcamentos.id AND ot.id_tag = tt.id_tag
                    )
                )
              )
            )

            /* ===== CATEGORIAS ===== */
            AND (
              NOT EXISTS (SELECT 1 FROM orcamentos_categorias oc WHERE oc.id_orcamento = orcamentos.id)
              OR EXISTS (
                SELECT 1
                FROM orcamentos_categorias oc
                WHERE oc.id_orcamento = orcamentos.id
                  AND (
                    (oc.id_categoria = receitas.id_categoria AND COALESCE(oc.id_subcategoria,'-1') = '-1')
                    OR
                    (oc.id_categoria = receitas.id_categoria AND oc.id_subcategoria = receitas.id_subcategoria)
                  )
              )
            )
         )

    WHERE
        orcamentos.tipo = 'RECEITA'
    AND (orcamentos.data_exclusao IS NULL OR date(:datainicio) <= date(orcamentos.data_exclusao))
    AND date(:datainicio) >= date(coalesce(orcamentos.data_criacao, :datainicio))
    AND orcamentos.data_inicial IS NULL
    AND orcamentos.data_final  IS NULL
    {params_calc}
  GROUP BY orcamentos.id
),

/* 2) Normalização (filhos somam no pai, pais zerados) */
norm AS (
  SELECT
    c.*,
    COALESCE(rel.id_pai, c.id_orc) AS display_id,
    CASE WHEN p.id IS NOT NULL THEN 0 ELSE c.orc_meta_val END AS orc_meta_norm,
    CASE WHEN p.id IS NOT NULL THEN 0 ELSE c.efet        END AS efet_norm,
    CASE WHEN p.id IS NOT NULL THEN 0 ELSE c.pend        END AS pend_norm
  FROM calc c
  LEFT JOIN orcamentos_agrupamento rel
         ON rel.id_filho = c.id_orc
  LEFT JOIN parents p
         ON p.id = c.id_orc
),

/* 3) Agregação por display_id (pais recebem soma dos filhos; avulsos mantêm valores) */
agg AS (
  SELECT
    display_id                 AS id_orc,
    SUM(orc_meta_norm)         AS orc_meta,
    SUM(efet_norm)             AS efet,
    SUM(pend_norm)             AS pend,
    MIN(orc_data)              AS orc_data
  FROM norm
  GROUP BY display_id
),

/* 4) Filhos individuais (usado quando mostrar_filhos = 'S') */
children_rows AS (
  SELECT
    n.id_orc,
    n.id_profile,
    n.notify_over,
    n.orc_data_criacao,
    n.data_exclusao,
    n.nao_somadas,
    n.saldo_previsto,
    n.orc_meta_val     AS orc_meta,   -- meta do próprio filho
    n.tipo,
    n.orc_data_inicial,
    n.orc_data_final,
    n.perc_alerta,
    n.perc_receitas,
    n.descricao,
    n.orc_cor,
    n.orc_icon,
    n.orc_exibir_resumo,
    n.orc_data,
    n.efet,
    n.pend
  FROM norm n
  WHERE EXISTS (SELECT 1 FROM children ch WHERE ch.id = n.id_orc)
)

/* 5) Resultado final top-level (+ filhos, se parametrizado), com flags pai/filho */
SELECT
   orcamentos.id                                   AS id_orc,
   orcamentos.id_profile                           AS id_profile,
   COALESCE(orcamentos.notify_over, 'N')           AS notify_over,
   COALESCE(orcamentos.data_criacao, :datainicio)  AS orc_data_criacao,
   orcamentos.data_exclusao                        AS data_exclusao,
   COALESCE(orcamentos.nao_somadas, 'S')           AS nao_somadas,
   COALESCE(orcamentos.saldo_previsto, 'N')        AS saldo_previsto,
   COALESCE(orcamentos.tipo_logica_tags, 'OR')     AS tipo_logica_tags,
   null                                            AS id_orcamento_receita_referencia,
   a.orc_meta                                      AS orc_meta,          -- soma filhos (ou próprio, se avulso)
   orcamentos.tipo                                 AS tipo,
   orcamentos.data_inicial                         AS orc_data_inicial,
   orcamentos.data_final                           AS orc_data_final,
   COALESCE(orcamentos.perc_alerta, 80)            AS perc_alerta,
   COALESCE(orcamentos.perc_receitas, 0)           AS perc_receitas,
   null                                            AS descricao_orcamento_receita_referencia,
   orcamentos.descricao                            AS descricao,
   COALESCE(orcamentos.cor, 0)                     AS orc_cor,
   COALESCE(orcamentos.icon_id, 955)               AS orc_icon,
   COALESCE(orcamentos.exibir_resumo, 'N')         AS orc_exibir_resumo,
   COALESCE(orcamentos.somar, 'S')                 AS orc_somar,
   a.orc_data                                      AS orc_data,
   a.efet,
   a.pend,
   CASE WHEN EXISTS (SELECT 1 FROM parents p2  WHERE p2.id  = orcamentos.id) THEN 'S' ELSE 'N' END AS pai,
   CASE WHEN EXISTS (SELECT 1 FROM children c2 WHERE c2.id = orcamentos.id) THEN 'S' ELSE 'N' END AS filho
FROM orcamentos
JOIN agg a
  ON a.id_orc = orcamentos.id
WHERE
  /* Avulsos não têm relação de agrupamento; pais agregados respeitam mostrar_pais.
     Isso evita duplicar o resumo previsto com pai agregado + filhos individuais. */
  ((:mostrar_pais = 'S'  AND EXISTS (SELECT 1 FROM parents  p WHERE p.id = orcamentos.id))
   OR
   (NOT EXISTS (SELECT 1 FROM children c WHERE c.id = orcamentos.id)
    AND NOT EXISTS (SELECT 1 FROM parents p WHERE p.id = orcamentos.id)))
  AND (:somente_resumo <> 'S' OR COALESCE(orcamentos.exibir_resumo,'N')='S')
  {params}

UNION ALL

SELECT
   orcamentos.id                                   AS id_orc,
   orcamentos.id_profile                           AS id_profile,
   COALESCE(orcamentos.notify_over, 'N')           AS notify_over,
   COALESCE(orcamentos.data_criacao, :datainicio)  AS orc_data_criacao,
   orcamentos.data_exclusao                        AS data_exclusao,
   COALESCE(orcamentos.nao_somadas, 'S')           AS nao_somadas,
   COALESCE(orcamentos.saldo_previsto, 'N')        AS saldo_previsto,
   COALESCE(orcamentos.tipo_logica_tags, 'OR')     AS tipo_logica_tags,
   null                                            AS id_orcamento_receita_referencia,
   cr.orc_meta                                     AS orc_meta,          -- meta do próprio filho
   orcamentos.tipo                                 AS tipo,
   orcamentos.data_inicial                         AS orc_data_inicial,
   orcamentos.data_final                           AS orc_data_final,
   COALESCE(orcamentos.perc_alerta, 80)            AS perc_alerta,
   COALESCE(orcamentos.perc_receitas, 0)           AS perc_receitas,
   null                                            AS descricao_orcamento_receita_referencia,
   orcamentos.descricao                            AS descricao,
   COALESCE(orcamentos.cor, 0)                     AS orc_cor,
   COALESCE(orcamentos.icon_id, 955)               AS orc_icon,
   COALESCE(orcamentos.exibir_resumo, 'N')         AS orc_exibir_resumo,
   COALESCE(orcamentos.somar, 'S')                 AS orc_somar,
   cr.orc_data                                     AS orc_data,
   cr.efet,
   cr.pend,
   'N' AS pai,
   'S' AS filho
FROM children_rows cr
JOIN orcamentos ON orcamentos.id = cr.id_orc
WHERE
  (:mostrar_filhos = 'S')
  AND (:somente_resumo <> 'S' OR COALESCE(orcamentos.exibir_resumo,'N')='S')
  {params}

ORDER BY descricao;
