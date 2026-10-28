SELECT * FROM (SELECT
despesas.id_origem as idori,
COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta) as despesas_id_conta,
despesas.descricao as descr,
 COALESCE(despesas_fixas_valor.data_cadastro, despesas.data_cadastro) data_cadastro,
despesas.id_profile as despesas_id_profile,
SUM(catmap.valor) as val,
COUNT(catmap.valor) as num_cats,
COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as card_id,

(CASE WHEN
COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito, '-1') != '-1'
THEN 1 ELSE 0 END) as despesa_cartao,

contas.descricao as conta_desc,

contas_cat.descricao as conta_cat_descricao,
COALESCE(contas_cat.cor, 0) as conta_cat_cor,
contas_cat.id as conta_id_categoria,

COALESCE(contas.currency,'') as conta_currency,
COALESCE(contas.somar_total,'S') as conta_somar,

despesas_cat.id as cat_id,
despesas_cat.nome as cat_nome,
despesas_cat.cor as cat_cor,
despesas_cat.icon_id as cat_icon,

despesas_subcat.id as subcat_id,
despesas_subcat.nome as subcat_nome,
despesas_subcat.cor as subcat_cor,
COALESCE(despesas_subcat.icon_id, 955) as subcat_icon,

cartoes_credito.nome           as card_nome,
cartoes_credito.img_id         as card_img

FROM despesas
inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
   AND (despesas.recorrencia != 'F' OR
       (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
        AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(COALESCE(obs, '')) = LOWER(COALESCE(catmap.obs,''))
        AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
        AND catmap.excluido != 'S'))
left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(COALESCE(despesas_fixas.data,despesas.data), 'start of month') = date(:datainicio, 'start of month')
left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join contas on contas.id = despesas_id_conta and (contas.data_exclusao IS NULL OR
                                             date(strftime('%Y-%m-01',:datainicio)) <=
                                             date(strftime('%Y-%m-01', contas.data_exclusao)))
left join contas_cat on contas_cat.id = contas.id_categoria
inner join despesas_cat on catmap.id_categoria = despesas_cat.id
inner join despesas_subcat on catmap.id_subcategoria = despesas_subcat.id
left join cartoes_credito on cartoes_credito.id = card_id
left join sugestoes_ignore on sugestoes_ignore.desc = lower(descr) and type = 'D' and sugestoes_ignore.id_profile = despesas.id_profile
WHERE sugestoes_ignore.desc is null
AND despesas_id_profile = :id_profile
GROUP BY  catmap.id_despesa
HAVING num_cats = 1)
{group}
HAVING val >= 0 AND MAX(data_cadastro)
{order}
limit 500