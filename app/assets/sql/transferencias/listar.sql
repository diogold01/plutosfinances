SELECT
transferencias.descricao as descr,
transferencias.id as transf_id,
transferencias.id_profile,
transferencias.id_provider,
transferencias.id_open_finance_transaction_origem,
transferencias.id_open_finance_transaction_destino,
transferencias.descricao_open_finance,
COALESCE(transferencias.sugerir_descricao, 'S') as sugerir_descricao,
ifnull(transferencias.id_origem, transferencias.id) as idori,
ifnull(transferencias.num_parcela, 1) as numpar,
ifnull(transferencias.num_parcelas, 0) as numpars,
ifnull(transferencias.recorrencia, 'N') as rec,
ifnull(transferencias_fixas.attach_id, transferencias.attach_id) as attach_id,
ifnull(transferencias_fixas.attach_path, transferencias.attach_path) as attach_path,
COALESCE(transferencias_fixas.cotacao, transferencias.cotacao, 1) as cotacao,
coalesce(transferencias_fixas.attach_size, transferencias.attach_size, 0) as attach_size,
ifnull(transferencias.intervalo, 0)   as intervalo,
ifnull(transferencias.ef_auto, 'N')   as efetivar_auto,
ifnull(transferencias.ef_inicio_dia, 'N')   as ef_inicio_dia,
0 as encargos,
ifnull(transferencias_fixas.excluido_mes,'N') as excluido,
transferencias.data_exclusao  as dt_exclusao,
transferencias.data as dtoriginal,
transferencias.data_registro_of as dt_registro_of,
transferencias.ultima_modificacao as ultima_modificacao,
conta_origem.descricao as gan_de,
conta_origem.id_profile as conta_de_id_profile,
conta_origem.somar_total as conta_origem_somar,
ifnull(conta_origem.image_id, 0) as conta_origem_image_id,
conta_origem.id_item as conta_origem_id_item,
conta_origem.id_open_finance_account as conta_origem_id_open_finance_account,
coalesce(conta_origem.image_url, ofi_origem.image_url) as conta_origem_image_url,
coalesce(conta_origem.currency, pr_origem.currency, '') as currency_origem,

conta_destino.descricao as gan_para,
conta_destino.somar_total as conta_destino_somar,
conta_destino.id_profile as conta_para_id_profile,
ifnull(conta_destino.image_id, 0) as conta_destino_image_id,
conta_destino.id_item as conta_destino_id_item,
conta_destino.id_open_finance_account as conta_destino_id_open_finance_account,
coalesce(conta_destino.image_url, ofi_destino.image_url) as conta_destino_image_url,
coalesce(conta_destino.currency, pr_destino.currency, '') as currency_destino,

/**{columns}**/

ifnull(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem) as transf_id_conta_origem,
ifnull(transferencias_fixas_valor.id_conta_destino, transferencias.id_conta_destino) as transf_id_conta_destino,
ifnull(transferencias_fixas_valor.valor, transferencias.valor) as val,
ifnull(transferencias_fixas_valor.id_desp_encargos, transferencias.id_desp_encargos) as id_desp_encargos,
transferencias_fixas_valor.data as data_valor,

ifnull(COALESCE(transferencias_fixas.obs, transferencias_fixas_valor.obs_futura, transferencias.obs),'') as transf_obs,

(CASE WHEN (ifnull(transferencias.recorrencia,'N') = 'N' OR transferencias.recorrencia = 'P')
THEN transferencias.contabilizada
WHEN transferencias.recorrencia = 'M' AND transferencias_fixas.contabilizada IS NULL
THEN 'N'
ELSE transferencias_fixas.contabilizada END) as contada,
COALESCE(transferencias_fixas.data_efetivacao, transferencias.data_efetivacao, transferencias.data) as data_efetivacao,
COALESCE(transferencias.data_cadastro, transferencias.data) as dtcad,

(CASE transferencias.recorrencia WHEN 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d', date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2)
END))
ELSE transferencias.data  END) as data_venc,

{param_data_referencia} as dt

FROM transferencias
/**{INNER_JOIN}**/
LEFT JOIN transferencias_fixas on transferencias.id = transferencias_fixas.id_transferencia
and date(ifnull(transferencias_fixas.data, transferencias.data), 'start of month') = date(:datainicio, 'start of month')

LEFT JOIN transferencias_fixas as transferencias_fixas_valor on transferencias_fixas_valor.id_transferencia = transferencias.id
and date(transferencias_fixas_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month')
from transferencias_fixas where transferencias_fixas.id_transferencia = transferencias.id
and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

LEFT JOIN contas as conta_origem on conta_origem.id = ifnull(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem)
LEFT JOIN profiles as pr_origem on pr_origem.id = conta_origem.id_profile
LEFT JOIN open_finance_items as ofi_origem on ofi_origem.id = conta_origem.id_item

LEFT JOIN contas as conta_destino on conta_destino.id = ifnull(transferencias_fixas_valor.id_conta_destino, transferencias.id_conta_destino)
LEFT JOIN profiles as pr_destino on pr_destino.id = conta_destino.id_profile
LEFT JOIN open_finance_items as ofi_destino on ofi_destino.id = conta_destino.id_item
