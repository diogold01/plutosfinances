WITH
/* Quem é pai/filho na relação */
parents AS (
  SELECT DISTINCT id_pai AS id FROM orcamentos_agrupamento
),
children AS (
  SELECT DISTINCT id_filho AS id FROM orcamentos_agrupamento
),

/* O rateio multiplica as linhas, não os encargos/descontos. Agrupa depois
   dos filtros para aplicar o valor assinado uma vez por despesa elegível. */
calc_por_ocorrencia AS (
  SELECT
           orcamentos.id                                    as id_orc,
           orcamentos.id_profile                            as id_profile,
           coalesce(orcamentos.notify_over, 'N')            as notify_over,
           coalesce(orcamentos.data_criacao, :datainicio)   as orc_data_criacao,
           orcamentos.data_exclusao                         as data_exclusao,
           coalesce(orcamentos.nao_somadas, 'S')            as nao_somadas,
           coalesce(orcamentos.saldo_previsto, 'N')         as saldo_previsto,
           coalesce(orc_meta.id_orcamento_receita_referencia, orcamentos.id_orcamento_receita_referencia)
                                                             as id_orcamento_receita_referencia,
           CASE
           WHEN coalesce(orc_meta.perc_receitas, orcamentos.perc_receitas, 0) > 0
           THEN (:valor_receitas * coalesce(orc_meta.perc_receitas, orcamentos.perc_receitas, 0)) / 100.0
           ELSE COALESCE(orc_meta.meta, orcamentos.meta)
           END                                              AS orc_meta_val,
           orcamentos.tipo                                  as tipo,
           orcamentos.data_inicial                          as orc_data_inicial,
           orcamentos.data_final                            as orc_data_final,
           coalesce(orcamentos.perc_alerta, 80)             as perc_alerta,
           coalesce(orc_meta.perc_receitas, orcamentos.perc_receitas, 0) as perc_receitas,
           (SELECT descricao
              FROM orcamentos AS orc_receita_ref
             WHERE orc_receita_ref.id = coalesce(orc_meta.id_orcamento_receita_referencia, orcamentos.id_orcamento_receita_referencia))
                                                             as descricao_orcamento_receita_referencia,
           descricao                                        as descricao,
           coalesce(cor, 0)                                 as orc_cor,
           COALESCE(icon_id, 955)                           as orc_icon,
           coalesce(orcamentos.exibir_resumo, 'N') 		    as orc_exibir_resumo,
           COALESCE(orcamentos.somar, 'S')                  AS orc_somar,
           coalesce(orc_meta.data, :datainicio)             as orc_data,

           coalesce(SUM(despesas.efet * cotacao),0)
             + coalesce(MAX(juros_efet * cotacao),0) as efet,
           coalesce(SUM(despesas.pend * cotacao),0)
             + coalesce(MAX(juros_pend * cotacao),0) as pend
     FROM
        orcamentos
        left join orcamentos_mensal as orc_meta on orcamentos.id = orc_meta.id_orcamento
        and date(orc_meta.data, 'start of month') = (select date(max(orcamentos_mensal.data),'start of month') from orcamentos_mensal where id_orcamento = orcamentos.id
        and date(orcamentos_mensal.data, 'start of month') <= date(:datainicio, 'start of month'))

        left join (SELECT
             despesas.id as id_despesa,
             despesas.id_origem,
             despesas.id_profile,
            catmap.id_categoria,
            catmap.id_subcategoria,
            despesas.somar_total,
           COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as id_card,
           COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1) as cotacao,
            (CASE  WHEN (case when recorrencia = 'F' and despesas_fixas.status is null
               then 'pd' when  recorrencia = 'F' and despesas_fixas.status is not null
               then despesas_fixas.status when   recorrencia != 'F' then despesas.status end) = 'pg' then
                    catmap.valor
                    else 0 end) as efet,
            (CASE  WHEN (case when recorrencia = 'F' and despesas_fixas.status is null
             		   then 'pd' when  recorrencia = 'F' and despesas_fixas.status is not null
             		   then despesas_fixas.status when   recorrencia != 'F' then despesas.status end) = 'pd' then
                    catmap.valor
                    else 0 end) as pend,

            (CASE  WHEN (case when recorrencia = 'F' and despesas_fixas.status is null
               then 'pd' when  recorrencia = 'F' and despesas_fixas.status is not null
               then despesas_fixas.status when   recorrencia != 'F' then despesas.status end) = 'pg' then
           COALESCE(despesas_fixas.juros, despesas.juros, 0)
            else 0 end) as juros_efet,

            (CASE  WHEN (case when recorrencia = 'F' and despesas_fixas.status is null
            then 'pd' when  recorrencia = 'F' and despesas_fixas.status is not null
            then despesas_fixas.status when   recorrencia != 'F' then despesas.status end) = 'pd' then
            COALESCE(despesas_fixas.juros, despesas.juros, 0)
            else 0 end) as juros_pend,
             {param_data_ref} as dt,
             COALESCE(contas.somar_total,'S') as conta_somar_total
             FROM despesas
             inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
                 AND (despesas.recorrencia != 'F' OR
                (date(catmap.data)  = date(COALESCE(
                 (SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                  AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(coalesce(obs, '')) = LOWER(coalesce(catmap.obs,''))
                  AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')),
                 /* Antes do primeiro vencimento, usa somente o mapeamento
                    inicial e nao antecipa categorias cadastradas no futuro. */
                 CASE WHEN :iniciar_fixa_no_lancamento = 'S' THEN
                  (SELECT MIN(dcv_inicio.data) FROM despesas_cat_valor dcv_inicio
                   WHERE dcv_inicio.id_despesa = catmap.id_despesa)
                 END))
                 AND catmap.excluido != 'S'))
             left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(coalesce(despesas_fixas.data, despesas.data), 'start of month') = date(:datainicio, 'start of month')
             left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
             and date(despesas_fixas_valor.data, 'start of month') = (select date(max(despesas_fixas.data),'start of month')
                  from despesas_fixas
                  where id_despesa = despesas.id
                  and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
           left join contas on contas.id = COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta)
            WHERE
            /* Com referencia por lancamento, a fixa sempre comeca em
               data_cadastro; outras referencias preservam o vencimento. */
            (despesas.recorrencia != 'F' OR date(
              CASE WHEN :iniciar_fixa_no_lancamento = 'S'
                THEN COALESCE(despesas.data_cadastro, despesas.data)
                ELSE despesas.data
              END, 'start of month') <= date(dt, 'start of month'))
            AND coalesce(despesas_fixas.excluido_mes,'N') = 'N'
            AND coalesce(despesas.ignore_orc, 'N') = 'N'
            AND (despesas.data_exclusao IS NULL OR
                                      datetime(strftime('%Y-%m-01',:datainicio)) <=
                                      datetime(strftime('%Y-%m-01', despesas.data_exclusao)))
            AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
            AND date(:datainicio,'start of month','+1 month','-1 day'))
            as despesas ON despesas.id_profile = orcamentos.id_profile
            AND (coalesce(orcamentos.nao_somadas, 'S') = 'S' OR (coalesce(despesas.somar_total, 'S') = 'S')  AND conta_somar_total = 'S')
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
                  WHERE tt.id_transacao = despesas.id_origem
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
                    WHERE tt.id_transacao = despesas.id_origem
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
                    WHERE tt.id_transacao = despesas.id_origem
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
                      (oc.id_categoria = despesas.id_categoria AND COALESCE(oc.id_subcategoria,'-1') = '-1')
                      OR
                      (oc.id_categoria = despesas.id_categoria AND oc.id_subcategoria = despesas.id_subcategoria)
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
                  WHERE oc.id_orcamento = orcamentos.id AND oc.id_cartao = id_card
                )
              )
            )

    WHERE
        orcamentos.tipo = 'DESPESA'
        AND (orcamentos.data_exclusao IS NULL OR date(:datainicio) <= date(orcamentos.data_exclusao))
        AND date(:datainicio) >= date(coalesce(orcamentos.data_criacao, :datainicio))
        AND orcamentos.data_inicial IS NULL
        AND orcamentos.data_final  IS NULL
    GROUP BY orcamentos.id, despesas.id_despesa
),
calc AS (
  SELECT
    id_orc, id_profile, notify_over, orc_data_criacao, data_exclusao,
    nao_somadas, saldo_previsto, id_orcamento_receita_referencia,
    orc_meta_val, tipo, orc_data_inicial, orc_data_final, perc_alerta,
    perc_receitas, descricao_orcamento_receita_referencia, descricao,
    orc_cor, orc_icon, orc_exibir_resumo, orc_somar, orc_data,
    SUM(efet) AS efet, SUM(pend) AS pend
  FROM calc_por_ocorrencia
  GROUP BY id_orc
),

/* Normalização para somar filhos no pai (se pais entram zerados */
norm AS (
  SELECT
    c.*,
    COALESCE(rel.id_pai, c.id_orc) AS display_id,
    CASE WHEN p.id IS NOT NULL THEN 0 ELSE c.orc_meta_val END AS orc_meta_norm,
    CASE WHEN p.id IS NOT NULL THEN 0 ELSE c.efet        END AS efet_norm,
    CASE WHEN p.id IS NOT NULL THEN 0 ELSE c.pend        END AS pend_norm,
    CASE WHEN p.id IS NOT NULL THEN 0 ELSE c.perc_receitas END AS perc_receitas_norm
  FROM calc c
  LEFT JOIN orcamentos_agrupamento rel
         ON rel.id_filho = c.id_orc
  LEFT JOIN parents p
         ON p.id = c.id_orc
),

/* Agregação por display_id (pais recebem soma dos filhos; avulsos mantêm seus valores) */
agg AS (
  SELECT
    display_id                           AS id_orc,
    SUM(orc_meta_norm)                   AS orc_meta,
    SUM(perc_receitas_norm)              AS perc_receitas,
    MIN(id_orcamento_receita_referencia) AS id_orcamento_receita_referencia,
    MIN(descricao_orcamento_receita_referencia)
                                         AS descricao_orcamento_receita_referencia,
    SUM(efet_norm)                       AS efet,
    SUM(pend_norm)                       AS pend,
    MIN(orc_data)                        AS orc_data
  FROM norm
  GROUP BY display_id
),

/* Filhos individuais (para quando mostrar_filhos='S') */
children_rows AS (
  SELECT
    c.id_orc,
    c.id_profile,
    c.notify_over,
    c.orc_data_criacao,
    c.data_exclusao,
    c.nao_somadas,
    c.saldo_previsto,
    c.id_orcamento_receita_referencia,
    c.orc_meta_val     AS orc_meta,   -- meta do próprio filho
    c.tipo,
    c.orc_data_inicial,
    c.orc_data_final,
    c.perc_alerta,
    c.perc_receitas,
    c.descricao_orcamento_receita_referencia,
    c.descricao,
    c.orc_cor,
    c.orc_icon,
    c.orc_exibir_resumo,
    c.orc_data,
    c.efet,
    c.pend,
    'N' AS pai,
    'S' AS filho
  FROM calc c
  WHERE EXISTS (SELECT 1 FROM children ch WHERE ch.id = c.id_orc)
)

/* Resultado final
   - Traz avulsos sempre e pais agregados somente quando mostrar_pais = 'S'
   - Se mostrar_filhos = 'S', adiciona os filhos individuais
*/
SELECT
   orcamentos.id                                   AS id_orc,
   orcamentos.id_profile                           AS id_profile,
   COALESCE(orcamentos.notify_over, 'N')           AS notify_over,
   COALESCE(orcamentos.data_criacao, :datainicio)  AS orc_data_criacao,
   orcamentos.data_exclusao                        AS data_exclusao,
   COALESCE(orcamentos.nao_somadas, 'S')           AS nao_somadas,
   COALESCE(orcamentos.saldo_previsto, 'N')        AS saldo_previsto,
   COALESCE(orcamentos.tipo_logica_tags, 'OR')     AS tipo_logica_tags,
   a.id_orcamento_receita_referencia,
   a.orc_meta                                      AS orc_meta,          -- soma filhos (ou próprio se avulso)
   orcamentos.tipo                                 AS tipo,
   orcamentos.data_inicial                         AS orc_data_inicial,
   orcamentos.data_final                           AS orc_data_final,
   COALESCE(orcamentos.perc_alerta, 80)            AS perc_alerta,
   a.perc_receitas,
   a.descricao_orcamento_receita_referencia,
   orcamentos.descricao                            AS descricao,
   COALESCE(orcamentos.cor, 0)                     AS orc_cor,
   COALESCE(orcamentos.icon_id, 955)               AS orc_icon,
   COALESCE(orcamentos.exibir_resumo, 'N')         AS orc_exibir_resumo,
   COALESCE(orcamentos.somar, 'S')                 AS orc_somar,
   a.orc_data                             AS orc_data,
   a.efet,
   a.pend,
   CASE WHEN EXISTS (SELECT 1 FROM parents p2 WHERE p2.id = orcamentos.id)
        THEN 'S' ELSE 'N' END             AS pai,
   CASE WHEN EXISTS (SELECT 1 FROM children c2 WHERE c2.id = orcamentos.id)
        THEN 'S' ELSE 'N' END             AS filho
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
   orcamentos.id                                  AS id_orc,
   orcamentos.id_profile,
   COALESCE(orcamentos.notify_over, 'N')          AS notify_over,
   COALESCE(orcamentos.data_criacao, :datainicio) AS orc_data_criacao,
   orcamentos.data_exclusao                       AS data_exclusao,
   COALESCE(orcamentos.nao_somadas, 'S')          AS nao_somadas,
   COALESCE(orcamentos.saldo_previsto, 'N')       AS saldo_previsto,
   COALESCE(orcamentos.tipo_logica_tags, 'OR')    AS tipo_logica_tags,
   cr.id_orcamento_receita_referencia,
   cr.orc_meta,
   orcamentos.tipo,
   orcamentos.data_inicial                        AS orc_data_inicial,
   orcamentos.data_final                          AS orc_data_final,
   COALESCE(orcamentos.perc_alerta, 80)           AS perc_alerta,
   cr.perc_receitas,
   cr.descricao_orcamento_receita_referencia,
   orcamentos.descricao                           AS descricao,
   COALESCE(orcamentos.cor, 0)                    AS orc_cor,
   COALESCE(orcamentos.icon_id, 955)              AS orc_icon,
   COALESCE(orcamentos.exibir_resumo, 'N')        AS orc_exibir_resumo,
   COALESCE(orcamentos.somar, 'S')                AS orc_somar,
   cr.orc_data,
   cr.efet,
   cr.pend,
   'N' AS pai,
   'S' AS filho
FROM children_rows cr
JOIN orcamentos
  ON orcamentos.id = cr.id_orc
WHERE
  (:mostrar_filhos = 'S')                     -- só inclui filhos se parametrizado
  AND (:somente_resumo <> 'S' OR COALESCE(orcamentos.exibir_resumo,'N')='S')
  {params}

ORDER BY descricao;
