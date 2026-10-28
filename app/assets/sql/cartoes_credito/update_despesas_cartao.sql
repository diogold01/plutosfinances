update despesas set data =
(datetime(strftime('%Y-%m', data) ||  '-' ||
             (CASE WHEN  substr('0'|| :dia_venc, -2, 2) > strftime('%d', date(data,'start of month','+1 month','-1 day'))
              THEN   strftime('%d', date(data,'start of month','+1 month','-1 day'))
              ELSE   substr('0'|| :dia_venc, -2, 2)
              END)))
/*{conta}*/
where recorrencia != 'F'
and id_cartao_credito = :idcartao
and date(data) >= date(:data_ref)