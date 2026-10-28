UPDATE receitas SET
descricao = :descricao,
valor = :valor,
cotacao = :cotacao,
num_parcelas = :num_parcelas,
obs = :obs,
id_categoria = :id_categoria,
id_subcategoria = :id_subcategoria,
id_conta  = :id_conta,
somar_total = :somar_total,
ignore_orc = :ignore_orc,
attach_id = :attach_id,
attach_path = :attach_path,
attach_size = :attach_size,
considerar_estatistica = :considerar_estatistica,
economia_mensal = :economia_mensal,
id_profile = :id_profile,
ef_auto = :ef_auto,
ef_inicio_dia = :ef_inicio_dia,
data_cadastro = :data_cadastro,
ultima_modificacao = :ultima_modificacao,
id_open_finance_transaction = :id_open_finance_transaction,
descricao_open_finance = :descricao_open_finance,
category_open_finance = :category_open_finance,
regra_efetivacao_parcial_open_finance = :regra_efetivacao_parcial_open_finance,
valor_parcial_open_finance = :valor_parcial_open_finance,
reconhecer_valor_diferente = :reconhecer_valor_diferente,
reconhecer_data_diferente = :reconhecer_data_diferente,
buscar_similares = :buscar_similares,
sugerir_descricao = :sugerir_descricao,
lembrete_vencimento = :lembrete_vencimento,
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
