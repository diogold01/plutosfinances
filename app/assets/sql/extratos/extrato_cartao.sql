select
(CASE WHEN val > 0 THEN
'deb' ELSE  'cred' END) op,
id,
id_origem,
id_profile,
tipo,
rec,
val,
num_cats,
data_lanc,
dt,
descr,
efetivado,
cat_cor,
cat_icon,
cat_id,
subcat_cor,
subcat_icon,
subcat_id,
cat_nome,
subcat_nome,
conta_desc,
obs,
adiantamento_fatura,
somar
 FROM
(SELECT
'g' as tipo,
despesas.id,
despesas.id_origem,
despesas.id_profile,
despesas.recorrencia as rec,
contas.descricao as conta_desc,
despesas_cat.id as cat_id,
despesas_cat.cor as cat_cor,
despesas_cat.nome as cat_nome,
despesas_cat.icon_id as cat_icon,
despesas_subcat.id as subcat_id,
despesas_subcat.nome as subcat_nome,
despesas_subcat.cor as subcat_cor,
despesas_subcat.icon_id as subcat_icon,
((round(SUM(catmap.valor),2) + COALESCE(despesas_fixas.juros, despesas.juros, 0))
* COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1)) as val,
COUNT(catmap.valor) as num_cats,
(CASE despesas.recorrencia WHEN 'F' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
 END))
 ELSE despesas.data  END) as dt,
 COALESCE(despesas_fixas_valor.data_cadastro, despesas.data_cadastro) data_lanc,

 (despesas.descricao || (CASE WHEN despesas.recorrencia = 'M' THEN ' ' || despesas.num_parcela || '/' || despesas.num_parcelas ELSE '' END)) as descr,

  (case when (case when despesas.recorrencia = 'F' and despesas_fixas.status is null
  		then 'pd'
        when  despesas.recorrencia = 'F' and despesas_fixas.status is not null
  		then despesas_fixas.status
  	  when despesas.recorrencia != 'F'
  		then despesas.status
  	   end ) = 'pd' then 'N' else 'S' end) as efetivado,
COALESCE(despesas_fixas.obs, despesas_fixas_valor.obs_futura, despesas.obs) as obs,
coalesce(despesas.adiantamento_fatura, 'N') as adiantamento_fatura,
(case when ifnull(contas.somar_total,'S') = 'N' THEN 'N' ELSE
ifnull(despesas.somar_total,'S') END) as somar
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
left join despesas_cat on despesas_cat.id = catmap.id_categoria
left join despesas_subcat on despesas_subcat.id = catmap.id_subcategoria
left join contas on contas.id = COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta)
WHERE
(despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
and COALESCE(despesas_fixas.excluido_mes,'N') = 'N'
AND (despesas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', despesas.data_exclusao)))
AND date(dt) BETWEEN date(:datainicio) and date(:datafim)
and COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) = :id_cartao
GROUP BY catmap.id_despesa
)
where 0=0
