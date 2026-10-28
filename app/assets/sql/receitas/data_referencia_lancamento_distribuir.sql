(CASE receitas.recorrencia WHEN 'M' THEN
DATETIME(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
END))
WHEN 'P' THEN
 /* Mantem a distribuicao pelo lancamento alinhada ao intervalo usado ao salvar
    parcelas, evitando tratar recorrencias anuais ou personalizadas como mensais. */
 (CASE
   WHEN ifnull(receitas.intervalo, 30) IN (30, 0, -1) THEN
     DATETIME(strftime('%Y-%m',
       date(receitas.data_cadastro, 'start of month', '+' || (ifnull(receitas.num_parcela, 1) - 1) || ' month')) ||  '-' ||
     (CASE WHEN  substr('0'|| strftime('%d', receitas.data_cadastro), -2, 2) > strftime('%d',date(receitas.data_cadastro, 'start of month', '+' || (ifnull(receitas.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
     THEN   strftime('%d',date(receitas.data_cadastro, 'start of month', '+' || (ifnull(receitas.num_parcela, 1) - 1) || ' month','+1 month','-1 day'))
     ELSE   substr('0'|| strftime('%d', receitas.data_cadastro), -2, 2)
     END))
   WHEN ifnull(receitas.intervalo, 30) = 7 THEN
     DATETIME(date(receitas.data_cadastro, '+' || ((ifnull(receitas.num_parcela, 1) - 1) * 7) || ' days'))
   WHEN ifnull(receitas.intervalo, 30) = 90 THEN
     DATETIME(strftime('%Y-%m',
       date(receitas.data_cadastro, 'start of month', '+' || ((ifnull(receitas.num_parcela, 1) - 1) * 3) || ' month')) ||  '-' ||
     (CASE WHEN  substr('0'|| strftime('%d', receitas.data_cadastro), -2, 2) > strftime('%d',date(receitas.data_cadastro, 'start of month', '+' || ((ifnull(receitas.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
     THEN   strftime('%d',date(receitas.data_cadastro, 'start of month', '+' || ((ifnull(receitas.num_parcela, 1) - 1) * 3) || ' month','+1 month','-1 day'))
     ELSE   substr('0'|| strftime('%d', receitas.data_cadastro), -2, 2)
     END))
   WHEN ifnull(receitas.intervalo, 30) = 365 THEN
     DATETIME(date(receitas.data_cadastro, '+' || (ifnull(receitas.num_parcela, 1) - 1) || ' year'))
   ELSE
     DATETIME(date(receitas.data_cadastro, '+' || ((ifnull(receitas.num_parcela, 1) - 1) * ifnull(receitas.intervalo, 30)) || ' days'))
 END)
ELSE receitas.data_cadastro  END)
