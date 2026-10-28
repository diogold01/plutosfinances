INSERT INTO "orcamentos_mensal" (
"data",
"efet",
"id_orcamento",
"meta",
"pend")
SELECT
	old.[orcamentos_mensal]."data",
	old.[orcamentos_mensal]."efet",
	old.[orcamentos_mensal]."id",
	old.[orcamentos_mensal]."meta",
	old.[orcamentos_mensal]."pend"
FROM old.[orcamentos_mensal];