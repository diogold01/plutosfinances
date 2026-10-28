UPDATE transferencias SET
descricao = :descricao,
valor = :valor,
id_conta_origem = :id_conta_origem,
id_conta_destino = :id_conta_destino,
num_parcelas = :num_parcelas,
attach_id = :attach_id,
attach_path = :attach_path,
attach_size = :attach_size,
cotacao = :cotacao,
obs = :obs,
ef_auto = :ef_auto,
id_profile = :id_profile,
ef_inicio_dia = :ef_inicio_dia,
data_cadastro = :data_cadastro,
ultima_modificacao = :ultima_modificacao,
id_open_finance_transaction_origem = :id_open_finance_transaction_origem,
id_open_finance_transaction_destino = :id_open_finance_transaction_destino,
descricao_open_finance = :descricao_open_finance,
sugerir_descricao = :sugerir_descricao,
data =   CASE
          -- se for para manter a data original
          WHEN :manter_data = 'S' THEN data
          -- Verifica se o dia especificado é maior que o último dia do mês resultante
          WHEN strftime('%d', date(data, printf({month_change}), 'start of month', '+1 month', '-1 day')) < strftime('%d', :data_vencimento) THEN
              -- Se for, ajusta para o último dia do mês
              date(data, printf({month_change}), 'start of month', '+1 month', '-1 day')
          ELSE
              -- Caso contrário, define o dia especificado
              date(data, printf({month_change}), 'start of month', printf('+%d days', strftime('%d', :data_vencimento) - 1))
          END
WHERE id_origem = :id_origem
