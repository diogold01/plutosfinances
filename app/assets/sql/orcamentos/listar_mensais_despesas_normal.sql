/* O rateio multiplica as linhas, não os encargos/descontos. Agrupa depois
   dos filtros para aplicar o valor assinado uma vez por despesa elegível. */
WITH valores_por_ocorrencia AS (
SELECT
           orcamentos.id                                    as id_orc,
           orcamentos.id_profile                            as id_profile,
           coalesce(orcamentos.notify_over, 'N')            as notify_over,
           coalesce(orcamentos.data_criacao, :datainicio)   as orc_data_criacao,
           orcamentos.data_exclusao                         as data_exclusao,
           coalesce(orcamentos.nao_somadas, 'S')            as nao_somadas,
           coalesce(orcamentos.saldo_previsto, 'N')         as saldo_previsto,
           coalesce(orcamentos.tipo_logica_tags, 'OR')      as tipo_logica_tags,
           coalesce(orc_meta.id_orcamento_receita_referencia, orcamentos.id_orcamento_receita_referencia)
                                                             as id_orcamento_receita_referencia,
           CASE
           WHEN coalesce(orc_meta.perc_receitas, orcamentos.perc_receitas, 0) > 0
           THEN (:valor_receitas * coalesce(orc_meta.perc_receitas, orcamentos.perc_receitas, 0)) / 100.0
           ELSE COALESCE(orc_meta.meta, orcamentos.meta)
           END                                              AS orc_meta,
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
             + coalesce(MAX(juros_pend * cotacao),0) as pend,
           CASE WHEN parents.id is not null
           THEN 'S' ELSE 'N' END                         AS pai,
           CASE WHEN children.id is not null
           THEN 'S' ELSE 'N' END                         AS filho
     FROM
        orcamentos
        left join orcamentos_mensal as orc_meta on orcamentos.id = orc_meta.id_orcamento
        and date(orc_meta.data, 'start of month') = (select date(max(orcamentos_mensal.data),'start of month') from orcamentos_mensal where id_orcamento = orcamentos.id
        and date(orcamentos_mensal.data, 'start of month') <= date(:datainicio, 'start of month'))
        left join (SELECT DISTINCT id_pai AS id FROM orcamentos_agrupamento) as parents on parents.id = orcamentos.id
        left join (SELECT DISTINCT id_filho AS id FROM orcamentos_agrupamento) as children on children.id = orcamentos.id
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
    AND (:somente_resumo <> 'S' OR COALESCE(orcamentos.exibir_resumo,'N')='S')
    {params}
GROUP BY orcamentos.id, despesas.id_despesa
)
SELECT
  id_orc, id_profile, notify_over, orc_data_criacao, data_exclusao,
  nao_somadas, saldo_previsto, tipo_logica_tags,
  id_orcamento_receita_referencia, orc_meta, tipo, orc_data_inicial,
  orc_data_final, perc_alerta, perc_receitas,
  descricao_orcamento_receita_referencia, descricao, orc_cor, orc_icon,
  orc_exibir_resumo, orc_somar, orc_data,
  SUM(efet) AS efet, SUM(pend) AS pend, pai, filho
FROM valores_por_ocorrencia
GROUP BY id_orc
ORDER BY descricao
