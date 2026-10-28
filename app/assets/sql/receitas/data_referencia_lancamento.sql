(CASE receitas.recorrencia WHEN 'M' THEN
DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
END))
WHEN 'P' THEN
 DATETIME(strftime('%Y-%m', receitas.data) ||  '-' ||
 (CASE WHEN  substr('0'|| strftime('%d', receitas.data_cadastro), -2, 2) > strftime('%d',date(receitas.data,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(receitas.data,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| strftime('%d', receitas.data_cadastro), -2, 2)
 END))
ELSE receitas.data_cadastro  END)