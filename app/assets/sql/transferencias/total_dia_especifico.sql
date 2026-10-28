SELECT
sum(
 round(CASE WHEN transferencias.id_profile = :id_profile
 THEN ifnull(transferencias_fixas_valor.valor, transferencias.valor)
 ELSE ifnull(transferencias_fixas_valor.valor, transferencias.valor) * COALESCE(transferencias_fixas_valor.cotacao, transferencias.cotacao, 1)
 END, 2)
) as total,
{param_data_referencia} as dt
from transferencias
LEFT JOIN transferencias_fixas as transferencias_fixas_valor on transferencias_fixas_valor.id_transferencia = transferencias.id
and date(transferencias_fixas_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month')
from transferencias_fixas where transferencias_fixas.id_transferencia = transferencias.id
and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

LEFT JOIN contas as conta_origem on conta_origem.id = ifnull(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem)
LEFT JOIN contas as conta_destino on conta_destino.id = ifnull(transferencias_fixas_valor.id_conta_destino, transferencias.id_conta_destino)

{PARAMS}