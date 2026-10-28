SELECT
 COALESCE(SUM(limite), 0)    as tot_limit,
 COALESCE(SUM(estornos), 0)  as tot_estornos,
 COALESCE(SUM(fatura), 0)    as tot_fatura,
 COALESCE(SUM(adiantamentos), 0) as tot_adiantamentos,
 COALESCE(SUM(despesas_mes), 0)  as tot_despesas_mes,
 COALESCE(SUM(faturas_abertas), 0) as tot_valor_aberto,
 COALESCE(SUM(pendentes), 0) as tot_pendente,
 COALESCE(SUM(efetivadas), 0) as tot_efetivadas
 FROM (SELECT
COALESCE(cartao_mes.limite, cartoes_credito.limite) as limite,
COALESCE(cartao_mes.dia_venc, cartoes_credito.dia_venc) as dia_venc,
COALESCE(cartao_mes.dia_fecha, cartoes_credito.dia_fecha) as dia_fecha,
COALESCE((despesas.total - despesas.estornos - despesas.adiantamentos), 0) as total,
COALESCE((despesas.total - despesas.estornos), 0) as despesas_mes,
COALESCE(despesas.adiantamentos, 0) as adiantamentos,
COALESCE(despesas.estornos, 0) as estornos,
-- Mantem o total agregado pendente alinhado ao saldo liquido das faturas.
COALESCE(despesas.pendentes - adiantamentos_pend - estornos_pend, 0) as pendentes,
COALESCE(despesas.efetivadas, 0) as efetivadas,

-- Usa primeiro o saldo pendente liquido da fatura. O total liquido fica como
-- fallback para adiantamentos em fatura aberta com novas despesas ja efetivadas.
COALESCE((CASE WHEN (despesas.pendentes - adiantamentos_pend - estornos_pend) > 0
THEN despesas.pendentes - adiantamentos_pend - estornos_pend
ELSE despesas.total - despesas.adiantamentos - despesas.estornos END), 0) as fatura,


 COALESCE((select SUM(despesas.valor) from  despesas
 		where
 		despesas.status = 'pd'
 		and despesas.recorrencia != 'F'
 		and COALESCE(despesas.limite_cartao, 'S') = 'S'
 		and despesas.data is not null
 		and despesas.id_cartao_credito = cartoes_credito.id
        -- A listagem do valor em aberto exige categoria. Ignorar órfãs aqui
        -- mantém o total do cartão reconciliado com as despesas exibidas.
        and exists (select 1 from despesas_cat_valor as categoria_valor_aberto
        where categoria_valor_aberto.id_despesa = despesas.id)
 		AND (despesas.data_exclusao IS NULL OR
    date(strftime('%Y-%m-01',:datainicio)) <=
    date(strftime('%Y-%m-01',despesas.data_exclusao)))), 0) as faturas_abertas

 FROM cartoes_credito
 left join cartoes_credito_mes as cartao_mes ON date(cartao_mes.ano || '-' || substr('0' || cartao_mes.mes, -2, 2) ||  '-01') =
 (select  max(date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01'))
 from cartoes_credito_mes
 where date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01') <= date(:datainicio, 'start of month')
 and id_cartao = cartoes_credito.id)
 and cartao_mes.id_cartao  = cartoes_credito.id
left join (SELECT
             id_cartao,
             ROUND(SUM((CASE WHEN val < 0 THEN 0 ELSE val END)), 2) as total,
             ROUND(SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'S' THEN val * -1 ELSE 0 END)), 2) as adiantamentos,
             ROUND(SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'S' AND status = 'pd' THEN val * -1 ELSE 0 END)), 2) as adiantamentos_pend,
             ROUND(SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'N' THEN val * -1 ELSE 0 END)), 2) as estornos,
             ROUND(SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'N' AND status = 'pd' THEN val * -1 ELSE 0 END)), 2) as estornos_pend,
             ROUND(SUM((CASE WHEN status = 'pd' AND val > 0 THEN val ELSE 0 END)), 2) as pendentes,
             ROUND(SUM((CASE WHEN status != 'pd' AND val > 0 THEN val ELSE 0 END)), 2) as efetivadas
           FROM (SELECT
             COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as id_cartao,
             (SUM(catmap.valor)  + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as val,
             COALESCE(adiantamento_fatura, 'N') as adiantamento_fatura,
             (case when recorrencia = 'F' and despesas_fixas.status is null
             then 'pd' when  recorrencia = 'F' and despesas_fixas.status is not null
             then despesas_fixas.status when   recorrencia != 'F' then despesas.status end) as status,
            (CASE recorrencia WHEN 'F' THEN
            datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
            (CASE WHEN  substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
             THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
             ELSE   substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
             END))
             ELSE despesas.data  END) as dt
             FROM despesas
             inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
               AND (despesas.recorrencia != 'F' OR
                      (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                       AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(COALESCE(obs, '')) = LOWER(COALESCE(catmap.obs,''))
                       AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
                       AND catmap.excluido != 'S'))
             left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(COALESCE(despesas_fixas.data, despesas.data), 'start of month') = date(:datainicio, 'start of month')
              left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
                     and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
                    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
            WHERE
             (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
             and COALESCE(despesas_fixas.excluido_mes,'N') = 'N'
            AND (despesas.data_exclusao IS NULL OR
                 date(strftime('%Y-%m-01',:datainicio)) <=
                 date(strftime('%Y-%m-01', despesas.data_exclusao)))

            AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
            and date(:datainicio,'start of month','+1 month','-1 day')
            and COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) NOT IN ('', '-1')
            GROUP BY catmap.id_despesa)
           GROUP BY id_cartao) as despesas on despesas.id_cartao = cartoes_credito.id
 WHERE
  (:graficos = 'N' OR total > 0)
  AND (:grafico_anual = 'N' OR cartoes_credito.id = :id)
  AND (cartoes_credito.data_exclusao IS NULL OR
        date(strftime('%Y-%m-01',:datainicio)) <=
        date(strftime('%Y-%m-01',cartoes_credito.data_exclusao)))
        {params}
)
