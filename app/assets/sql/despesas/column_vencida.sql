(case when ((CASE despesas.recorrencia WHEN 'F' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
 END))
 ELSE despesas.data  END) < date(:datahoje) AND (case when despesas.recorrencia = 'F' and despesas_fixas.status is null
		then 'pd'
      when  despesas.recorrencia = 'F' and despesas_fixas.status is not null
		then despesas_fixas.status
	  when despesas.recorrencia != 'F'
		then despesas.status
	   end ) = 'pd') then 1 else 0 end) as vencida,
