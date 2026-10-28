(CASE WHEN COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito, '-1') ='-1' AND
COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao, '') != '' THEN
COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao)
WHEN despesas.recorrencia = 'F'
THEN DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
END))
ELSE despesas.data END)