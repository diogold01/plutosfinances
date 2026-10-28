(CASE despesas.recorrencia WHEN 'F' THEN
 datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
 (CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
  END))
  WHEN 'M' THEN
 datetime(strftime('%Y-%m', despesas.data) ||  '-' ||
 (CASE WHEN  substr('0'|| strftime('%d', despesas.data_cadastro), -2, 2) > strftime('%d', date(despesas.data,'start of month','+1 month','-1 day'))
  THEN   strftime('%d',date(despesas.data,'start of month','+1 month','-1 day'))
  ELSE   substr('0'|| strftime('%d', despesas.data_cadastro), -2, 2)
  END))
  ELSE despesas.data_cadastro END)