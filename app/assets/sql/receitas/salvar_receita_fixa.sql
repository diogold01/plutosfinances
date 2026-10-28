insert into receitas_fixas (
id,
id_receita,
valor,
data,
excluido_mes,
obs,
obs_futura,
efetivado,
id_conta,
data_efetivacao,
dia_venc,
attach_path,
attach_size,
cotacao,
id_open_finance_transaction)
values (
((select coalesce(max(id),0) from receitas_fixas) + 1),
:id_receita,
:valor,
:data,
:excluido_mes,
:obs,
(SELECT obs_futura FROM receitas_fixas WHERE id_receita = :id_receita
 AND date(data, 'start of month') <= date(:data, 'start of month')
 ORDER BY data DESC LIMIT 1),
:efetivado,
:id_conta,
:data_efetivacao,
:dia_venc,
:attach_path,
:attach_size,
:cotacao,
:id_open_finance_transaction)
