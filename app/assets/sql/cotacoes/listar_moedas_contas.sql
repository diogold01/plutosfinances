select distinct contas.currency from contas
inner join profiles on profiles.id = contas.id_profile
AND profiles.currency != contas.currency
AND contas.currency != ''
and profiles.currency = :profile_currency