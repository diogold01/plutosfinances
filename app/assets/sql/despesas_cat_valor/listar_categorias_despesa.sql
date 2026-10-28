SELECT
catmap.id,
catmap.id_despesa,
catmap.id_categoria,
catmap.id_subcategoria,
catmap.valor,
catmap.obs,
catmap.excluido,
(CASE despesas.recorrencia WHEN 'F' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', catmap.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', catmap.data)), -2, 2)
 END))
 ELSE catmap.data END) AS data,
catmap.data as data_original,
despesas_cat.id AS cat_id,
despesas_cat.nome AS cat_nome,
despesas_cat.cor AS cat_cor,
despesas_cat.icon_id AS cat_icon_id,

despesas_subcat.id AS subcat_id,
despesas_subcat.nome AS subcat_nome,
despesas_subcat.cor AS subcat_cor,
despesas_subcat.icon_id AS subcat_icon_id

FROM
 despesas_cat_valor AS catmap
 INNER JOIN despesas ON despesas.id = catmap.id_despesa
 INNER JOIN despesas_cat ON despesas_cat.id = catmap.id_categoria
 INNER JOIN despesas_subcat ON despesas_subcat.id = catmap.id_subcategoria
 LEFT JOIN despesas_fixas AS despesas_fixas_valor ON despesas_fixas_valor.id_despesa = despesas.id
    AND DATE(despesas_fixas_valor.data, 'start of month')  = (SELECT DATE(MAX(despesas_fixas.data),'start of month') FROM despesas_fixas WHERE id_despesa = despesas.id
    AND DATE(despesas_fixas.data, 'start of month') <= DATE(:datainicio, 'start of month'))

WHERE
catmap.id_despesa = :id_despesa
AND (despesas.recorrencia != 'F' OR
    (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
     AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(ifnull(obs, '')) = LOWER(ifnull(catmap.obs,''))
     AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
     AND catmap.excluido != 'S'))
ORDER BY catmap.valor

