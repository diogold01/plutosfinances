INSERT INTO "cartoes_credito_mes" (
"ano",
"attach_id",
"attach_path",
"conta_vinculada",
"dia_fecha",
"dia_venc",
"fatura_paga",
"id_cartao",
"id_conta",
"limite",
"mes")
SELECT
	old.[cartao_credito_mes]."ano",
	old.[cartao_credito_mes]."attach_drive_id",
	old.[cartao_credito_mes]."attach_path",
	old.[cartao_credito_mes]."conta_vinculada",
	old.[cartao_credito_mes]."dia_fecha",
	old.[cartao_credito_mes]."dia_venc",
	old.[cartao_credito_mes]."fatura_paga",
	old.[cartao_credito_mes]."id_cartao",
	old.[cartao_credito_mes]."id_conta",
	old.[cartao_credito_mes]."limite",
	old.[cartao_credito_mes]."mes"
FROM old.[cartao_credito_mes];