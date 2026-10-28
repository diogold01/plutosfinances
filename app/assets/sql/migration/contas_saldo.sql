INSERT INTO "contas_saldo" (
"ano",
"cheque_especial",
"id_conta",
"mes",
"obs",
"si",
"si_custom")
SELECT
	old.[conta_saldo]."ano",
	old.[conta_saldo]."cheque_especial",
	old.[conta_saldo]."id_conta",
	old.[conta_saldo]."mes",
	old.[conta_saldo]."obs",
	old.[conta_saldo]."si",
	old.[conta_saldo]."si_custom"
FROM old.[conta_saldo];