SELECT
'-1' as id_despesa,
despesas_id_profile,
dtcad,
'' as place_id,
null as origem_ajuste,
null as id_provider,
null as id_open_finance_transaction,
null as descricao_open_finance,
null as category_open_finance,
'N' as possivel_transferencia_of,
'N' as possivel_fixa_mensal,
'S' as buscar_similares,
'S' as sugerir_descricao,
'N' as regra_efetivacao_parcial_open_finance,
null as valor_parcial_open_finance,
'N' as reconhecer_valor_diferente,
'N' as reconhecer_data_diferente,
'N' as lembrete_vencimento,
'' as cupom_url,
despesas_id_conta,
'-1' as id_orig_parcial,
null as dt_orig_parcial,
null as dt_registro_of,
null as ultima_modificacao,
descr,
'' as local,
'S' as limite_cartao,
'N' as excluido,
'N' as sms,
'N' as ignore_orc,
'S' as economia_mensal,
0 as intervalo,
'N' as automatica,
cons_est,
val1,
data_valor,
1 as num_cats,
'' as obs_cat_valor,
'-1'  as id_cat_valor,
juros,
dt_pg,
adiantamento_fatura,
'-1' as id_estorno,
dados_fatura,
'N' as rec,
'' as attach_id,
'' as attach_path,
0 as attach_size,
dtoriginal,
st,
'' as obs,
idori,

1 as numpar,
0 as numpars,
0 as parc_ini,
'' as idcal,
'' as ideve,
null as dteve,
'' as data_exc,
somar,
'N' as ef_auto,
'N' as ef_inicio_dia,
'S' as contabilizar,
null as lat,
null as lng,

cotacao,
conta_currency,
conta_desc,
conta_id_item,
conta_id_open_finance_account,
conta_image_url,
conta_image_id,
conta_id_categoria,
conta_cat_descricao,
conta_cat_cor,
conta_cat_icon_id,
conta_somar,

'-1' as cat_id,
'' as cat_nome,
-1 as cat_cor,
-1 as cat_icon_id,

'-1' as subcat_id,
'' as subcat_nome,
-1 as subcat_cor,
-1 as subcat_icon_id,

/**{columns_card_out}**/
card_id,
card_nome,
card_tipo,
card_img,
card_limite,
card_cor,
card_padrao,
card_dia_venc,
dia_fecha,
num_cartao,
card_id_conta,
card_id_open_finance_account,
'S' as agrupando,
card_dias_fechamento,
card_fechamento_dias_uteis,

ROUND(SUM((CASE WHEN val1 < 0 THEN 0 ELSE val1 END)), 2) as val,
ROUND(SUM((CASE WHEN val1 < 0 AND coalesce(adiantamento_fatura, 'N') = 'S' THEN val1 * -1 ELSE 0 END)), 2) as adiantamentos,
ROUND(SUM((CASE WHEN val1 < 0 AND coalesce(adiantamento_fatura, 'N') = 'S' AND st = 'pd' THEN val1 * -1 ELSE 0 END)), 2) as adiantamentos_pend,
ROUND(SUM((CASE WHEN val1 < 0 AND coalesce(adiantamento_fatura, 'N') = 'N' THEN val1 * -1 ELSE 0 END)), 2) as estornos,
ROUND(SUM((CASE WHEN val1 < 0 AND coalesce(adiantamento_fatura, 'N') = 'N' AND st = 'pd' THEN val1 * -1 ELSE 0 END)), 2) as estornos_pend,
ROUND(SUM((CASE WHEN st = 'pd' AND val1 > 0 THEN val1 ELSE 0 END)), 2) as pendentes,
ROUND(SUM((CASE WHEN st != 'pd' AND val1 > 0 THEN val1 ELSE 0 END)), 2) as efetivadas,

count(0) as registros,

(datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| card_dia_venc, -2, 2) > strftime('%d', date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| card_dia_venc, -2, 2)
 END))) as data_venc,

(datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| card_dia_venc, -2, 2) > strftime('%d', date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| card_dia_venc, -2, 2)
END))) as dt

FROM
(SELECT
cartoes_credito.id_profile  as despesas_id_profile,
COALESCE(despesas_fixas_valor.data_cadastro, despesas.data_cadastro) dtcad,
ifnull(despesas_fixas_valor.id_conta, despesas.id_conta) as despesas_id_conta,
cartoes_credito.nome as descr,
ifnull(considerar_estatistica, 'S') as cons_est,
round(SUM(catmap.valor) + COALESCE(despesas_fixas.juros, despesas.juros, 0), 2) as val1,
despesas_fixas_valor.data as data_valor,
0.0 as juros,
COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) as dt_pg,
coalesce(adiantamento_fatura, 'N') as adiantamento_fatura,
despesas.dados_fatura as dados_fatura,
despesas.recorrencia as rec,

(CASE despesas.recorrencia WHEN 'F' THEN
 datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
 (CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
  END))
  ELSE despesas.data  END) as dt,

despesas.data as dtoriginal,
ifnull(despesas_fixas.status, despesas.status) as st,
despesas.id_origem as idori,

COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1) cotacao,
COALESCE(contas.currency, '')   as conta_currency,
contas.descricao                as conta_desc,
contas.id_item                  as conta_id_item,
contas.id_open_finance_account  as conta_id_open_finance_account,
coalesce(contas.image_url, ofi.image_url) as conta_image_url,
ifnull(contas.image_id, 0)      as conta_image_id,
contas_cat.id as conta_id_categoria,
contas_cat.descricao as conta_cat_descricao,
ifnull(contas_cat.cor, 0) as conta_cat_cor,
ifnull(contas_cat.icon_id, 252) as conta_cat_icon_id,

ifnull(contas.somar_total,'S') as conta_somar,
ifnull(despesas.somar_total,'S') as somar,

/**{columns_card_in}**/

ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito)    as card_id,
cartoes_credito.nome                                         as card_nome,
ifnull(cartoes_credito.tipo, 'NONE')                         as card_tipo,
cartoes_credito.img_id                                       as card_img,
ifnull(cartao_mes.limite, cartoes_credito.limite)            as card_limite,
cartoes_credito.cor                                          as card_cor,
ifnull(cartoes_credito.padrao, 'N')                          as card_padrao,
ifnull(cartao_mes.dia_venc, cartoes_credito.dia_venc)        as card_dia_venc,
ifnull(cartao_mes.dia_fecha, cartoes_credito.dia_fecha)      as dia_fecha,
cartoes_credito.dia_fecha                                    as num_cartao,
 ifnull(cartao_mes.id_conta, cartoes_credito.id_conta)       as card_id_conta,
cartoes_credito.id_open_finance_account                      as card_id_open_finance_account,
coalesce(cartoes_credito.dias_fechamento, -1)                as card_dias_fechamento,
ifnull(cartoes_credito.fechamento_dias_uteis, 'N')           as card_fechamento_dias_uteis

FROM despesas
inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
               AND (despesas.recorrencia != 'F' OR
                      (date(catmap.data)  = date(COALESCE(
                       (SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                        AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
                        AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')),
                       /* Antes do primeiro vencimento, a listagem do orçamento usa somente
                          o mapeamento inicial e não antecipa categorias cadastradas depois. */
                       CASE WHEN '{iniciar_fixa_no_lancamento}' = 'S' THEN
                        (SELECT MIN(dcv_inicio.data) FROM despesas_cat_valor dcv_inicio
                         WHERE dcv_inicio.id_despesa = catmap.id_despesa)
                       END))
                       AND catmap.excluido != 'S'))
/**{INNER_JOIN}**/
left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
and (date(COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao), 'start of month') = date(:datainicio, 'start of month') OR date(despesas_fixas.data, 'start of month') = date(:datainicio, 'start of month'))
left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
    and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join contas on contas.id = despesas_id_conta
left join open_finance_items as ofi on ofi.id = contas.id_item
left join contas_cat on contas_cat.id = contas.id_categoria
left join cartoes_credito on cartoes_credito.id = card_id
left join cartoes_credito_mes as cartao_mes ON date(cartao_mes.ano || '-' || substr('0' || cartao_mes.mes, -2, 2) ||  '-01') =
(select  max(date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01'))
from cartoes_credito_mes
where date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01') <= date(:datainicio, 'start of month')
and id_cartao = cartoes_credito.id)
and cartao_mes.id_cartao  = cartoes_credito.id
{PARAMS}
-- o filtro pelos lançamentos do cartão, quando agrupando, deve ser a fatura completa
-- para isso, o filtro de data deve sempre compreender o mês inteiro
AND date(dt) BETWEEN date(:datainicio, 'start of month') and date(:datainicio,'start of month','+1 month','-1 day')
{GROUP_CARTAO}

UNION ALL

SELECT
despesas.id as id_despesa,
despesas.id_profile  as despesas_id_profile,
COALESCE(despesas_fixas_valor.data_cadastro, despesas.data_cadastro) dtcad,
despesas.place_id as place_id,
despesas.origem_ajuste as origem_ajuste,
despesas.id_provider as id_provider,
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
despesas.descricao_open_finance      as descricao_open_finance,
despesas.category_open_finance      as category_open_finance,
despesas.possivel_transferencia_of   as possivel_transferencia_of,
despesas.possivel_fixa_mensal   as possivel_fixa_mensal,
COALESCE(despesas.buscar_similares, 'S') as buscar_similares,
COALESCE(despesas.sugerir_descricao, 'S') as sugerir_descricao,
COALESCE(despesas.regra_efetivacao_parcial_open_finance, 'N') as regra_efetivacao_parcial_open_finance,
despesas.valor_parcial_open_finance as valor_parcial_open_finance,
COALESCE(despesas.reconhecer_valor_diferente, 'N') as reconhecer_valor_diferente,
COALESCE(despesas.reconhecer_data_diferente, 'N') as reconhecer_data_diferente,
COALESCE(despesas.lembrete_vencimento, 'N') as lembrete_vencimento,
despesas.cupom_url as cupom_url,
ifnull(despesas_fixas_valor.id_conta, despesas.id_conta) as despesas_id_conta,
despesas.id_orig_parcial as id_orig_parcial,
despesas.dt_orig_parcial as dt_orig_parcial,
despesas.data_registro_of as dt_registro_of,
despesas.ultima_modificacao as ultima_modificacao,
despesas.descricao as descr,
COALESCE(despesas.local, despesas.descricao_open_finance, despesas.descricao) as local,
ifnull(despesas.limite_cartao, 'S') as limite_cartao,
ifnull(despesas_fixas.excluido_mes,'N') as excluido,
ifnull(despesas.sms,'N') as sms,
COALESCE(despesas.ignore_orc,'N') as ignore_orc,
ifnull(despesas.economia_mensal,'S') as economia_mensal,
ifnull(despesas.intervalo,0) as intervalo,
ifnull(despesas.automatica,'N') as automatica,
ifnull(considerar_estatistica, 'S') as cons_est,
-1 as val1,
despesas_fixas_valor.data as data_valor,
COUNT(catmap.valor) as num_cats,
catmap.obs as obs_cat_valor,
catmap.id  as id_cat_valor,
COALESCE(despesas_fixas.juros, despesas.juros, 0) as juros,
COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) as dt_pg,
coalesce(adiantamento_fatura, 'N') as adiantamento_fatura,
despesas.id_despesa_estornada as id_estorno,
despesas.dados_fatura as dados_fatura,
despesas.recorrencia as rec,
ifnull(despesas_fixas.attach_id, despesas.attach_id) as attach_id,
ifnull(despesas_fixas.attach_path, despesas.attach_path) as attach_path,
coalesce(despesas_fixas.attach_size, despesas.attach_size, 0) as attach_size,
despesas.data as dtoriginal,
(case when despesas.recorrencia != 'F' then despesas.status
else  ifnull(despesas_fixas.status, 'pd') end ) as st,
COALESCE(despesas_fixas.obs, despesas_fixas_valor.obs_futura, despesas.obs) as obs,
despesas.id_origem as idori,
despesas.num_parcela as numpar,
despesas.num_parcelas as numpars,
ifnull(despesas.parc_inicial,0) as parc_ini,
despesas.id_calendario as idcal,
despesas.id_event as ideve,
despesas.data_evento as dteve,
despesas.data_exclusao as data_exc,
ifnull(despesas.somar_total,'S') as somar,

ifnull(despesas.ef_auto, 'N') as ef_auto,
ifnull(despesas.ef_inicio_dia, 'N') as ef_inicio_dia,
ifnull(despesas_fixas.contabilizar, despesas.contabilizar) as contabilizar,
despesas.latitude as lat,
despesas.longitude as lng,
COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1) cotacao,
COALESCE(contas.currency, '') as conta_currency,
contas.descricao as conta_desc,
contas.id_item                  as conta_id_item,
contas.id_open_finance_account  as conta_id_open_finance_account,
coalesce(contas.image_url, ofi.image_url) as conta_image_url,
ifnull(contas.image_id, 0) as conta_image_id,
contas_cat.id as conta_id_categoria,
contas_cat.descricao as conta_cat_descricao,
ifnull(contas_cat.cor, 0) as conta_cat_cor,
ifnull(contas_cat.icon_id, 252) as conta_cat_icon_id,

ifnull(contas.somar_total,'S') as conta_somar,

despesas_cat.id as cat_id,
despesas_cat.nome as cat_nome,
despesas_cat.cor as cat_cor,
COALESCE(despesas_cat.icon_id, 955) as cat_icon_id,

despesas_subcat.id as subcat_id,
despesas_subcat.nome as subcat_nome,
despesas_subcat.cor as subcat_cor,
COALESCE(despesas_subcat.icon_id, 955) as subcat_icon_id,

/**{columns}**/

ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as card_id,
null    as card_nome,
'NONE'  as card_tipo,
-1      as card_img,
-1      as card_limite,
-1      as card_cor,
'N'     as card_padrao,
-1      as card_dia_venc,
-1      as dia_fecha,
-1      as num_cartao,
'-1'      as card_id_conta,
null    as card_id_open_finance_account,
'N'     as agrupando,
-1      as card_dias_fechamento,
'N'     as card_fechamento_dias_uteis,


ROUND(SUM(catmap.valor), 2) as val,
0 as adiantamentos,
0 as adiantamentos_pend,
0 as estornos,
0 as estornos_pend,
0 as pendentes,
0 as efetivadas,
1 as registros,
(CASE despesas.recorrencia WHEN 'F' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
 END))
 ELSE despesas.data  END) as data_venc,

{param_data_referencia} as dt

FROM despesas
/**{INNER_JOIN}**/
left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
and (date(COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao), 'start of month') = date(:datainicio, 'start of month') OR date(despesas_fixas.data, 'start of month') = date(:datainicio, 'start of month'))

inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
    AND (despesas.recorrencia != 'F' OR
           (date(catmap.data)  = date(COALESCE(
            (SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
             AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
             AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')),
            /* Antes do primeiro vencimento, a listagem do orçamento usa somente
               o mapeamento inicial e não antecipa categorias cadastradas depois. */
            CASE WHEN '{iniciar_fixa_no_lancamento}' = 'S' THEN
             (SELECT MIN(dcv_inicio.data) FROM despesas_cat_valor dcv_inicio
              WHERE dcv_inicio.id_despesa = catmap.id_despesa)
            END))
            AND catmap.excluido != 'S'))

left join despesas_cat on despesas_cat.id = catmap.id_categoria
left join despesas_subcat on despesas_subcat.id = catmap.id_subcategoria

left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
    and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

left join contas on contas.id = despesas_id_conta
left join open_finance_items as ofi on ofi.id = contas.id_item
left join contas_cat on contas_cat.id = contas.id_categoria

{PARAMS}
{FILTRO_DATAS}
{GROUP_NAO_CARTAO}
