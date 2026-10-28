INSERT INTO "despesas_subcat" (
"cor",
"data_exclusao",
"icon_id",
"id",
"id_categoria",
"id_profile",
"nome",
"orcamento",
"rate")
SELECT
	old.[subcat_despesas]."cor",
	old.[subcat_despesas]."data_exclusao",
	old.[subcat_despesas]."icon_id",
	old.[subcat_despesas]."id",
	old.[subcat_despesas]."idcategoria",
	old.[subcat_despesas]."profile_id",
	old.[subcat_despesas]."nome",
	old.[subcat_despesas]."orcamento",
	old.[subcat_despesas]."rate"
FROM old.[subcat_despesas];