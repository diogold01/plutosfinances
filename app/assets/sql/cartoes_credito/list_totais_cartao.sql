SELECT
 (despesas.total - despesas.estornos - despesas.adiantamentos) as total,
 (despesas.total - despesas.estornos) as despesas_mes,
 despesas.adiantamentos,
 despesas.estornos,
 -- Mantem o total pendente alinhado ao saldo liquido exibido na fatura.
 (despesas.pendentes - adiantamentos_pend - estornos_pend) as pendentes,
 despesas.efetivadas,
-- Usa primeiro o saldo pendente liquido da fatura. O total liquido fica como
-- fallback para adiantamentos em fatura aberta com novas despesas ja efetivadas.
round((CASE WHEN (despesas.pendentes - adiantamentos_pend - estornos_pend) > 0
THEN despesas.pendentes - adiantamentos_pend - estornos_pend
ELSE despesas.total - despesas.adiantamentos - despesas.estornos END), 2) as fatura,
 ifnull((select SUM(despesas.valor) from  despesas
 		where
 		despesas.status = 'pd'
 		and despesas.recorrencia != 'F'
 		and ifnull(despesas.limite_cartao, 'S') = 'S'
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
left join contas on  ifnull(cartao_mes.id_conta, cartoes_credito.id_conta) = contas.id
left join (SELECT
             id_cartao,
             SUM((CASE WHEN val < 0 THEN 0 ELSE val END)) as total,
             SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'S' THEN val * -1 ELSE 0 END)) as adiantamentos,
             SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'S' AND status = 'pd' THEN val * -1 ELSE 0 END)) as adiantamentos_pend,
             SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'N' THEN val * -1 ELSE 0 END)) as estornos,
             SUM((CASE WHEN val < 0 AND coalesce(adiantamento_fatura, 'N') = 'N' AND status = 'pd' THEN val * -1 ELSE 0 END)) as estornos_pend,
             SUM((CASE WHEN status = 'pd' AND val > 0 THEN val ELSE 0 END)) as pendentes,
             SUM((CASE WHEN status != 'pd' AND val > 0 THEN val ELSE 0 END)) as efetivadas
           FROM (SELECT
             ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as id_cartao,
             (SUM(catmap.valor)  + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as val,
             ifnull(adiantamento_fatura, 'N') as adiantamento_fatura,
             (case when recorrencia = 'F' and despesas_fixas.status is null
             then 'pd' when  recorrencia = 'F' and despesas_fixas.status is not null
             then despesas_fixas.status when   recorrencia != 'F' then despesas.status end) as status,
            (CASE recorrencia WHEN 'F' THEN
            datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
            (CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
             THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
             ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
             END))
             ELSE despesas.data  END) as dt
             FROM despesas
             inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
               AND (despesas.recorrencia != 'F' OR
                      (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                       AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
                       AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
                       AND catmap.excluido != 'S'))
             left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(ifnull(despesas_fixas.data, despesas.data), 'start of month') = date(:datainicio, 'start of month')
              left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
                     and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
                    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
            WHERE
             (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
             and ifnull(despesas_fixas.excluido_mes,'N') = 'N'
            AND (despesas.data_exclusao IS NULL OR
                 date(strftime('%Y-%m-01',:datainicio)) <=
                 date(strftime('%Y-%m-01',despesas.data_exclusao)))

            AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
            and date(:datainicio,'start of month','+1 month','-1 day')
            and ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) NOT IN ('', '-1')
            GROUP BY catmap.id_despesa)
           GROUP BY id_cartao) as despesas on despesas.id_cartao = cartoes_credito.id
