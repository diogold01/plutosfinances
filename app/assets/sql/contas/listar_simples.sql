select
contas.id as conta_id,
contas.id_conta_pai as id_conta_pai,
ifnull(contas.conta_pai, 'N') as conta_pai,

-- OPEN FINANCE
id_item,
id_open_finance_account,
subtype,
number,
routing_number,
last_successful_sync_at,
coalesce(ofi.name_connector, '') as nome_instituicao,
-- A imagem local definida no item Open Finance deve substituir a URL remota
-- da instituição também nas contas vinculadas.
case when ofi.image_id is not null and ofi.image_id >= 0
then null
else coalesce(contas.image_url, ofi.image_url) end as image_url,
coalesce(ofi.status, '')        as status_conexao,
coalesce(ofi.primary_color, '') as primary_color,

coalesce(contas.currency, profiles.currency) as currency,
ifnull(contas.exibir_saldo, 'N') as exibir_saldo,
ifnull(contas.liquidacao, 'N') as liquidacao,
ifnull(contas.exibir_resumo, 'N') as exibir_resumo,
ifnull(contas.investimento, 'N') as investimento,
ifnull(contas.somar_todas_contas_agrupadas, 'N') as somar_todas_contas_agrupadas,
ifnull(contas.padrao_importacao, 'S') as padrao_importacao,
ifnull(contas.pendente_primeira_reconciliacao_saldo_tempo_real, 'N') as pendente_primeira_reconciliacao_saldo_tempo_real,
ifnull(contas.sequence, 0) as sequence,
contas.descricao as conta_desc,
contas.id_profile as id_profile,
contas.dados_adicionais as dados,
contas.fav as favorita_count,
contas.data_cadastro as conta_data_cad,
contas.somar_total as conta_somar,
contas.padrao as conta_padrao,
contas.id_categoria as conta_id_categoria,
contas.data_exclusao as conta_data_ex,
case when ofi.image_id is not null
then ofi.image_id
else ifnull(contas.image_id, 0) end as image_id,
contas_cat.descricao as categoria_desc,
contas_cat.padrao as categoria_padrao,
ifnull(contas_cat.cor, 0) as categoria_cor,
'N' as categoria_not_resume,
'N' as categoria_not_balance,
252 as categoria_icon_id

from contas
inner join profiles on contas.id_profile = profiles.id
left join contas_cat on contas_cat.id = contas.id_categoria

/* OPN FINANCE ITEMS */
left join open_finance_items as ofi on ofi.id = contas.id_item

/**{INNER_JOIN}**/
where
(:considerar_arquivadas = 'S' OR contas.data_exclusao IS NULL OR
                          date(strftime('%Y-%m-01',:datainicio)) <=
                          date(strftime('%Y-%m-01', contas.data_exclusao)))
