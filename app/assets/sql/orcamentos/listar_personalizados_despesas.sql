WITH RECURSIVE
orc AS (
  SELECT
    o.*,
    o.data_inicial       AS ini_orc,
    o.data_final         AS fim_orc
  FROM orcamentos o
  WHERE o.tipo = 'DESPESA'
    AND o.data_inicial IS NOT NULL
    AND o.data_final  IS NOT NULL
),
meses_orc(id_orc, mes) AS (
  SELECT o.id, date(o.ini_orc, 'start of month') FROM orc o
  UNION ALL
  SELECT mo.id_orc, date(mo.mes, '+1 month')
  FROM meses_orc mo
  JOIN orc o ON o.id = mo.id_orc
  WHERE mo.mes < date(o.fim_orc, 'start of month')
),
df_vigente AS (
  SELECT
    mo.id_orc,
    d.id AS id_despesa,
    mo.mes AS mes_ref,
    (
      SELECT date(MAX(df.data), 'start of month')
      FROM despesas_fixas df
      WHERE df.id_despesa = d.id
        AND date(df.data, 'start of month') <= date(mo.mes, 'start of month')
    ) AS data_vigente
  FROM despesas d
  JOIN orc o  ON o.id_profile = d.id_profile
  JOIN meses_orc mo ON mo.id_orc = o.id
  WHERE d.recorrencia = 'F'
  AND coalesce(d.ignore_orc, 'N') = 'N'
),
df_valor_mes AS (
  SELECT
    v.id_orc,
    v.mes_ref,
    d.id AS id_despesa,
    dfv.id_conta,
    dfv.dia_venc,
    dfv.status,
    dfv.juros,
    dfv.data_efetivacao,
    dfv.data,
    dfv.cotacao,
    dfv.excluido_mes,
    dfv.attach_id,
    dfv.attach_path,
    dfv.attach_size,
    dfv.id_cartao_credito
  FROM df_vigente v
  JOIN despesas d ON d.id = v.id_despesa
  LEFT JOIN despesas_fixas dfv
    ON dfv.id_despesa = d.id
   AND date(dfv.data,'start of month') = v.data_vigente
),
despesas_periodo AS (
  SELECT
    o.id AS id_orc,
    d.id AS id_despesa,
    mo.mes AS mes_ref,
    d.id_origem,
    d.id_profile,
    cm.id_categoria,
    cm.id_subcategoria,
    d.somar_total,
    COALESCE(dfm.id_cartao_credito, d.id_cartao_credito) as id_card,
    COALESCE(dfm.cotacao, d.cotacao, 1)           AS cotacao,

    CASE WHEN d.recorrencia = 'F'
         THEN IFNULL(dfm.status, 'pd')
         ELSE d.status END                        AS status_mes,

    COALESCE(dfm.juros, d.juros, 0)               AS juros_mes,

    {param_data_ref} AS dt,

    COALESCE(contas.somar_total,'S')               AS conta_somar_total,
    cm.valor                                       AS valor_cat,
    IFNULL(dfm.excluido_mes, 'N')                  AS excluido_mes
  FROM orc o
  JOIN meses_orc mo ON mo.id_orc = o.id
  JOIN despesas d   ON d.id_profile = o.id_profile
  INNER JOIN despesas_cat_valor cm
    ON cm.id_despesa = d.id
   AND (
         d.recorrencia != 'F'
         OR (
           date(cm.data) = date(COALESCE(
             (SELECT MAX(dcv.data)
              FROM despesas_cat_valor dcv
              WHERE dcv.id_despesa       = cm.id_despesa
                AND dcv.id_categoria     = cm.id_categoria
                AND dcv.id_subcategoria  = cm.id_subcategoria
                AND LOWER(COALESCE(dcv.obs, '')) = LOWER(COALESCE(cm.obs,''))
                AND date(dcv.data) <= date(mo.mes, 'start of month')),
             /* Antes do primeiro vencimento, usa somente o mapeamento
                inicial e nao antecipa categorias cadastradas no futuro. */
             CASE WHEN :iniciar_fixa_no_lancamento = 'S' THEN
               (SELECT MIN(dcv_inicio.data)
                FROM despesas_cat_valor dcv_inicio
                WHERE dcv_inicio.id_despesa = cm.id_despesa)
             END))
           AND cm.excluido != 'S'
         )
       )
  LEFT JOIN df_valor_mes dfm
    ON dfm.id_despesa = d.id
   AND dfm.mes_ref    = mo.mes
   AND dfm.id_orc     = o.id
  LEFT JOIN contas
    ON contas.id = COALESCE(dfm.id_conta, d.id_conta)
 WHERE
    coalesce(d.ignore_orc, 'N') = 'N'
    AND (
      /* FIXAS- uma instância por mês a partir do mês de origem */
      /* Com referencia por lancamento, a fixa sempre comeca em
         data_cadastro; outras referencias preservam o vencimento. */
      (d.recorrencia != 'F' OR date(
        CASE WHEN :iniciar_fixa_no_lancamento = 'S'
          THEN COALESCE(d.data_cadastro, d.data)
          ELSE d.data
        END, 'start of month') <= date(dt, 'start of month'))
      /* NÃO‑FIXAS- mês real dentro do intervalo do orçamento (sem replicar) */
      AND date(dt) BETWEEN date(o.data_inicial) AND date(o.data_final)
      AND (d.recorrencia = 'F' OR strftime('%Y-%m', dt) = strftime('%Y-%m', mo.mes))
    )
    AND (d.recorrencia <> 'F' OR IFNULL(dfm.excluido_mes, 'N') = 'N')
    AND (d.data_exclusao IS NULL OR datetime(strftime('%Y-%m-01',mo.mes)) <=
                                      datetime(strftime('%Y-%m-01', d.data_exclusao)))
),
despesas_calc AS (
  SELECT
    id_orc,
    id_despesa,
    mes_ref,
    id_origem,
    id_profile,
    id_categoria,
    id_subcategoria,
    somar_total,
    cotacao,
    conta_somar_total,
    valor_cat,
    id_card,
    CASE WHEN status_mes = 'pg' THEN valor_cat  ELSE 0 END  AS efet,
    CASE WHEN status_mes = 'pd' THEN valor_cat  ELSE 0 END  AS pend,
    CASE WHEN status_mes = 'pg' THEN juros_mes  ELSE 0 END  AS juros_efet,
    CASE WHEN status_mes = 'pd' THEN juros_mes  ELSE 0 END  AS juros_pend,
    dt
  FROM despesas_periodo
),
/* O rateio multiplica as linhas, não os encargos/descontos. Agrupa depois
   dos filtros, por despesa e mês, preservando cada ocorrência da fixa. */
calc_por_ocorrencia AS (
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
  COALESCE(SUM(d.efet * d.cotacao), 0)
    + COALESCE(MAX(d.juros_efet * d.cotacao), 0) AS efet,
  COALESCE(SUM(d.pend * d.cotacao), 0)
    + COALESCE(MAX(d.juros_pend * d.cotacao), 0) AS pend,
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
LEFT JOIN despesas_calc d
  ON d.id_profile = orcamentos.id_profile
 AND d.id_orc     = orcamentos.id
 AND (
   COALESCE(orcamentos.nao_somadas, 'S') = 'S'
   OR (COALESCE(d.somar_total, 'S') = 'S' AND d.conta_somar_total = 'S')
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
       WHERE tt.id_transacao = d.id_origem
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
         WHERE tt.id_transacao = d.id_origem
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
         WHERE tt.id_transacao = d.id_origem
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
           (oc.id_categoria = d.id_categoria AND COALESCE(oc.id_subcategoria,'-1') = '-1')
           OR
           (oc.id_categoria = d.id_categoria AND oc.id_subcategoria = d.id_subcategoria)
         )
     )
   )
   /* ===== CARTÕES ===== */
   AND (
     NOT EXISTS (
       SELECT 1 FROM orcamentos_cartoes oc
       WHERE oc.id_orcamento = orcamentos.id
     )
     OR EXISTS (
       SELECT 1
       FROM orcamentos_cartoes oc
       WHERE oc.id_orcamento = orcamentos.id AND oc.id_cartao = d.id_card
     )
   )
 )

WHERE
  (orcamentos.data_exclusao IS NULL OR date(orcamentos.data_inicial) <= date(orcamentos.data_exclusao))
  AND orcamentos.data_inicial IS NOT NULL
  AND orcamentos.data_final   IS NOT NULL
  AND (:somente_resumo <> 'S' OR
  (COALESCE(orcamentos.exibir_resumo,'N') = 'S'
  AND date(:datainicio) BETWEEN date(orcamentos.data_inicial, 'start of month')
  AND date(orcamentos.data_final,'start of month','+1 month','-1 day')))
  {params}
GROUP BY orcamentos.id, d.id_despesa, d.mes_ref
)
SELECT
  id_orc, id_profile, notify_over, orc_data_criacao, orc_data_inicial,
  orc_data_final, data_exclusao, nao_somadas, saldo_previsto, tipo_logica_tags,
  id_orcamento_receita_referencia, orc_meta, tipo, perc_alerta, perc_receitas,
  descricao_orcamento_receita_referencia, descricao, orc_cor, orc_icon,
  orc_exibir_resumo, orc_somar, orc_data,
  SUM(efet) AS efet, SUM(pend) AS pend, pai, filho
FROM calc_por_ocorrencia
GROUP BY id_orc
ORDER BY descricao, orc_data_final
