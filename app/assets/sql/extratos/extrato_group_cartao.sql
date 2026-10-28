select
op,
extrato.id,
id_origem,
extrato.id_profile,
recorrencia,
tipo,
val,
COALESCE(cotacao, 1) as cotacao,
num_cats,
dt_venc,
dt_lanc,
dt,
dt_efet,
descr,
efetivado,
(CASE
WHEN tipo = 't' THEN somar
WHEN COALESCE(contas.somar_total,'S') = 'N' THEN 'N'
ELSE somar
END) as somar_totais,
id_conta,
COALESCE(conta_desc, contas.descricao)  as conta_desc,
contas.currency as conta_currency,
card_img,
cat_cor,
cat_icon,
cat_id,
subcat_cor,
subcat_icon,
subcat_id,
cat_nome,
subcat_nome,
obs,
adiantamento_fatura,
card_dias_fechamento,
card_fechamento_dias_uteis,
card_dia_venc
from
(
--DESPESAS SEM CARTAO
SELECT
despesas.id,
despesas.id_origem,
despesas.id_profile,
despesas.recorrencia,
'deb' as op,
'g' as tipo,
-1    as card_img,
(round(SUM(catmap.valor),2) + COALESCE(despesas_fixas.juros, despesas.juros, 0)) as val,
COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1) as cotacao,
COUNT(catmap.valor) as num_cats,
(CASE despesas.recorrencia WHEN 'F' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
 END))
 ELSE despesas.data END) as dt_venc,
 COALESCE(despesas_fixas_valor.data_cadastro, despesas.data_cadastro) dt_lanc,

(CASE WHEN COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito, '-1') IN ('', '-1') AND
COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao, '') != '' THEN
 COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) ELSE
 (CASE despesas.recorrencia WHEN 'F' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
 END))
 ELSE despesas.data END) END) as dt,
COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) as dt_efet,
 (despesas.descricao || (CASE WHEN despesas.recorrencia = 'M' THEN ' ' || despesas.num_parcela || '/' || despesas.num_parcelas ELSE '' END)) as descr,
 (case when (case when despesas.recorrencia = 'F' and despesas_fixas.status is null
 		then 'pd'
       when  despesas.recorrencia = 'F' and despesas_fixas.status is not null
 		then despesas_fixas.status
 	  when despesas.recorrencia != 'F'
 		then despesas.status
 	   end ) = 'pd' then 'N' else 'S' end) as efetivado,

COALESCE(despesas.somar_total,'S') as somar,
COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta) as id_conta,
null as conta_desc,

despesas_cat.cor as cat_cor,
despesas_cat.nome as cat_nome,
despesas_cat.icon_id as cat_icon,
despesas_cat.id as cat_id,
despesas_subcat.nome as subcat_nome,
despesas_subcat.cor as subcat_cor,
despesas_subcat.icon_id as subcat_icon,
despesas_subcat.id as subcat_id,
COALESCE(despesas_fixas.obs, despesas_fixas_valor.obs_futura, despesas.obs) as obs,
coalesce(despesas.adiantamento_fatura, 'N') as adiantamento_fatura,
-1    as card_dias_fechamento,
'N'   as card_fechamento_dias_uteis,
-1    as card_dia_venc

FROM
despesas
inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
    AND (despesas.recorrencia != 'F' OR
           (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
            AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(COALESCE(obs, '')) = LOWER(COALESCE(catmap.obs,''))
            AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
            AND catmap.excluido != 'S'))
left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(COALESCE(despesas_fixas.data,despesas.data), 'start of month') = date(:datainicio, 'start of month')
left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
   and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
   and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
 left join despesas_cat on despesas_cat.id = catmap.id_categoria
 left join despesas_subcat on despesas_subcat.id = catmap.id_subcategoria
WHERE
despesas.id_profile = :id_profile
AND (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt, 'start of month'))
and COALESCE(despesas_fixas.excluido_mes,'N') = 'N'
AND (despesas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', despesas.data_exclusao)))
AND date(dt) BETWEEN date(:datainicio) and date(:datafim)
AND  (:id_conta = 'ALL' OR COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta) = :id_conta)
AND  COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito, '-1') IN ('', '-1')
GROUP BY catmap.id_despesa

UNION ALL

--DESPESAS COM CARTÃO
SELECT id,
'-1' as id_origem,
id_profile,
'N' as recorrencia,
'deb' as op,
'g' as tipo,
card_img,
round(SUM(val1), 2) as val,
1 as cotacao,
1 as num_cats,
dt_venc,
dt_venc as dt_lanc,
dt,
dt_efet,
descr,
efetivado,
somar,
id_conta,
conta_desc,
cat_cor,
'' as cat_nome,
278 as cat_icon,
'-1' as cat_id,
'' as subcat_nome,
subcat_cor,
278 as subcat_icon,
'-1' as subcat_id,
'' as obs,
'N' as adiantamento_fatura,
card_dias_fechamento,
card_fechamento_dias_uteis,
card_dia_venc

 FROM
(SELECT
COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito) as id,
cartoes_credito.img_id  as card_img,
coalesce(cartoes_credito.dias_fechamento, -1)  as card_dias_fechamento,
COALESCE(cartoes_credito.fechamento_dias_uteis, 'N') as card_fechamento_dias_uteis,
COALESCE(cartao_mes.dia_venc, cartoes_credito.dia_venc)        as card_dia_venc,
((round(SUM(catmap.valor),2) + COALESCE(despesas_fixas.juros, despesas.juros, 0))
* COALESCE(despesas_fixas_valor.cotacao, despesas.cotacao, 1)) as val1,
(CASE despesas.recorrencia WHEN 'F' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
 ELSE   substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
 END))
 ELSE despesas.data  END) as dt_venc,
 (CASE WHEN COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao, '') != '' THEN
  COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) ELSE
  (CASE despesas.recorrencia WHEN 'F' THEN
 datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
 (CASE WHEN  substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
  ELSE   substr('0'|| COALESCE(despesas_fixas_valor.dia_venc, strftime('%d', despesas.data)), -2, 2)
  END))
  ELSE despesas.data  END) END) as dt,
 COALESCE(despesas_fixas.data_efetivacao, despesas.data_efetivacao) as dt_efet,
 cartoes_credito.nome as descr,
 (case when (case when despesas.recorrencia = 'F' and despesas_fixas.status is null
 		then 'pd'
       when  despesas.recorrencia = 'F' and despesas_fixas.status is not null
 		then despesas_fixas.status
 	  when despesas.recorrencia != 'F'
 		then despesas.status
 	   end ) = 'pd' then 'N' else 'S' end) as efetivado,

(case when COALESCE(contas.somar_total,'S') = 'N'
THEN 'N'
ELSE 'S' END) as somar,
contas.id as id_conta,
contas.descricao as conta_desc,
cartoes_credito.cor as cat_cor,
cartoes_credito.cor as subcat_cor,
cartoes_credito.id_profile
FROM
despesas
inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
               AND (despesas.recorrencia != 'F' OR
                      (date(catmap.data)  = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
                       AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(COALESCE(obs, '')) = LOWER(COALESCE(catmap.obs,''))
                       AND date(despesas_cat_valor.data) <= DATE(:datainicio, 'start of month')))
                       AND catmap.excluido != 'S'))
left join despesas_fixas on despesas.id = despesas_fixas.id_despesa and date(COALESCE(despesas_fixas.data,despesas.data), 'start of month') = date(:datainicio, 'start of month')
left join despesas_fixas as despesas_fixas_valor on despesas_fixas_valor.id_despesa = despesas.id
   and date(despesas_fixas_valor.data, 'start of month')  = (select date(max(despesas_fixas.data),'start of month') from despesas_fixas where id_despesa = despesas.id
   and date(despesas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))

left join despesas_cat on CAST(despesas.id_categoria as integer) = despesas_cat.id
left join despesas_subcat on despesas.id_subcategoria = despesas_subcat.id
left join contas on contas.id = COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta)
left join cartoes_credito on cartoes_credito.id = COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito)
left join cartoes_credito_mes as cartao_mes ON date(cartao_mes.ano || '-' || substr('0' || cartao_mes.mes, -2, 2) ||  '-01') =
(select  max(date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01'))
from cartoes_credito_mes
where date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01') <= date(:datainicio, 'start of month')
and id_cartao = cartoes_credito.id)
and cartao_mes.id_cartao  = cartoes_credito.id
WHERE
despesas.id_profile = :id_profile
AND (despesas.recorrencia != 'F' OR date(despesas.data, 'start of month') <= date(dt_venc, 'start of month'))
and COALESCE(despesas_fixas.excluido_mes,'N') = 'N'
AND (despesas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', despesas.data_exclusao)))
AND date(dt_venc) BETWEEN date(:datainicio) and date(:datafim)
AND  (:id_conta = 'ALL' OR COALESCE(despesas_fixas_valor.id_conta, despesas.id_conta) = :id_conta
-- isso faria o valor da fatura ficar igual ao cartão de crédito, mas causa outras divergencias
-- deixar comentado por enquanto.
-- ocorre que pagamentos antecipados (estornos) feitos usando outras contas
-- nao sao considerados no extrato da conta do cartao mesmo
--OR catmap.valor < 0
)
group by catmap.id_despesa
having COALESCE(despesas_fixas_valor.id_cartao_credito, despesas.id_cartao_credito, '-1') NOT IN ('', '-1'))
GROUP BY id
HAVING val != 0

UNION ALL

--RECEITAS
select
receitas.id,
receitas.id_origem,
receitas.id_profile,
receitas.recorrencia,
  'cred' as op,
  'd' as tipo,
  -1    as card_img,
COALESCE(receitas_fixas_valor.valor, receitas.valor) as val,
COALESCE(receitas_fixas_valor.cotacao, receitas.cotacao, 1) as cotacao,
1 as num_cats,
(CASE receitas.recorrencia WHEN 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
END))
ELSE receitas.data  END)  as dt_venc,
receitas.data_cadastro as dt_lanc,
(CASE WHEN COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao, '') != '' THEN
COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao) ELSE
(CASE receitas.recorrencia WHEN 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(receitas_fixas_valor.dia_venc, strftime('%d', receitas.data)), -2, 2)
END))
ELSE receitas.data  END) END) as dt,
COALESCE(receitas_fixas.data_efetivacao, receitas.data_efetivacao) as dt_efet,
(CASE WHEN receitas.recorrencia = 'P' THEN
   receitas.descricao || ' ' || receitas.num_parcela || '/' || receitas.num_parcelas
  ELSE
  receitas.descricao
  END) as descr,
COALESCE(receitas_fixas.efetivado, receitas.efetivado,'N') as efetivado,

COALESCE(receitas.somar_total,'S') as somar,
COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta) as id_conta,
null as conta_desc,

receitas_cat.cor as cat_cor,
receitas_cat.descricao as cat_nome,
receitas_cat.icon_id as cat_icon,
receitas_cat.id as cat_id,
receitas_subcat.nome as subcat_nome,
receitas_subcat.cor as subcat_cor,
receitas_subcat.icon_id as subcat_icon,
receitas_subcat.id as subcat_id,
COALESCE(receitas_fixas.obs, receitas_fixas_valor.obs_futura, receitas.obs,'') as obs,
'N' as adiantamento_fatura,
-1  as card_dias_fechamento,
'N' as card_fechamento_dias_uteis,
-1  as card_dia_venc

from receitas left join receitas_fixas on receitas.id = receitas_fixas.id_receita
and date(COALESCE(receitas_fixas.data, receitas.data), 'start of month') = date(:datainicio, 'start of month')
 left join receitas_fixas as receitas_fixas_valor on receitas_fixas_valor.id_receita = receitas.id
 and date(receitas_fixas_valor.data, 'start of month') = (select date(max(receitas_fixas.data),'start of month') from receitas_fixas where id_receita = receitas.id
 and date(receitas_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
 left join receitas_cat on receitas_cat.id = receitas.id_categoria
 left join receitas_subcat on receitas.id_subcategoria = receitas_subcat.id
where
receitas.id_profile = :id_profile
AND (receitas.recorrencia != 'M' OR date(receitas.data, 'start of month') <= date(dt, 'start of month'))
and COALESCE(receitas_fixas.excluido_mes,'N') = 'N'
AND (receitas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', receitas.data_exclusao)))
AND date(dt) BETWEEN date(:datainicio) and date(:datafim)
and (:id_conta = 'ALL' OR COALESCE(receitas_fixas_valor.id_conta, receitas.id_conta) = :id_conta)

UNION ALL

--TRANSFERENCIAS
SELECT
transferencias.id,
transferencias.id_origem,
transferencias.id_profile,
transferencias.recorrencia,
(CASE WHEN :id_conta = 'ALL' THEN
(CASE WHEN (conta_origem.id_profile = :id_profile AND conta_destino.id_profile != :id_profile)
OR conta_destino.somar_total = 'N'
THEN 'deb' ELSE 'cred' END)
ELSE
 (case when COALESCE(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem) = :id_conta
 THEN  'deb' ELSE 'cred'  END) END) as op,
't' as tipo,
-1    as card_img,

 round(CASE WHEN transferencias.id_profile = :id_profile
 THEN ifnull(transferencias_fixas_valor.valor, transferencias.valor)
 ELSE ifnull(transferencias_fixas_valor.valor, transferencias.valor) * COALESCE(transferencias_fixas_valor.cotacao, transferencias.cotacao, 1)
 END, 2) as val,
1 as cotacao,
0 as num_cats,
(CASE COALESCE(transferencias.recorrencia, 'N') WHEN 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2)
END))
ELSE transferencias.data  END)  as dt_venc,
transferencias.data_cadastro as dt_lanc,
(CASE WHEN COALESCE(transferencias_fixas.data_efetivacao, transferencias.data_efetivacao,  '') != '' THEN
COALESCE(transferencias_fixas.data_efetivacao, transferencias.data_efetivacao) ELSE
(CASE WHEN COALESCE(transferencias.recorrencia, 'N') = 'M' THEN
datetime(strftime('%Y-%m', :datainicio) ||  '-' ||
(CASE WHEN  substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2) > strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
THEN   strftime('%d',date(:datainicio,'start of month','+1 month','-1 day'))
ELSE   substr('0'|| COALESCE(transferencias_fixas_valor.dia_venc, strftime('%d', transferencias.data)), -2, 2)
END))
ELSE transferencias.data  END) END) as dt,
COALESCE(transferencias_fixas.data_efetivacao, transferencias.data_efetivacao) as dt_efet,
( COALESCE(transferencias.descricao, 'Transf') ||
 (CASE WHEN transferencias.recorrencia = 'P' THEN
   ' ' || transferencias.num_parcela || '/' || transferencias.num_parcelas
  ELSE
  ''
  END)) as descr,
COALESCE(transferencias_fixas.contabilizada, transferencias.contabilizada) as efetivado,

(CASE WHEN :id_conta = 'ALL' AND
       ((conta_origem.id_profile = :id_profile AND conta_origem.somar_total = 'N'
       AND conta_origem.id_profile != conta_destino.id_profile)
       OR (conta_destino.id_profile = :id_profile AND conta_destino.somar_total = 'N'
       AND conta_origem.id_profile != conta_destino.id_profile)
       OR (conta_destino.somar_total = 'S' AND conta_origem.somar_total = 'S'
       AND conta_origem.id_profile = conta_destino.id_profile) OR
       (conta_destino.somar_total = 'N' AND conta_origem.somar_total = 'N'))
  then 'N'
  else 'S'end) as somar,
null  as id_conta,
(CASE WHEN :id_conta = 'ALL' THEN
(conta_origem.descricao || ' ➞ ' || conta_destino.descricao)
ELSE
(case when COALESCE(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem) = :id_conta
THEN conta_destino.descricao ELSE conta_origem.descricao END)
END) as conta_desc,
-740352 as cat_cor,
'' as cat_nome,
869 as cat_icon,
'-1' as cat_id,
'' as subcat_nome,
-740352 as subcat_cor,
869 as subcat_icon,
'-1' as subcat_id,
COALESCE(transferencias_fixas.obs, transferencias_fixas_valor.obs_futura, transferencias.obs, '') as obs,
'N' as adiantamento_fatura,
-1  as card_dias_fechamento,
'N' as card_fechamento_dias_uteis,
-1  as card_dia_venc

FROM transferencias

LEFT JOIN transferencias_fixas on transferencias.id = transferencias_fixas.id_transferencia
and date(COALESCE(transferencias_fixas.data, transferencias.data), 'start of month') = date(:datainicio, 'start of month')

LEFT JOIN transferencias_fixas as transferencias_fixas_valor on transferencias_fixas_valor.id_transferencia = transferencias.id
and date(transferencias_fixas_valor.data, 'start of month') = (select date(max(transferencias_fixas.data),'start of month')
from transferencias_fixas where transferencias_fixas.id_transferencia = transferencias.id
and date(transferencias_fixas.data, 'start of month') <= date(:datainicio, 'start of month'))
LEFT JOIN contas as conta_origem on conta_origem.id = COALESCE(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem)
LEFT JOIN contas as conta_destino on conta_destino.id = COALESCE(transferencias_fixas_valor.id_conta_destino, transferencias.id_conta_destino)
WHERE
COALESCE(transferencias_fixas.excluido_mes,'N') = 'N'
AND (transferencias.recorrencia != 'M' OR date(transferencias.data, 'start of month') <= date(dt, 'start of month'))
AND date(dt) between date(strftime('%Y-%m-01', :datainicio))
AND date(:datainicio,'start of month','+1 month','-1 day')
AND (transferencias.data_exclusao IS NULL OR
date(strftime('%Y-%m-01', :datainicio)) <=
date(strftime('%Y-%m-01', transferencias.data_exclusao)))
AND (transferencias.id_profile = :id_profile OR conta_destino.id_profile =:id_profile OR conta_origem.id_profile = :id_profile)
AND (:id_conta = 'ALL' OR
    COALESCE(transferencias_fixas_valor.id_conta_origem, transferencias.id_conta_origem) = :id_conta OR
    COALESCE(transferencias_fixas_valor.id_conta_destino, transferencias.id_conta_destino) = :id_conta)
 ) as extrato
LEFT JOIN contas on contas.id = id_conta

where 0=0
