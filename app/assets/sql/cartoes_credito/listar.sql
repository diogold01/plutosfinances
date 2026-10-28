SELECT
 cartoes_credito.id as card_id,
 nome,
 nome_carteira,
 cor,

 -- OPEN FINANCE
 cartoes_credito.id_item,
 cartoes_credito.id_open_finance_account,
 cartoes_credito.holder_type,
 last_successful_sync_at,
 coalesce(ofi.name_connector, '') as nome_instituicao,
 -- A imagem local definida no item Open Finance deve substituir a URL remota
 -- da instituição também nos cartões vinculados.
 case when ofi.image_id is not null and ofi.image_id >= 0
 then null
 else coalesce(cartoes_credito.image_url, ofi.image_url) end as image_url,
 coalesce(ofi.status, '')         as status_conexao,
 coalesce(ofi.primary_color, '')  as primary_color,

 cartoes_credito.id_profile,
 cartao_mes_referencia.attach_path,
 cartao_mes_referencia.attach_id,
 COALESCE(cartao_mes_referencia.attach_size, 0) as attach_size,
 ifnull(cartoes_credito.tipo, 'NONE') as tipo,
 coalesce(dias_fechamento, -1) as dias_fechamento,
 ifnull(cartoes_credito.fechamento_dias_uteis, 'N') as fechamento_dias_uteis,
 ifnull(cartoes_credito.padrao, 'N') as padrao,
 ifnull(cartoes_credito.text_alt, 'N') as text_alternativo,
 ifnull(cartoes_credito.sequence, 0) as sequence,
 ifnull(cartao_mes.limite, cartoes_credito.limite) as limite,
 ifnull(cartao_mes.conta_vinculada, cartoes_credito.conta_vinculada) as has_conta_vinculada,
 img_id,
 case when ofi.image_id is not null
 then ofi.image_id
 else ifnull(cartoes_credito.image_id, -1) end as image_id,
 ifnull(cartao_mes.dia_venc, cartoes_credito.dia_venc) as dia_venc,
 ifnull(cartao_mes.dia_fecha, cartoes_credito.dia_fecha) as dia_fecha,
 num_cartao,
 ifnull(cartao_mes.id_conta, cartoes_credito.id_conta) as id_conta,
 contas.descricao as conta_name,
 contas.somar_total as conta_somar,
 cartoes_credito.data_exclusao as data_ex,

 ifnull((despesas.total - despesas.estornos - despesas.adiantamentos), 0) as total,
 ifnull((despesas.total - despesas.estornos), 0) as despesas_mes,
  ifnull(despesas.adiantamentos, 0) as adiantamentos,
  ifnull(despesas.estornos, 0) as estornos,
  -- O rodape deve apresentar o saldo pendente liquido, como a fatura exibida
  -- no cartao, descontando estornos e adiantamentos ainda pendentes.
  ifnull(despesas.pendentes - despesas.adiantamentos_pend - despesas.estornos_pend, 0) as pendentes,
  ifnull(despesas.efetivadas, 0) as efetivadas,
  -- Usa primeiro o saldo pendente liquido da fatura. O total liquido fica como
  -- fallback para adiantamentos em fatura aberta com novas despesas ja efetivadas.
  ifnull((CASE WHEN (despesas.pendentes - despesas.adiantamentos_pend - despesas.estornos_pend) > 0
  THEN despesas.pendentes - despesas.adiantamentos_pend - despesas.estornos_pend
  ELSE despesas.total - despesas.adiantamentos - despesas.estornos END), 0) as fatura,
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
    date(strftime('%Y-%m-01',despesas.data_exclusao)))), 0) as faturas_abertas,
     ifnull((select SUM(despesas.valor) from  despesas
            where
            despesas.status = 'pd'
            and ifnull(despesas.limite_cartao, 'S') = 'N'
            and despesas.data is not null
            and despesas.id_cartao_credito = cartoes_credito.id
            AND (despesas.data_exclusao IS NULL OR
        date(strftime('%Y-%m-01',:datainicio)) <=
        date(strftime('%Y-%m-01', despesas.data_exclusao)))), 0) as ignorar_limite

FROM cartoes_credito
-- Dados fixos do cartao do mes pesquisado em diante
left join cartoes_credito_mes as cartao_mes ON cartao_mes.id_cartao  = cartoes_credito.id AND date(cartao_mes.ano || '-' || substr('0' || cartao_mes.mes, -2, 2) ||  '-01') =
(select  max(date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01'))
from cartoes_credito_mes
where date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01') <= date(:datainicio, 'start of month')
and id_cartao = cartoes_credito.id)

/* OPN FINANCE ITEMS */
left join open_finance_items as ofi on ofi.id = cartoes_credito.id_item

-- Dados do mês atualmente sendo pesquisado
left join cartoes_credito_mes as cartao_mes_referencia ON cartao_mes_referencia.id_cartao  = cartoes_credito.id AND
date(cartao_mes_referencia.ano || '-' || substr('0' || cartao_mes_referencia.mes, -2, 2) ||  '-01') = date(:datainicio, 'start of month')
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
             (round(SUM(catmap.valor),2)  + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as val,
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
                 date(strftime('%Y-%m-01', despesas.data_exclusao)))

            AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
            and date(:datainicio,'start of month','+1 month','-1 day')
            and ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) NOT IN ('', '-1')
            GROUP BY catmap.id_despesa)
           GROUP BY id_cartao) as despesas on despesas.id_cartao = card_id
{joins}
WHERE
 (:graficos = 'N' OR total > 0)
  AND (cartoes_credito.id = :id_cartao OR
(COALESCE(:id_cartao, '') = ''
AND (cartoes_credito.data_exclusao IS NULL OR
date(strftime('%Y-%m-01', :datainicio)) <=
date(strftime('%Y-%m-01', cartoes_credito.data_exclusao)))))
 {params}
 ORDER BY  sequence, ifnull(cartoes_credito.padrao, 'N') desc, nome
