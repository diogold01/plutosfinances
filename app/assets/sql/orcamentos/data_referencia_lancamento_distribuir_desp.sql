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
    /* Mantem a distribuicao pelo lancamento alinhada ao intervalo usado ao
       salvar parcelas, inclusive em orcamentos. */
    (CASE
      WHEN ifnull(d.intervalo, 30) IN (30, 0, -1) THEN
        datetime(strftime('%Y-%m',
          date(d.data_cadastro, 'start of month', '+' || (ifnull(d.num_parcela, 1) - 1) || ' month')) ||  '-' ||
        (CASE WHEN  substr('0'|| strftime('%d', d.data_cadastro), -2, 2) > strftime('%d', date(d.data_cadastro, 'start of month', '+' || (ifnull(d.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
         THEN   strftime('%d',date(d.data_cadastro, 'start of month', '+' || (ifnull(d.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
         ELSE   substr('0'|| strftime('%d', d.data_cadastro), -2, 2)
         END))
      WHEN ifnull(d.intervalo, 30) = 7 THEN
        datetime(date(d.data_cadastro, '+' || ((ifnull(d.num_parcela, 1) - 1) * 7) || ' days'))
      WHEN ifnull(d.intervalo, 30) = 90 THEN
        datetime(strftime('%Y-%m',
          date(d.data_cadastro, 'start of month', '+' || ((ifnull(d.num_parcela, 1) - 1) * 3) || ' month')) ||  '-' ||
        (CASE WHEN  substr('0'|| strftime('%d', d.data_cadastro), -2, 2) > strftime('%d', date(d.data_cadastro, 'start of month', '+' || ((ifnull(d.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
         THEN   strftime('%d',date(d.data_cadastro, 'start of month', '+' || ((ifnull(d.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
         ELSE   substr('0'|| strftime('%d', d.data_cadastro), -2, 2)
         END))
      WHEN ifnull(d.intervalo, 30) = 365 THEN
        datetime(date(d.data_cadastro, '+' || (ifnull(d.num_parcela, 1) - 1) || ' year'))
      ELSE
        datetime(date(d.data_cadastro, '+' || ((ifnull(d.num_parcela, 1) - 1) * ifnull(d.intervalo, 30)) || ' days'))
    END)
  ELSE d.data_cadastro END)
