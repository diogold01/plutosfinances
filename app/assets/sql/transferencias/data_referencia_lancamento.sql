(CASE transferencias.recorrencia WHEN 'M' THEN
DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2)
END))
WHEN 'P' THEN
 DATETIME(strftime('%Y-%m', transferencias.data) ||  '-' ||
 (CASE WHEN  substr('0'|| strftime('%d', transferencias.data_cadastro), -2, 2) > strftime('%d',date(transferencias.data,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(transferencias.data,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| strftime('%d', transferencias.data_cadastro), -2, 2)
 END))
ELSE transferencias.data_cadastro  END)