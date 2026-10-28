(case when ((CASE WHEN ifnull(transferencias.recorrencia,'N') = 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| ifnull(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2)
 END))
 ELSE transferencias.data  END) < date(:datahoje) AND (case when ifnull(transferencias.recorrencia,'N') = 'M' and transferencias_fixas.contabilizada is null
		then 'N'
      when  ifnull(transferencias.recorrencia,'N') = 'M' and transferencias_fixas.contabilizada is not null
		then transferencias_fixas.contabilizada
	  when ifnull(transferencias.recorrencia,'N') != 'M'
		then transferencias.contabilizada
	   end ) = 'N') then 1 else 0 end) as vencida,
