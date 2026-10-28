SELECT
transferencias.id,
transferencias.id_origem as idori,
transferencias.descricao,
transferencias.id_profile,
ifnull(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem) as de,
ifnull(transferencias_fixas_valor.id_conta_destino, transferencias.id_conta_destino) as para,
ifnull(transferencias_fixas_valor.valor, transferencias.valor) as val,
conta_origem.descricao as gan_de,
conta_origem.id_profile as id_profile_origem,
coalesce(conta_origem.currency, pr_origem.currency, '') as currency_origem,

conta_destino.id_profile as id_profile_destino,
ifnull(conta_origem.image_id, 0) as image_id_de,
conta_destino.descricao as gan_para,
ifnull(conta_destino.image_id, 0) as image_id_para,
coalesce(conta_destino.currency, pr_destino.currency, '') as currency_destino

from transferencias
LEFT JOIN transferencias_fixas on transferencias.id = transferencias_fixas.id_transferencia
and date(ifnull(transferencias_fixas.data, transferencias.data), 'start of month') = date(:datainicio, 'start of month')

LEFT JOIN transferencias_fixas as transferencias_fixas_valor on transferencias_fixas_valor.id_transferencia = transferencias.id
and date(transferencias_fixas_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month')
from transferencias_fixas where transferencias_fixas.id_transferencia = transferencias.id
and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

LEFT JOIN contas as conta_origem on conta_origem.id = ifnull(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem)
LEFT JOIN profiles as pr_origem on pr_origem.id = conta_origem.id_profile

LEFT JOIN contas as conta_destino on conta_destino.id = ifnull(transferencias_fixas_valor.id_conta_destino, transferencias.id_conta_destino)
LEFT JOIN profiles as pr_destino on pr_destino.id = conta_destino.id_profile

left join sugestoes_ignore on sugestoes_ignore.desc = lower(transferencias.descricao) and type = 'T' and sugestoes_ignore.id_profile = transferencias.id_profile
WHERE sugestoes_ignore.desc is null
AND transferencias.id_profile = :id_profile
GROUP BY conta_origem.id, conta_destino.id, transferencias.descricao
HAVING MAX(transferencias.data)
ORDER BY transferencias.data DESC
limit 500