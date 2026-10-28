SELECT
 cartoes_credito.id as card_id,
 nome,
 nome_carteira,
 cor,
 img_id,
 case when ofi.image_id is not null
 then ofi.image_id
 else ifnull(cartoes_credito.image_id, -1) end as image_id,

 -- OPEN FINANCE
 cartoes_credito.id_item,
 cartoes_credito.id_open_finance_account,
 cartoes_credito.holder_type,
 last_successful_sync_at,
 coalesce(ofi.name_connector, '') as nome_instituicao,
 -- A imagem local definida no item Open Finance deve substituir a URL remota
 -- da instituição também nos cartões vinculados.
 case when ofi.image_id is not null and ofi.image_id >= 0
 then null
 else coalesce(cartoes_credito.image_url, ofi.image_url) end as image_url,
 coalesce(ofi.status, '')         as status_conexao,
 coalesce(ofi.primary_color, '')  as primary_color,

 cartoes_credito.id_profile,
 cartao_mes.attach_path,
 coalesce(cartao_mes.attach_size,  0) as attach_size,
 cartao_mes.attach_id,
 coalesce(dias_fechamento, -1) as dias_fechamento,
 ifnull(cartoes_credito.tipo, 'NONE') as tipo,
 ifnull(cartoes_credito.text_alt, 'N') as text_alternativo,
 ifnull(cartoes_credito.fechamento_dias_uteis, 'N') as fechamento_dias_uteis,
 ifnull(cartoes_credito.sequence, 0) as sequence,
 ifnull(padrao, 'N') as padrao,
ifnull(cartao_mes.limite, cartoes_credito.limite) as limite,
ifnull(cartao_mes.conta_vinculada, cartoes_credito.conta_vinculada) as has_conta_vinculada,
img_id,
cartoes_credito.data_exclusao as data_ex,
ifnull(cartao_mes.fatura_paga, 'N') as fatura_paga,
ifnull(cartao_mes.dia_venc, cartoes_credito.dia_venc) as dia_venc,
ifnull(cartao_mes.dia_fecha, cartoes_credito.dia_fecha) as dia_fecha,
num_cartao,
ifnull(cartao_mes.id_conta, cartoes_credito.id_conta) as id_conta,
0 as fatura,
0 as ignorar_limite,
0 as faturas_abertas
FROM cartoes_credito
/**{INNER_JOIN}**/
left join cartoes_credito_mes as cartao_mes ON date(cartao_mes.ano || '-' || substr('0' || cartao_mes.mes, -2, 2) ||  '-01') =
(select  max(date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01'))
from cartoes_credito_mes
where date(ano || '-' || substr('0' || mes, -2, 2) ||  '-01') <= date(:datainicio, 'start of month')
and id_cartao = cartoes_credito.id)
and cartao_mes.id_cartao  = cartoes_credito.id

/* OPN FINANCE ITEMS */
left join open_finance_items as ofi on ofi.id = cartoes_credito.id_item

WHERE
((coalesce(:APENAS_ARQUIVADOS, 'N') = 'S' AND cartoes_credito.data_exclusao IS NOT NULL) OR
(coalesce(:APENAS_ARQUIVADOS, 'N') = 'N' AND (cartoes_credito.data_exclusao IS NULL OR
date(strftime('%Y-%m-01', :datainicio)) <=
date(strftime('%Y-%m-01', cartoes_credito.data_exclusao)))))
AND (coalesce(:NAO_LISTAR_ARQUIVADOS, 'N') = 'N' OR cartoes_credito.data_exclusao IS NULL)
      {params}
ORDER BY sequence, nome
