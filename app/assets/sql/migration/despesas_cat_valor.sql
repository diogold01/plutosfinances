INSERT INTO "despesas_cat_valor" (
"data",
"excluido",
"id",
"id_categoria",
"id_despesa",
"id_subcategoria",
"obs",
"valor")
SELECT
	old.[categoria_valor_desp]."data",
	old.[categoria_valor_desp]."excluido",
	old.[categoria_valor_desp]."id",
	old.[categoria_valor_desp]."id_categoria",
	old.[categoria_valor_desp]."id_despesa",
	old.[categoria_valor_desp]."id_subcategoria",
	old.[categoria_valor_desp]."obs",
	old.[categoria_valor_desp]."valor"
FROM old.[categoria_valor_desp];