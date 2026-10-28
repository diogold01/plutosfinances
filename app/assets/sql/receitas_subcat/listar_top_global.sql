select
receitas_subcat.id,
receitas_subcat.nome,
receitas_subcat.cor,
receitas_subcat.id_categoria,
receitas_subcat.id_profile,
receitas_subcat.icon_id,
receitas_subcat.data_exclusao as cat_data_exclusao,
(case when nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
ifnull(sum(receitas.efetivadas * receitas.cotacao), 0) as efet,
ifnull(sum(receitas.pendentes * receitas.cotacao), 0) as pend,
count(receitas.efetivadas) as registros
from receitas_subcat
left join (
  select
    receitas.id_profile,
    receitas.id_categoria,
    receitas.id_subcategoria,
    (case when (
      case when receitas.recorrencia = 'M' and receitas_fixas.efetivado is null
        then 'N'
      when receitas.recorrencia = 'M' and receitas_fixas.efetivado is not null
        then receitas_fixas.efetivado
      when receitas.recorrencia != 'M'
        then receitas.efetivado
      end
    ) = 'N'
      then 0
      else ifnull(receitas_fixas_valor.valor, receitas.valor) end) as efetivadas,
    (case when (
      case when receitas.recorrencia = 'M' and receitas_fixas.efetivado is null
        then 'N'
      when receitas.recorrencia = 'M' and receitas_fixas.efetivado is not null
        then receitas_fixas.efetivado
      when receitas.recorrencia != 'M'
        then receitas.efetivado
      end
    ) = 'S'
      then 0
      else ifnull(receitas_fixas_valor.valor, receitas.valor) end) as pendentes,
    coalesce(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
    {param_data_referencia} as dt
  from receitas
  left join receitas_fixas
    on receitas.id = receitas_fixas.id_receita
    and date(ifnull(receitas_fixas.data, receitas.data), 'start of month') =
        date(:datainicio, 'start of month')
  left join receitas_fixas as receitas_fixas_valor
    on receitas_fixas_valor.id_receita = receitas.id
    and date(receitas_fixas_valor.data, 'start of month') = (
      select date(max(receitas_fixas.data), 'start of month')
      from receitas_fixas
      where id_receita = receitas.id
        and date(receitas_fixas.data, 'start of month') <=
            date(:datainicio, 'start of month')
    )
  where ifnull(receitas_fixas.excluido_mes, 'N') = 'N'
    and (receitas.recorrencia != 'M' or
        date(receitas.data, 'start of month') <= date(dt, 'start of month'))
    and (:filtro_conta = 'N' or
        coalesce(receitas_fixas_valor.id_conta, receitas.id_conta) = :id_conta)
    and date(dt) between date(strftime('%Y-%m-01', :datainicio))
    and date(:datainicio, 'start of month', '+1 month', '-1 day')
    and (:graficos = 'N' or ifnull(receitas.considerar_estatistica, 'S') = 'S')
    and receitas.id_profile = :id_profile
    and (receitas.data_exclusao is null or
        date(strftime('%Y-%m-01', :datainicio)) <=
            date(strftime('%Y-%m-01', receitas.data_exclusao)))
) as receitas
  on receitas.id_categoria = receitas_subcat.id_categoria
  and receitas.id_subcategoria = receitas_subcat.id
where receitas_subcat.id_profile = :id_profile
/**{params}**/
group by receitas_subcat.id, receitas_subcat.id_categoria
having (:graficos = 'N' or (efet > 0 or pend > 0))
