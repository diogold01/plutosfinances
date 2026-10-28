INSERT INTO "receitas_fixas" (
"attach_id",
"attach_path",
"data",
"data_efetivacao",
"dia_venc",
"efetivado",
"excluido_mes",
"id",
"id_conta",
"id_receita",
"obs",
"valor")
SELECT
    old.[deposito_mensal]."drive_id_photo",
    old.[deposito_mensal]."path_photo",
	old.[deposito_mensal]."data",
	COALESCE(old.[deposito_mensal]."data_efetivacao", old.[deposito_mensal]."data_recebimento"),
	old.[deposito_mensal]."dia_venc",
	old.[deposito_mensal]."recebido",
	old.[deposito_mensal]."excluido_mes",
	old.[deposito_mensal]."id",
	old.[deposito_mensal]."id_conta",
	old.[deposito_mensal]."iddep",
	old.[deposito_mensal]."obs",
	old.[deposito_mensal]."valor"
FROM old.[deposito_mensal];