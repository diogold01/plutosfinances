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
    /* Mantem a distribuicao pelo lancamento alinhada ao intervalo usado ao
       salvar parcelas, inclusive em orcamentos. */
    (CASE
      WHEN ifnull(r.intervalo, 30) IN (30, 0, -1) THEN
        datetime(strftime('%Y-%m',
          date(r.data_cadastro, 'start of month', '+' || (ifnull(r.num_parcela, 1) - 1) || ' month')) ||  '-' ||
        (CASE WHEN  substr('0'|| strftime('%d', r.data_cadastro), -2, 2) > strftime('%d', date(r.data_cadastro, 'start of month', '+' || (ifnull(r.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
         THEN   strftime('%d',date(r.data_cadastro, 'start of month', '+' || (ifnull(r.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
         ELSE   substr('0'|| strftime('%d', r.data_cadastro), -2, 2)
         END))
      WHEN ifnull(r.intervalo, 30) = 7 THEN
        datetime(date(r.data_cadastro, '+' || ((ifnull(r.num_parcela, 1) - 1) * 7) || ' days'))
      WHEN ifnull(r.intervalo, 30) = 90 THEN
        datetime(strftime('%Y-%m',
          date(r.data_cadastro, 'start of month', '+' || ((ifnull(r.num_parcela, 1) - 1) * 3) || ' month')) ||  '-' ||
        (CASE WHEN  substr('0'|| strftime('%d', r.data_cadastro), -2, 2) > strftime('%d', date(r.data_cadastro, 'start of month', '+' || ((ifnull(r.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
         THEN   strftime('%d',date(r.data_cadastro, 'start of month', '+' || ((ifnull(r.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
         ELSE   substr('0'|| strftime('%d', r.data_cadastro), -2, 2)
         END))
      WHEN ifnull(r.intervalo, 30) = 365 THEN
        datetime(date(r.data_cadastro, '+' || (ifnull(r.num_parcela, 1) - 1) || ' year'))
      ELSE
        datetime(date(r.data_cadastro, '+' || ((ifnull(r.num_parcela, 1) - 1) * ifnull(r.intervalo, 30)) || ' days'))
    END)
  ELSE r.data_cadastro END)
