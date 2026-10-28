UPDATE despesas_fixas SET excluido_mes = 'N' WHERE id_despesa = :id_despesa and date(data)
 between date(strftime('%Y-%m-01',:data))
 and date(:data,'start of month','+1 month','-1 day')