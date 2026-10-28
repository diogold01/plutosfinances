UPDATE receitas_fixas set excluido_mes = 'N' WHERE id_receita = :id_receita and date(data)
 between date(strftime('%Y-%m-01',:data))
 and date(:data,'start of month','+1 month','-1 day')