insert into transferencias_fixas
(
id,
id_transferencia,
valor,
data,
data_efetivacao,
excluido_mes,
obs,
obs_futura,
contabilizada,
id_conta_origem,
id_conta_destino,
id_desp_encargos,
dia_venc,
attach_path,
attach_size,
cotacao)
values
(
:id,
:id_transferencia,
:valor,
:data,
:data_efetivacao,
:excluido_mes,
:obs,
(SELECT obs_futura FROM transferencias_fixas WHERE id_transferencia = :id_transferencia
 AND date(data, 'start of month') <= date(:data, 'start of month')
 ORDER BY data DESC LIMIT 1),
:contabilizada,
:id_conta_origem,
:id_conta_destino,
:id_desp_encargos,
:dia_venc,
:attach_path,
:attach_size,
:cotacao)