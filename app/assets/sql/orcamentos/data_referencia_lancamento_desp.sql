(CASE d.recorrencia WHEN 'F' THEN
  DATETIME(strftime('%Y-%m', mo.mes) || '-' ||
     CASE
       WHEN substr('0'|| IFNULL(dfm.dia_venc, strftime('%d', d.data)), -2, 2) >
            strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
       THEN strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
       ELSE substr('0'|| IFNULL(dfm.dia_venc, strftime('%d', d.data)), -2, 2)
     END
   )
   WHEN 'M' THEN
    datetime(strftime('%Y-%m', d.data) ||  '-' ||
    (CASE WHEN  substr('0'|| strftime('%d', d.data_cadastro), -2, 2) > strftime('%d', date(d.data,'start of month','+1 month','-1 day'))
     THEN   strftime('%d',date(d.data,'start of month','+1 month','-1 day'))
     ELSE   substr('0'|| strftime('%d', d.data_cadastro), -2, 2)
     END))
  ELSE d.data_cadastro END)