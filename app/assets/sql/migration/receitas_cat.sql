INSERT INTO "receitas_cat" (
"cor",
"data_exclusao",
"descricao",
"icon_id",
"id",
"id_profile",
"not_dash",
"not_resume",
"orcamento",
"rate")
SELECT
	old.[cat_deposito]."cor",
	old.[cat_deposito]."data_exclusao",
	old.[cat_deposito]."descricao",
	old.[cat_deposito]."icon_id",
	old.[cat_deposito]."id",
	old.[cat_deposito]."profile_id",
	old.[cat_deposito]."not_dash",
	old.[cat_deposito]."not_resume",
	old.[cat_deposito]."orcamento",
	old.[cat_deposito]."rate"
FROM old.[cat_deposito];