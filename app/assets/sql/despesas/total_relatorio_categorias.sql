SELECT cat_id,
 cat_nome,
 cat_cor,
 cat_icon_id,
 subcat_id,
 subcat_nome,
 subcat_cor,
 subcat_icon_id,
 COALESCE(SUM((val + juros) * cotacao),0) as total
 FROM (SELECT
despesas.id as idgas,
despesas.id_profile,
despesas.descricao,
ifnull(despesas_fixas_valor.id_conta, despesas.id_conta) as despesas_id_conta,
round(SUM(catmap.valor), 2) as val,
ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as card_id,
COALESCE(despesas_fixas.juros, despesas.juros, 0) as juros,

COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1) as cotacao,

despesas.recorrencia as rec,

{param_data_referencia} as dt,

despesas_cat.id as cat_id,
despesas_cat.nome as cat_nome,
despesas_cat.cor as cat_cor,
COALESCE(despesas_cat.icon_id, 955) as cat_icon_id,

despesas_subcat.id as subcat_id,
despesas_subcat.nome as subcat_nome,
despesas_subcat.cor as subcat_cor,
COALESCE(despesas_subcat.icon_id, 955) as subcat_icon_id,

despesas.data as dtoriginal,
(case when despesas.recorrencia != 'F'
then despesas.status
else  COALESCE(despesas_fixas.status, 'pd') end ) as st,
(CASE WHEN COALESCE(contas.somar_total, 'S') = 'N'
THEN 'N' ELSE COALESCE(despesas.somar_total,'S') END) as somar

FROM despesas
inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
   AND (despesas.recorrencia != 'F' OR
       (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
        AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
        AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
        AND catmap.excluido != 'S'))

left join filtros_contas fc on fc.id_filtro = :id_filtro
left join filtros_cartoes fct on fct.id_filtro = :id_filtro
left join filtros_categorias fcg on fcg.id_filtro = :id_filtro AND ifnull(fcg.tipo, '') IN ('', 'D')

left join despesas_cat on despesas_cat.id = catmap.id_categoria
left join despesas_subcat on despesas_subcat.id = catmap.id_subcategoria

left join despesas_fixas on despesas.id = despesas_fixas.id_despesa
and (date(COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao), 'start of month') = date(:datainicio, 'start of month') OR date(despesas_fixas.data, 'start of month') = date(:datainicio, 'start of month'))
left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
    and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
    and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
LEFT JOIN contas ON contas.id = despesas_id_conta

WHERE (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
AND despesas.id_profile = :id_profile
AND (despesas.data_exclusao IS NULL OR date(strftime('%Y-%m-01',:datainicio)) <=
date(strftime('%Y-%m-01', despesas.data_exclusao)))
AND date(dt) BETWEEN date(:datainicio) AND date(:datafim)
AND ifnull(despesas_fixas.excluido_mes,'N') = 'N'
AND (fc.id_conta IS NULL OR fc.id_conta = despesas_id_conta)
AND (fct.id_cartao IS NULL OR fct.id_cartao = card_id)
AND (fcg.id_subcategoria IS NULL OR (fcg.id_categoria = catmap.id_categoria
AND (fcg.id_subcategoria = '-1' OR fcg.id_subcategoria = catmap.id_subcategoria)))
AND ( NOT EXISTS (SELECT 1 FROM filtros_tags WHERE id_filtro = :id_filtro)
OR EXISTS (SELECT 1 FROM tags_transacoes tt JOIN filtros_tags ft ON ft.id_tag = tt.id_tag WHERE tt.id_transacao = id_origem AND ft.id_filtro = :id_filtro))
{params}
GROUP BY catmap.id_despesa, catmap.id_categoria, catmap.id_subcategoria
)
GROUP BY cat_id
