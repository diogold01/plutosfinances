(CASE r.recorrencia WHEN 'M' THEN
  DATETIME(strftime('%Y-%m', mo.mes) || '-' ||
     CASE
       WHEN substr('0'|| IFNULL(rfm.dia_venc, strftime('%d', r.data)), -2, 2) >
            strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
       THEN strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
       ELSE substr('0'|| IFNULL(rfm.dia_venc, strftime('%d', r.data)), -2, 2)
     END
   )
   WHEN 'P' THEN
    datetime(strftime('%Y-%m', r.data) ||  '-' ||
    (CASE WHEN  substr('0'|| strftime('%d', r.data_cadastro), -2, 2) > strftime('%d', date(r.data,'start of month','+1 month','-1 day'))
     THEN   strftime('%d',date(r.data,'start of month','+1 month','-1 day'))
     ELSE   substr('0'|| strftime('%d', r.data_cadastro), -2, 2)
     END))
  ELSE r.data_cadastro END)