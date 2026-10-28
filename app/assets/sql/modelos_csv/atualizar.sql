update modelos_csv set
id_conta = :id_conta,
id_cartao = :id_cartao,
valor_negativo_despesas = :valor_negativo_despesas,
separador = :separador,
possui_cabecalho = :possui_cabecalho,
formato_data = :formato_data,
observacoes = :observacoes,
descricao = :descricao
where id = :id