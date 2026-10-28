INSERT INTO "objetivos" (
"color",
"data_cadastro",
"data_realizado",
"descricao",
"expec",
"icon_id",
"id",
"id_profile",
"meta",
"motivacao",
"realizado",
"saldo_inicial")
SELECT
	old.[sonhos]."color",
	old.[sonhos]."data_cadastro",
	old.[sonhos]."data_realizado",
	old.[sonhos]."descricao",
	old.[sonhos]."expec",
	old.[sonhos]."icon_id",
	old.[sonhos]."id",
	old.[sonhos]."profile_id",
	old.[sonhos]."meta",
	old.[sonhos]."motivacao",
	old.[sonhos]."realizado",
	old.[sonhos]."si"
FROM old.[sonhos];