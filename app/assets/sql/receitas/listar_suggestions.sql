select
receitas.id_origem as idori,
coalesce(receitas_fixas_valor.valor, receitas.valor) as val,
coalesce(receitas_fixas.id_conta, receitas.id_conta) as receitas_id_conta,
receitas.descricao as descr,
receitas.id_profile as id_profile,

contas.descricao as conta_desc,
contas_cat.id as conta_id_categoria,
COALESCE(contas.currency,'') as conta_currency,
contas_cat.descricao as conta_cat_descricao,
coalesce(contas_cat.cor, 0) as conta_cat_cor,
coalesce(contas.somar_total,'S') as conta_somar,

coalesce(receitas.id_categoria, '-1') as cat_id,
receitas_cat.descricao as cat_nome,
receitas_cat.cor as cat_cor,
receitas_cat.icon_id as cat_icon,

receitas_subcat.id as subcat_id,
receitas_subcat.nome as subcat_nome,
receitas_subcat.cor as subcat_cor,
receitas_subcat.icon_id as subcat_icon

from receitas
left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(coalesce(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
inner join receitas_cat on receitas_cat.id = receitas.id_categoria
inner join receitas_subcat on receitas.id_subcategoria = receitas_subcat.id
inner join contas on contas.id = coalesce(receitas_fixas_valor.id_conta, receitas.id_conta) and (contas.data_exclusao IS NULL OR
                                                                                             date(strftime('%Y-%m-01',:datainicio)) <=
                                                                                             date(strftime('%Y-%m-01', contas.data_exclusao)))
left join contas_cat on contas_cat.id = contas.id_categoria
left join sugestoes_ignore on sugestoes_ignore.desc = lower(descr) and type = 'R' and sugestoes_ignore.id_profile = receitas.id_profile
WHERE sugestoes_ignore.desc is null
AND receitas.id_profile = :id_profile
{group}
HAVING MAX(receitas.data_cadastro)
ORDER BY receitas.data_cadastro DESC
limit 500