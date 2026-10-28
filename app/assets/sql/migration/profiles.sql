INSERT INTO "profiles" (
"archived",
"color",
"current",
"icon",
"id",
"name")
SELECT
	old.[profile]."archived",
	old.[profile]."color",
	old.[profile]."current",
	old.[profile]."icon",
	old.[profile]."id",
	old.[profile]."name"
FROM old.[profile];