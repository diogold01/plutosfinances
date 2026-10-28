INSERT INTO "despesas_cat" (
"cor",
"data_exclusao",
"icon_id",
"id",
"id_profile",
"nome",
"not_balance",
"not_dash",
"not_resume",
"orcamento",
"rate")
SELECT
	old.[cat_despesas]."cor",
	old.[cat_despesas]."data_exclusao",
	old.[cat_despesas]."icon_id",
	old.[cat_despesas]."id",
	old.[cat_despesas]."profile_id",
	old.[cat_despesas]."nome",
	old.[cat_despesas]."not_balance",
	old.[cat_despesas]."not_dash",
	old.[cat_despesas]."not_resume",
	old.[cat_despesas]."orcamento",
	old.[cat_despesas]."rate"
FROM old.[cat_despesas];