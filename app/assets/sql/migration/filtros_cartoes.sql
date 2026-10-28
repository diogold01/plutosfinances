INSERT INTO "filtros_cartoes" (
"id_cartao",
"id_filtro")
SELECT
	old.[filtros_cartoes]."id_cartao",
	old.[filtros_cartoes]."id_filtro"
FROM old.[filtros_cartoes];