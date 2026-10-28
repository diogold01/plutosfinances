UPDATE transferencias_fixas set excluido_mes = 'N' WHERE transferencias_fixas.id_transferencia = :id_transferencia
 and date(data)
 between date(strftime('%Y-%m-01',:data))
 and date(:data,'start of month','+1 month','-1 day')