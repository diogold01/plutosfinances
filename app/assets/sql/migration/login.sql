INSERT INTO "login" (
"id",
"pwd")
SELECT
	old.[login]."id",
	old.[login]."pwd"
FROM old.[login];