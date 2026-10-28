update contas_saldo
set
si = :si,
si_custom = 'N',
obs = :obs,
cheque_especial = :cheque_especial
where
id_conta = :id_conta
and mes = :mes
and ano = :ano