(case when ((CASE receitas.recorrencia WHEN 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| ifnull(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
 END))
 ELSE receitas.data  END) < date(:datahoje) AND (case when receitas.recorrencia = 'M' and receitas_fixas.efetivado is null
		then 'N'
      when  receitas.recorrencia = 'M' and receitas_fixas.efetivado is not null
		then receitas_fixas.efetivado
	  when receitas.recorrencia != 'M'
		then receitas.efetivado
	   end ) = 'N') then 1 else 0 end) as vencida,
