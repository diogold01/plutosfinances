select
ifnull(cartoes_credito_mes.dia_venc,cartoes_credito.dia_venc) as dia_venc
from cartoes_credito
left join cartoes_credito_mes on date(cartoes_credito_mes.ano || '-' || substr('0' || cartoes_credito_mes.mes, -2, 2) ||  '-01') =
(select  max(date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01'))
from cartoes_credito_mes
where date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01') <= date(:datainicio, 'start of month')
and id_cartao = cartoes_credito.id)
and cartoes_credito_mes.id_cartao  = cartoes_credito.id
WHERE
cartoes_credito.id  = :idcartao