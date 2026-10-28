INSERT INTO "objetivos_dep" (
"data",
"id",
"id_objetivo",
"mensal",
"obs",
"valor")
SELECT
	old.[sonhos_dep]."data",
	old.[sonhos_dep]."id",
	old.[sonhos_dep]."id_sonho",
	old.[sonhos_dep]."mensal",
	old.[sonhos_dep]."obs",
	old.[sonhos_dep]."valor"
FROM old.[sonhos_dep];
