INSERT INTO "filtros_categorias" (
"id_categoria",
"id_filtro",
"id_subcategoria")
SELECT
	old.[filtros_categorias]."id_categoria",
	old.[filtros_categorias]."id_filtro",
	old.[filtros_categorias]."id_subcategoria"
FROM old.[filtros_categorias];