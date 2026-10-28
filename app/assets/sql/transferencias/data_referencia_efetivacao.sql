(CASE WHEN transferencias.recorrencia = 'M'
THEN
COALESCE(transferencias_fixas.data_efetivacao, DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2)
END)))
ELSE COALESCE(transferencias.data_efetivacao, transferencias.data)  END)