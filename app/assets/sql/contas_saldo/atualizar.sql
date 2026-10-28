update contas_saldo
set
si = :si,
obs = :obs,
cheque_especial = :cheque_especial
where
id_conta = :id_conta
and mes = :mes
and ano = :ano