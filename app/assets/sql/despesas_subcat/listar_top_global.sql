select
despesas_subcat.id,
despesas_subcat.nome,
despesas_subcat.cor,
despesas_subcat.icon_id,
despesas_subcat.id_profile,
despesas_subcat.id_categoria,
despesas_subcat.data_exclusao as cat_data_exclusao,
(case when nome in ('Outros', 'Others', 'Otros') then 0 else 1 end) ord,
ifnull(sum(despesas.pago), 0) as efet,
ifnull(sum(despesas.pendente), 0) as pend,
count(despesas.pago) as registros
from despesas_subcat
left join (
  select
    id_profile,
    id_categoria,
    id_subcategoria,
    sum(pago * cotacao) as pago,
    sum(pendente * cotacao) as pendente
  from (
    select
      despesas.id_profile,
      catmap.id_categoria,
      catmap.id_subcategoria,
      (case when (
        case when recorrencia = 'F'
          then coalesce(despesas_fixas.status, 'pd')
          else despesas.status end
      ) = 'pd'
        then 0
        else (sum(catmap.valor) + coalesce(despesas_fixas.juros, despesas.juros, 0)) end) as pago,
      (case when (
        case when recorrencia = 'F'
          then coalesce(despesas_fixas.status, 'pd')
          else despesas.status end
      ) = 'pg'
        then 0
        else (sum(catmap.valor) + coalesce(despesas_fixas.juros, despesas.juros, 0)) end) as pendente,
      coalesce(despesas_fixas.cotacao, despesas.cotacao, 1) as cotacao,
      {param_data_referencia} as dt
    from despesas
    left join despesas_fixas
      on despesas.id = despesas_fixas.id_despesa
      and date(ifnull(despesas_fixas.data, despesas.data), 'start of month') =
          date(:datainicio, 'start of month')
    inner join despesas_cat_valor as catmap
      on catmap.id_despesa = despesas.id
      and (despesas.recorrencia != 'F' or
          (date(catmap.data) = date((
              select max(despesas_cat_valor.data)
              from despesas_cat_valor
              where id_despesa = catmap.id_despesa
                and id_categoria = catmap.id_categoria
                and id_subcategoria = catmap.id_subcategoria
                and lower(ifnull(obs, '')) = lower(ifnull(catmap.obs, ''))
                and date(despesas_cat_valor.data) <=
                    date(:datainicio, 'start of month')
            ))
            and catmap.excluido != 'S'))
    left join despesas_fixas as despesas_fixas_valor
      on despesas_fixas_valor.id_despesa = despesas.id
      and date(despesas_fixas_valor.data, 'start of month') = (
        select date(max(despesas_fixas.data), 'start of month')
        from despesas_fixas
        where id_despesa = despesas.id
          and date(despesas_fixas.data, 'start of month') <=
              date(:datainicio, 'start of month')
      )
    where (despesas.recorrencia != 'F' or
            date(despesas.data, 'start of month') <= date(dt, 'start of month'))
      and ifnull(despesas_fixas.excluido_mes, 'N') = 'N'
      and (:graficos = 'N' or ifnull(despesas.considerar_estatistica, 'S') = 'S')
      and (:filtro_cartao = 'N' or
          ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) =
              :id_cartao_credito)
      and (:filtro_conta = 'N' or
          ifnull(despesas_fixas_valor.id_conta, despesas.id_conta) = :id_conta)
      and (:apenas_cartao = 'N' or
          ifnull(ifnull(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito), '-1')
              not in ('', '-1'))
      and despesas.id_profile = :id_profile
      and (despesas.data_exclusao is null or
          date(strftime('%Y-%m-01', :datainicio)) <=
              date(strftime('%Y-%m-01', despesas.data_exclusao)))
      and date(dt) between date(strftime('%Y-%m-01', :datainicio))
      and date(:datainicio, 'start of month', '+1 month', '-1 day')
    group by despesas.id, catmap.id_categoria, catmap.id_subcategoria
  )
  group by id_profile, id_categoria, id_subcategoria
) as despesas
  on despesas.id_categoria = despesas_subcat.id_categoria
  and despesas.id_subcategoria = despesas_subcat.id
where despesas_subcat.id_profile = :id_profile
/**{params}**/
group by despesas_subcat.id, despesas_subcat.id_categoria
having (:graficos = 'N' or (efet > 0 or pend > 0))
