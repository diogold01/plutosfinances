INSERT INTO "receitas_subcat" (
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
	old.[subcat_receitas]."cor",
	old.[subcat_receitas]."data_exclusao",
	old.[subcat_receitas]."icon_id",
	old.[subcat_receitas]."id",
	old.[subcat_receitas]."idcategoria",
	old.[subcat_receitas]."profile_id",
	old.[subcat_receitas]."nome",
	old.[subcat_receitas]."orcamento",
	old.[subcat_receitas]."rate"
FROM old.[subcat_receitas];