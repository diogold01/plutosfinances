(CASE despesas.recorrencia WHEN 'F' THEN
 datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
 (CASE WHEN  substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  ELSE   substr('0'|| ifnull(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
  END))
 WHEN 'M' THEN
  /* Mantem a distribuicao pelo lancamento alinhada ao intervalo usado ao salvar
     parcelas, evitando tratar recorrencias anuais ou personalizadas como mensais. */
  (CASE
    WHEN ifnull(despesas.intervalo, 30) IN (30, 0, -1) THEN
      datetime(strftime('%Y-%m',
        date(despesas.data_cadastro, 'start of month', '+' || (ifnull(despesas.num_parcela, 1) - 1) || ' month')) ||  '-' ||
      (CASE WHEN  substr('0'|| strftime('%d', despesas.data_cadastro), -2, 2) > strftime('%d', date(despesas.data_cadastro, 'start of month', '+' || (ifnull(despesas.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
       THEN   strftime('%d',date(despesas.data_cadastro, 'start of month', '+' || (ifnull(despesas.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
       ELSE   substr('0'|| strftime('%d', despesas.data_cadastro), -2, 2)
       END))
    WHEN ifnull(despesas.intervalo, 30) = 7 THEN
      datetime(date(despesas.data_cadastro, '+' || ((ifnull(despesas.num_parcela, 1) - 1) * 7) || ' days'))
    WHEN ifnull(despesas.intervalo, 30) = 90 THEN
      datetime(strftime('%Y-%m',
        date(despesas.data_cadastro, 'start of month', '+' || ((ifnull(despesas.num_parcela, 1) - 1) * 3) || ' month')) ||  '-' ||
      (CASE WHEN  substr('0'|| strftime('%d', despesas.data_cadastro), -2, 2) > strftime('%d', date(despesas.data_cadastro, 'start of month', '+' || ((ifnull(despesas.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
       THEN   strftime('%d',date(despesas.data_cadastro, 'start of month', '+' || ((ifnull(despesas.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
       ELSE   substr('0'|| strftime('%d', despesas.data_cadastro), -2, 2)
       END))
    WHEN ifnull(despesas.intervalo, 30) = 365 THEN
      datetime(date(despesas.data_cadastro, '+' || (ifnull(despesas.num_parcela, 1) - 1) || ' year'))
    ELSE
      datetime(date(despesas.data_cadastro, '+' || ((ifnull(despesas.num_parcela, 1) - 1) * ifnull(despesas.intervalo, 30)) || ' days'))
  END)
  ELSE despesas.data_cadastro END)
