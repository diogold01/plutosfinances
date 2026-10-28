(CASE WHEN COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) != '-1'
THEN
(CASE despesas.recorrencia WHEN 'F' THEN
DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
END))
ELSE
DATETIME(strftime('%Y-%m', despesas.data) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(cartao_mes.dia_venc, cartoes_credito.dia_venc), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| ifnull(cartao_mes.dia_venc, cartoes_credito.dia_venc), -2, 2)
END)) END)
ELSE
(CASE despesas.recorrencia WHEN 'F' THEN
DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
END))
ELSE despesas.data END)
END)