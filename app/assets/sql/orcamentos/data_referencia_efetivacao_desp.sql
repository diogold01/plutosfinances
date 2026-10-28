(CASE WHEN COALESCE(dfm.id_cartao_credito, d.id_cartao_credito, '-1') ='-1' AND
COALESCE(dfm.data_efetivacao, d.data_efetivacao, '') != '' THEN
COALESCE(dfm.data_efetivacao, d.data_efetivacao)
 WHEN d.recorrencia = 'F'
 THEN DATETIME(strftime('%Y-%m', mo.mes) || '-' ||
           CASE
             WHEN substr('0'|| IFNULL(dfm.dia_venc, strftime('%d', d.data)), -2, 2) >
                  strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
             THEN strftime('%d', date(mo.mes,'start of month','+1 month','-1 day'))
             ELSE substr('0'|| IFNULL(dfm.dia_venc, strftime('%d', d.data)), -2, 2)
           END
         )
         ELSE d.data
END)