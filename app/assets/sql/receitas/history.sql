SELECT
 {param_data_referencia} as dt,
SUM(round(COALESCE(receitas_fixas_valor.valor, receitas.valor),2)) as val,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
COALESCE(receitas.somar_total,'S') as somar

FROM receitas
left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
                               and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
left join contas on contas.id = COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta)

WHERE
dt between :data and :data_end
AND COALESCE(receitas_fixas.excluido_mes,'N') = 'N'
AND (receitas.recorrencia != 'F' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
AND (receitas.data_exclusao IS NULL OR date(strftime('%Y-%m-01',:datainicio)) <=
date(strftime('%Y-%m-01', receitas.data_exclusao)))
{params}
GROUP BY date(dt) HAVING val > 0
ORDER BY dt