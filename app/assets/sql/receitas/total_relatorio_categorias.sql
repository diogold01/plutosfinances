SELECT
id_categoria,
cat_nome,
cat_cor,
cat_icon_id,
subcat_id,
subcat_nome,
subcat_cor,
subcat_icon_id,
COALESCE(SUM(val * cotacao), 0) as total FROM (
select
receitas.id as idreceita,
receitas.id_profile,
receitas.descricao,
ifnull(receitas.recorrencia,'N')     as rec,
round(COALESCE(receitas_fixas_valor.valor, receitas.valor),2) as val,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
ifnull(receitas_fixas_valor.id_conta, receitas.id_conta) as receitas_id_conta,

(CASE WHEN COALESCE(contas.somar_total, 'S') = 'N'
THEN 'N' ELSE COALESCE(receitas.somar_total,'S') END) as somar,

(case when receitas.recorrencia != 'M' then receitas.efetivado
	  else ifnull(receitas_fixas.efetivado,'N') end) as efetivado,

COALESCE(receitas.id_categoria, '-1') as id_categoria,
receitas_cat.descricao as cat_nome,
receitas_cat.cor as cat_cor,
receitas_cat.icon_id as cat_icon_id,

receitas_subcat.id as subcat_id,
receitas_subcat.nome as subcat_nome,
receitas_subcat.cor as subcat_cor,
receitas_subcat.icon_id as subcat_icon_id,

{param_data_referencia} as dt

from receitas
left join filtros_contas fc on fc.id_filtro = :id_filtro
left join filtros_categorias fcg on fcg.id_filtro = :id_filtro AND ifnull(fcg.tipo, '') IN ('', 'R')
left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')

left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

left join receitas_cat on receitas_cat.id = receitas.id_categoria
left join receitas_subcat on receitas.id_subcategoria = receitas_subcat.id
left join contas on contas.id = receitas_id_conta

where (receitas.recorrencia != 'M' OR  date(receitas.data, 'start of month') <= date(dt, 'start of month'))
AND receitas.id_profile = :id_profile
AND (fc.id_conta IS NULL OR fc.id_conta = receitas_id_conta)
AND (fcg.id_subcategoria IS NULL OR (fcg.id_categoria = ifnull(receitas.id_categoria, '-1')
AND (fcg.id_subcategoria = '-1' OR fcg.id_subcategoria = receitas.id_subcategoria)))
AND ( NOT EXISTS (SELECT 1 FROM filtros_tags WHERE id_filtro = :id_filtro)
OR EXISTS (SELECT 1 FROM tags_transacoes tt JOIN filtros_tags ft ON ft.id_tag = tt.id_tag WHERE tt.id_transacao = id_origem AND ft.id_filtro = :id_filtro))
AND (receitas.data_exclusao IS NULL OR
date(strftime('%Y-%m-01',:datainicio)) <=  date(strftime('%Y-%m-01', receitas.data_exclusao)))
AND date(dt) BETWEEN date(:datainicio) and date(:datatermino)
and ifnull(receitas_fixas.excluido_mes,'N') = 'N'
{params}
)
GROUP BY id_categoria



