SELECT SUM(total) as total FROM (
SELECT
(SUM(catmap.valor) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as total,
(datetime(strftime('%Y',:datainicio) || '-' || strftime('%m',:datainicio) ||  '-' ||
          (CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
          THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
           ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
           END))) as dt,
 despesas.data as dtoriginal,
(case when despesas_fixas.status is null
then 'pd'
when  despesas_fixas.status is not null
then despesas_fixas.status
end ) as st
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
st = 'pd'
and despesas.recorrencia = 'F'
and ifnull(despesas_fixas.excluido_mes,'N') = 'N'
and (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month') )
AND date(dt) between date(strftime('%Y-%m-01',:datainicio))
and date(:datainicio,'start of month','+1 month','-1 day','23:59:59')
AND (despesas.data_exclusao IS NULL OR
        date(strftime('%Y-%m-01',:datainicio)) <=
        date(strftime('%Y-%m-01', despesas.data_exclusao)))
and ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) = :idcartao
group by catmap.id_despesa)

