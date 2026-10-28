INSERT INTO "contas_cat" (
"cor",
"descricao",
"icon_id",
"id",
"id_profile",
"not_balance",
"not_dash",
"not_resume",
"padrao",
"rate")

select
old.[tipos_ganho].cor,
old.[tipos_ganho].descricao,
old.[tipos_ganho].icon_id,
old.[tipos_ganho].id,
old.[tipos_ganho].profile_id,
old.[tipos_ganho].not_balance,
old.[tipos_ganho].not_dash,
old.[tipos_ganho].not_resume,
old.[tipos_ganho].padrao,
old.[tipos_ganho].rate
FROM
old.[tipos_ganho];
