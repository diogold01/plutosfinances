SELECT
           orcamentos.id                                    as id_orc,
           orcamentos.id_profile                            as id_profile,
           coalesce(orcamentos.notify_over, 'N')            as notify_over,
           coalesce(orcamentos.data_criacao, :datainicio)   as orc_data_criacao,
           orcamentos.data_exclusao                         as data_exclusao,
           coalesce(orcamentos.nao_somadas, 'S')            as nao_somadas,
           coalesce(orcamentos.saldo_previsto, 'N')         as saldo_previsto,
           coalesce(orcamentos.tipo_logica_tags, 'OR')      as tipo_logica_tags,
           null                                             as id_orcamento_receita_referencia,
           coalesce(orc_meta.meta, orcamentos.meta)         as orc_meta,
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
           COALESCE(orcamentos.somar, 'S')                  AS orc_somar,
           coalesce(orc_meta.data, :datainicio)             as orc_data,
           coalesce(SUM(receitas.efet * cotacao),0)         as efet,
           coalesce(SUM(receitas.pend * cotacao),0)         as pend,
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
                      receitas.id_origem,
                      receitas.id_profile,
                      COALESCE(receitas.id_categoria, '-1')     as id_categoria,
                      COALESCE(receitas.id_subcategoria, '-1')  as id_subcategoria,
                      receitas.somar_total,
                      (CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                      else COALESCE(receitas_fixas.efetivado,'N') end) = 'N' THEN 0 ELSE
                      COALESCE(receitas_fixas_valor.valor, receitas.valor) END) as efet,

                      (CASE WHEN (case when receitas.recorrencia != 'M' then receitas.efetivado
                      else COALESCE(receitas_fixas.efetivado,'N') end) = 'S' THEN 0 ELSE
                      COALESCE(receitas_fixas_valor.valor, receitas.valor) END) as pend,

                      COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,

                       {param_data_ref} as dt,
                       COALESCE(contas.somar_total,'S') as conta_somar_total
                      FROM receitas LEFT JOIN receitas_fixas on receitas.id = receitas_fixas.id_receita
                      and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
                      left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
                      and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                      and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
                      left join contas on contas.id = COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta)
                   WHERE
                     COALESCE(receitas_fixas.excluido_mes,'N') = 'N'
                     AND coalesce(receitas.ignore_orc, 'N') = 'N'
                     AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
                     AND date(dt) between date(strftime('%Y-%m-01',:datainicio)) and date(:datainicio,'start of month','+1 month','-1 day')
                     AND (receitas.data_exclusao IS NULL OR
                                                 datetime(strftime('%Y-%m-01',:datainicio)) <=
                                                 datetime(strftime('%Y-%m-01', receitas.data_exclusao))))
            as receitas ON receitas.id_profile = orcamentos.id_profile
            AND (coalesce(orcamentos.nao_somadas, 'S') = 'S' OR (coalesce(receitas.somar_total, 'S') = 'S')  AND conta_somar_total = 'S')
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
                  WHERE tt.id_transacao = receitas.id_origem
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
                    WHERE tt.id_transacao = receitas.id_origem
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
                    WHERE tt.id_transacao = receitas.id_origem
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
    AND (:somente_resumo <> 'S' OR COALESCE(orcamentos.exibir_resumo,'N')='S')
    {params}
GROUP BY orcamentos.id
ORDER BY orcamentos.descricao
