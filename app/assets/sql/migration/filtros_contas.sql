INSERT INTO "filtros_contas" (
"id_conta",
"id_filtro",
"tipo_conta")
SELECT
	old.[filtros_contas]."id_conta",
	old.[filtros_contas]."id_filtro",
	old.[filtros_contas]."tipo_conta"
FROM old.[filtros_contas];