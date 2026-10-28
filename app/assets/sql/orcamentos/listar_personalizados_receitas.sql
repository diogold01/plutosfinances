WITH RECURSIVE
orc AS (
  SELECT
    o.*,
    o.data_inicial       AS ini_orc,
    o.data_final         AS fim_orc
  FROM orcamentos o
  WHERE o.tipo = 'RECEITA'
    AND o.data_inicial IS NOT NULL
    AND o.data_final   IS NOT NULL
),
meses_orc(id_orc, mes) AS (
  SELECT o.id, date(o.ini_orc, 'start of month') FROM orc o
  UNION ALL
  SELECT mo.id_orc, date(mo.mes, '+1 month')
  FROM meses_orc mo
  JOIN orc o ON o.id = mo.id_orc
  WHERE mo.mes < date(o.fim_orc, 'start of month')
),

rf_vigente AS (
  SELECT
    mo.id_orc,
    r.id     AS id_receita,
    mo.mes   AS mes_ref,
    (
      SELECT date(MAX(rf.data), 'start of month')
      FROM receitas_fixas rf
      WHERE rf.id_receita = r.id
        AND date(rf.data,'start of month') <= date(mo.mes,'start of month')
    ) AS data_vigente
  FROM receitas r
  JOIN orc o      ON o.id_profile = r.id_profile
  JOIN meses_orc mo ON mo.id_orc  = o.id
  WHERE r.recorrencia = 'M'
  AND coalesce(r.ignore_orc, 'N') = 'N'
),
rf_valor_mes AS (
  SELECT
    v.id_orc,
    v.mes_ref,
    r.id AS id_receita,
    rfv.id_conta,
    rfv.dia_venc,
    rfv.efetivado,
    rfv.data_efetivacao,
    rfv.data,
    rfv.valor,
    rfv.cotacao,
    rfv.excluido_mes,
    rfv.attach_id,
    rfv.attach_path,
    rfv.attach_size
  FROM rf_vigente v
  JOIN receitas r ON r.id = v.id_receita
  LEFT JOIN receitas_fixas rfv
    ON rfv.id_receita = r.id
   AND date(rfv.data,'start of month') = v.data_vigente
),

/* Expansão no período- fixas mês a mês; não-fixas apenas no mês real.
   Derivamos o status_mes a partir de 'efetivado' (S/N) como na consulta antiga. */
receitas_periodo AS (
  SELECT
    o.id AS id_orc,
    r.id_origem,
    r.id_profile,
    /* receitas não são multicategoria- pegamos direto da própria receita */
    COALESCE(r.id_categoria,   '-1') AS id_categoria,
    COALESCE(r.id_subcategoria,'-1') AS id_subcategoria,
    r.somar_total,
    COALESCE(rfm.cotacao, r.cotacao, 1)            AS cotacao,

    CASE
      WHEN r.recorrencia = 'M' THEN
        /* fixa- usa efetivado da linha vigente em receitas_fixas */
        CASE WHEN COALESCE(rfm.efetivado, 'N') = 'S' THEN 'pg' ELSE 'pd' END
      ELSE
        /* não-fixa- usa efetivado da própria receita */
        CASE WHEN COALESCE(r.efetivado, 'N') = 'S' THEN 'pg' ELSE 'pd' END
    END AS status_mes,
    {param_data_ref} AS dt,
    COALESCE(contas.somar_total,'S')               AS conta_somar_total,

    /* Valor base da receita (sem multicategoria)- linha vigente da fixa OU valor da receita */
    COALESCE(rfm.valor, r.valor)                   AS valor_base,

    IFNULL(rfm.excluido_mes, 'N')                  AS excluido_mes
  FROM orc o
  JOIN meses_orc mo ON mo.id_orc = o.id
  JOIN receitas r   ON r.id_profile = o.id_profile
  LEFT JOIN rf_valor_mes rfm
    ON rfm.id_receita = r.id
   AND rfm.mes_ref    = mo.mes
   AND rfm.id_orc     = o.id
  LEFT JOIN contas
    ON contas.id = COALESCE(rfm.id_conta, r.id_conta)
  WHERE
    coalesce(r.ignore_orc, 'N') = 'N'
    AND (
      /* FIXAS- uma instância por mês a partir do mês de origem */
      (r.recorrencia != 'M' OR date(r.data, 'start of month') <= date(dt, 'start of month'))
      /* NÃO‑FIXAS- mês real dentro do intervalo do orçamento (sem replicar) */
      AND date(dt) BETWEEN date(o.data_inicial) AND date(o.data_final)
      AND (r.recorrencia = 'M' OR strftime('%Y-%m', dt) = strftime('%Y-%m', mo.mes))
    )
    AND (r.recorrencia <> 'M' OR IFNULL(rfm.excluido_mes, 'N') = 'N')
    AND (r.data_exclusao IS NULL OR datetime(strftime('%Y-%m-01',mo.mes)) <=
                                      datetime(strftime('%Y-%m-01', r.data_exclusao)))
),

/* Aplica status ao valor (efet/pend), mantendo cotação p/ etapa seguinte */
receitas_calc AS (
  SELECT
    id_orc,
    id_origem,
    id_profile,
    id_categoria,
    id_subcategoria,
    somar_total,
    cotacao,
    conta_somar_total,
    valor_base,
    CASE WHEN status_mes = 'pg' THEN valor_base ELSE 0 END AS efet,
    CASE WHEN status_mes = 'pd' THEN valor_base ELSE 0 END AS pend,
    dt
  FROM receitas_periodo
)

SELECT
  orcamentos.id                                           AS id_orc,
  orcamentos.id_profile                                   AS id_profile,
  COALESCE(orcamentos.notify_over, 'N')                   AS notify_over,
  orcamentos.data_criacao                                 AS orc_data_criacao,
  orcamentos.data_inicial                                 AS orc_data_inicial,
  orcamentos.data_final                                   AS orc_data_final,
  orcamentos.data_exclusao                                AS data_exclusao,
  COALESCE(orcamentos.nao_somadas, 'S')                   AS nao_somadas,
  coalesce(orcamentos.saldo_previsto, 'N')                as saldo_previsto,
  coalesce(orcamentos.tipo_logica_tags, 'OR')             as tipo_logica_tags,
  null                                                    AS id_orcamento_receita_referencia,
  COALESCE(om.meta, orcamentos.meta)                      AS orc_meta,
  orcamentos.tipo                                         AS tipo,
  COALESCE(orcamentos.perc_alerta, 80)                    AS perc_alerta,
  0                                                       AS perc_receitas,
  null                                                    AS descricao_orcamento_receita_referencia,
  orcamentos.descricao                                    AS descricao,
  COALESCE(orcamentos.cor, 0)                             AS orc_cor,
  COALESCE(orcamentos.icon_id, 955)                       AS orc_icon,
  COALESCE(orcamentos.exibir_resumo, 'N')                 AS orc_exibir_resumo,
  COALESCE(orcamentos.somar, 'S')                         AS orc_somar,
  om.data                                                 AS orc_data,
  COALESCE(SUM( r.efet * r.cotacao ), 0)                  AS efet,
  COALESCE(SUM( r.pend * r.cotacao ), 0)                  AS pend,
  'N' AS pai,
  'N' AS filho
FROM orc orcamentos
LEFT JOIN orcamentos_mensal om
  ON om.id_orcamento = orcamentos.id
 AND date(om.data, 'start of month') = (
       SELECT date(MAX(orcamentos_mensal.data), 'start of month')
       FROM orcamentos_mensal
       WHERE id_orcamento = orcamentos.id
         AND date(orcamentos_mensal.data, 'start of month') <= date(orcamentos.data_inicial, 'start of month')
     )
LEFT JOIN receitas_calc r
  ON r.id_profile = orcamentos.id_profile
 AND r.id_orc     = orcamentos.id
 AND (
   COALESCE(orcamentos.nao_somadas, 'S') = 'S'
   OR (COALESCE(r.somar_total, 'S') = 'S' AND r.conta_somar_total = 'S')
 )
  AND (
/* ===== TAGS ===== */
(
  NOT EXISTS (
    SELECT 1 FROM orcamentos_tags ot
    WHERE ot.id_orcamento = orcamentos.id
  )
  OR (coalesce(orcamentos.tipo_logica_tags, 'OR') = 'OR' AND EXISTS (
    SELECT 1
    FROM tags_transacoes tt
    WHERE tt.id_transacao = r.id_origem
      AND EXISTS (
        SELECT 1
        FROM orcamentos_tags ot
        WHERE ot.id_orcamento = orcamentos.id
          AND ot.id_tag = tt.id_tag
      )
  ))
  OR (coalesce(orcamentos.tipo_logica_tags, 'OR') = 'AND'
    AND (
      SELECT COUNT(DISTINCT tt.id_tag)
      FROM tags_transacoes tt
      WHERE tt.id_transacao = r.id_origem
        AND EXISTS (
          SELECT 1
          FROM orcamentos_tags ot
          WHERE ot.id_orcamento = orcamentos.id
            AND ot.id_tag = tt.id_tag
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
      WHERE tt.id_transacao = r.id_origem
        AND EXISTS (
          SELECT 1
          FROM orcamentos_tags ot
          WHERE ot.id_orcamento = orcamentos.id
            AND ot.id_tag = tt.id_tag
        )
    )
  )
)
/* ===== CATEGORIAS ===== */
AND (
  NOT EXISTS (
    SELECT 1 FROM orcamentos_categorias oc
    WHERE oc.id_orcamento = orcamentos.id
  )
  OR EXISTS (
    SELECT 1
    FROM orcamentos_categorias oc
    WHERE oc.id_orcamento = orcamentos.id
      AND (
        (oc.id_categoria = r.id_categoria AND COALESCE(oc.id_subcategoria,'-1') = '-1')
        OR
        (oc.id_categoria = r.id_categoria AND oc.id_subcategoria = r.id_subcategoria)
      )
  )
)
  )
WHERE
  (orcamentos.data_exclusao IS NULL OR date(orcamentos.data_inicial) <= date(orcamentos.data_exclusao))
  AND orcamentos.data_inicial IS NOT NULL
  AND orcamentos.data_final   IS NOT NULL
  AND (:somente_resumo <> 'S' OR COALESCE(orcamentos.exibir_resumo,'N')='S')
  {params}
GROUP BY orcamentos.id
ORDER BY orcamentos.descricao, orcamentos.data_final
