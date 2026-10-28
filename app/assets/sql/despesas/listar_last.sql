SELECT
coalesce(despesas_fixas_valor.id_conta, despesas.id_conta) as despesas_id_conta,
despesas.id as id_gas,
despesas.id_origem as id_ori,
despesas.id_profile as despesas_id_profile,
despesas.id_provider as id_provider,
despesas.descricao as descr,
COALESCE(despesas.regra_efetivacao_parcial_open_finance, 'N') as regra_efetivacao_parcial_open_finance,
despesas.valor_parcial_open_finance as valor_parcial_open_finance,
COALESCE(despesas.reconhecer_valor_diferente, 'N') as reconhecer_valor_diferente,
COALESCE(despesas.reconhecer_data_diferente, 'N') as reconhecer_data_diferente,
COALESCE(despesas.lembrete_vencimento, 'N') as lembrete_vencimento,
 COALESCE(despesas_fixas_valor.data_cadastro, despesas.data_cadastro) data_cadastro,

CASE WHEN despesas.recorrencia = 'F' THEN
  COALESCE(
    despesas_fixas.id_open_finance_transaction,
    CASE WHEN NOT EXISTS (
      SELECT 1
      FROM despesas_fixas despesas_fixas_id_of
      WHERE despesas_fixas_id_of.id_despesa = despesas.id
        AND COALESCE(despesas_fixas_id_of.id_open_finance_transaction, '') != ''
    ) THEN despesas.id_open_finance_transaction END
  )
ELSE despesas.id_open_finance_transaction END as id_open_finance_transaction,
despesas.descricao_open_finance as descricao_open_finance,
despesas.category_open_finance as category_open_finance,
despesas.possivel_transferencia_of as possivel_transferencia_of,
despesas.possivel_fixa_mensal as possivel_fixa_mensal,
COALESCE(despesas.buscar_similares, 'S') as buscar_similares,
COALESCE(despesas.sugerir_descricao, 'S') as sugerir_descricao,
(CASE despesas.recorrencia WHEN 'F' THEN
 datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
 (CASE WHEN  substr('0'|| coalesce(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  ELSE   substr('0'|| coalesce(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
  END))
  ELSE despesas.data END) as data_ref,

{param_data_referencia} as dt,
coalesce(despesas.somar_total,'S') as somar,
coalesce(adiantamento_fatura, 'N') as adiantamento_fatura,
coalesce(despesas.sms,'N') as sms,
COALESCE(despesas.ignore_orc,'N') as ignore_orc,
coalesce(despesas.limite_cartao, 'S') as limite_cartao,
despesas.obs,
despesas.recorrencia,
despesas.num_parcela,
despesas.num_parcelas,
(case when despesas.recorrencia != 'F' then despesas.status
else  coalesce(despesas_fixas.status, 'pd') end ) as st,
{valor},
COUNT(catmap.valor) as num_cats,
catmap.obs as obs_cat_valor,
catmap.id  as id_cat_valor,
coalesce(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as card_id,
COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1) cotacao,
COALESCE(contas.currency, '') as conta_currency,
contas.descricao as conta_desc,
contas.id_item                  as conta_id_item,
contas.id_open_finance_account  as conta_id_open_finance_account,
coalesce(contas.image_url, ofi.image_url) as conta_image_url,
coalesce(contas.image_id, 0) as conta_image_id,

contas_cat.descricao as conta_cat_descricao,
coalesce(contas_cat.cor, 0) as conta_cat_cor,
contas_cat.id as conta_id_categoria,

coalesce(contas.somar_total,'S') as conta_somar,

despesas_cat.id as cat_id,
despesas_cat.nome as cat_nome,
despesas_cat.cor as cat_cor,
despesas_cat.icon_id as cat_icon,

despesas_subcat.id as subcat_id,
despesas_subcat.nome as subcat_nome,
despesas_subcat.cor as subcat_cor,
despesas_subcat.icon_id as subcat_icon,

coalesce(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as card_id,
cartoes_credito.nome           as card_nome,
cartoes_credito.img_id         as card_img,
coalesce(cartoes_credito.tipo, 'NONE') as card_tipo,
cartoes_credito.limite         as card_limite,
cartoes_credito.cor            as card_cor,
coalesce(cartoes_credito.padrao, 'N') as card_padrao,
cartoes_credito.dia_venc       as card_dia_venc,
cartoes_credito.dia_fecha      as dia_fecha,
cartoes_credito.dia_fecha      as num_cartao,
cartoes_credito.id_conta       as card_id_conta,
coalesce(cartoes_credito.dias_fechamento, -1)      as card_dias_fechamento,
coalesce(cartoes_credito.fechamento_dias_uteis, 'N') as card_fechamento_dias_uteis

FROM despesas
left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
and date(coalesce(despesas_fixas.data,despesas.data), 'start of month') = date(:datainicio, 'start of month')

inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
    AND (despesas.recorrencia != 'F' OR
           (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
            AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(coalesce(obs, '')) = LOWER(coalesce(catmap.obs,''))
            AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
            AND catmap.excluido != 'S'))

left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
    and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join despesas_cat on despesas_cat.id = catmap.id_categoria
left join despesas_subcat on despesas_subcat.id = catmap.id_subcategoria
left join contas on contas.id = despesas_id_conta
left join open_finance_items as ofi on ofi.id = contas.id_item
left join contas_cat on contas_cat.id = contas.id_categoria
left join cartoes_credito on cartoes_credito.id = card_id
{params}
