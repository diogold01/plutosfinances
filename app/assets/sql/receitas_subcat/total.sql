SELECT SUM(COALESCE(total, 0) * cotacao)
FROM (SELECT
COALESCE(receitas_fixas_valor.valor, receitas.valor) as total,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
receitas.id_profile,
{param_data_referencia} as dt
from receitas left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(ifnull(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
where
ifnull(receitas.id_categoria, '-1') = :id_categoria
and (:obedecer_estatistcas = 'N' OR ifnull(receitas.considerar_estatistica, 'S') = 'S')
and ifnull(receitas.id_subcategoria, '-1') = :id_subcategoria
and ifnull(receitas_fixas.excluido_mes,'N') = 'N'
AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
AND date(dt) between date(:datainicio) and date(:datafim)
AND (receitas.data_exclusao IS NULL OR
                    date(strftime('%Y-%m-01',:datainicio)) <=
                    date(strftime('%Y-%m-01', receitas.data_exclusao)))
AND receitas.id_profile = :id_profile
)
