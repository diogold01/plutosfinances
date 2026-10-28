SELECT
contas_saldo.id_conta,
contas_saldo.mes,
contas_saldo.ano,
contas_saldo.si,
ifnull(contas_saldo.si_custom, 'N') as si_custom,
ifnull(contas_saldo.cheque_especial,0)   as cheque_especial,
contas_saldo.obs
FROM contas_saldo
WHERE
contas_saldo.id_conta = :id_conta
and mes = :mes
and ano = :ano
GROUP BY contas_saldo.id_conta




