INSERT INTO "sugestoes_ignore" (
"desc",
"id_profile",
"type")
SELECT
	old.[sug_del]."desc",
	old.[sug_del]."profile_id",
	old.[sug_del]."type"
FROM old.[sug_del];