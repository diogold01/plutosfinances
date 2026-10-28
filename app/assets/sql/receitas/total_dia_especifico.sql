SELECT COALESCE(SUM(val * cotacao),0) total FROM (
select
round(COALESCE(receitas_fixas_valor.valor, receitas.valor),2) as val,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
COALESCE(COALESCE(receitas_fixas.efetivado, receitas.efetivado),'N') as efetivado,
COALESCE(receitas_fixas.excluido_mes,'N') as excluido,
{param_data_referencia} as dt

from receitas
left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                                 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
where
(receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
AND (receitas.data_exclusao IS NULL OR
date(strftime('%Y-%m-01', :datainicio)) <=
date(strftime('%Y-%m-01', receitas.data_exclusao)))
AND receitas.id_profile = :id_profile
AND date(dt) between date(:datainicio) and date(:datatermino)
/**{params}**/)