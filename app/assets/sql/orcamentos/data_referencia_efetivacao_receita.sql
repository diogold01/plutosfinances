(CASE WHEN COALESCE( rfm.data_efetivacao, r.data_efetivacao, '') != '' THEN
COALESCE(rfm.data_efetivacao, r.data_efetivacao)
 WHEN r.recorrencia = 'M'
 THEN DATETIME(strftime('%Y-%m', mo.mes) || '-' ||
           CASE
             WHEN substr('0'|| IFNULL( rfm.dia_venc, strftime('%d', r.data)), -2, 2) >
                  strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
             THEN strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
             ELSE substr('0'|| IFNULL( rfm.dia_venc, strftime('%d', r.data)), -2, 2)
           END
         )
         ELSE r.data
END)