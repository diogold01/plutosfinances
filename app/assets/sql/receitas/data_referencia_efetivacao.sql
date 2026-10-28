(CASE WHEN receitas.recorrencia = 'M'
THEN
COALESCE(receitas_fixas.data_efetivacao, DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
END)))
ELSE COALESCE(receitas.data_efetivacao, receitas.data)  END)