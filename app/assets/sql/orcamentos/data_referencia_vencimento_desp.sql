(CASE WHEN d.recorrencia = 'F' THEN
DATETIME(strftime('%Y-%m', mo.mes) || '-' ||
   CASE
     WHEN substr('0'|| IFNULL(dfm.dia_venc, strftime('%d', d.data)), -2, 2) >
          strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
     THEN strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
     ELSE substr('0'|| IFNULL(dfm.dia_venc, strftime('%d', d.data)), -2, 2)
   END
 )
ELSE d.data END)