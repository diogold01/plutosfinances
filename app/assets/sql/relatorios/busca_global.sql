SELECT
dados.id,
dados.id_origem,
dados.descricao,
dados.valor,
dados.vencimento,
dados.lancamento,
dados.efetivacao,
dados.data_exclusao,
dados.tipo,
dados.recorrencia,
dados.local,
dados.obs,
dados.id_profile,
dados.nome_profile,
dados.img_id,
dados.cor,
dados.tipo_filtro
FROM
(

--- DESPESAS
select
despesas_busca.id,
despesas_busca.id_origem,
despesas_busca.descricao,
sum(despesas_busca.valor) as valor,
despesas_busca.vencimento,
despesas_busca.lancamento,
despesas_busca.efetivacao,
despesas_busca.data_exclusao,
'D' as tipo,
despesas_busca.recorrencia,
despesas_busca.local,
despesas_busca.obs,
despesas_busca.id_profile,
'' as nome_profile,
-1 as img_id,
-1 as cor,
-1 as tipo_filtro,
max(despesas_busca.match_obs_cat) as match_obs_cat
from (
select
despesas.id,
despesas.id_origem,
despesas.descricao,
round(COALESCE(SUM(catmap.valor), despesas.valor), 2) + COALESCE(despesas.juros, 0) as valor,
despesas.data as vencimento,
despesas.data_cadastro as lancamento,
despesas.data_efetivacao as efetivacao,
despesas.data_exclusao,
despesas.recorrencia,
despesas.local,
despesas.obs,
despesas.id_profile,
MAX(CASE WHEN lower(COALESCE(catmap.obs, '')) GLOB {pesquisa} THEN 1 ELSE 0 END) as match_obs_cat
from despesas
left join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
   AND (despesas.recorrencia != 'F' OR
       (date(catmap.data) = date((SELECT MAX(despesas_cat_valor.data) FROM despesas_cat_valor WHERE id_despesa = catmap.id_despesa
        AND id_categoria = catmap.id_categoria AND id_subcategoria = catmap.id_subcategoria AND LOWER(COALESCE(obs, '')) = LOWER(COALESCE(catmap.obs,''))))
        AND catmap.excluido != 'S'))
WHERE coalesce(:busca_despesas, 'S') = 'S'
{params_despesas_cat_obs}
group by despesas.id
) as despesas_busca
group by id_origem

UNION

--- RECEITAS
select
receitas.id,
receitas.id_origem,
descricao,
sum(valor) as valor,
data as vencimento,
data_cadastro as lancamento,
data_efetivacao as efetivacao,
data_exclusao,
'R' as tipo,
recorrencia,
local,
obs,
id_profile,
'' as nome_profile,
-1 as img_id,
-1 as cor,
-1 as tipo_filtro,
0 as match_obs_cat
from receitas
WHERE coalesce(:busca_receitas, 'S') = 'S'
group by id_origem

UNION

--- TRANSFERENCIAS
select
transferencias.id,
transferencias.id_origem,
descricao,
valor,
data as vencimento,
data as lancamento,
data as efetivacao,
data_exclusao,
'T' as tipo,
recorrencia,
'' as local,
obs,
id_profile,
'' as nome_profile,
-1 as img_id,
-1 as cor,
-1 as tipo_filtro,
0 as match_obs_cat
from transferencias
WHERE coalesce(:busca_transferencias, 'S') = 'S'
group by id_origem

UNION

--- CONTAS
select
contas.id,
contas.id as id_origem,
descricao,
0 as valor,
null as vencimento,
null as lancamento,
null as efetivacao,
data_exclusao,
'C' as tipo,
'N'  as recorrencia,
''as local,
'' AS obs,
id_profile,
profiles.name as nome_profile,
-1 as img_id,
-1 as cor,
-1 as tipo_filtro,
0 as match_obs_cat
from contas
inner join profiles on profiles.id = id_profile
WHERE coalesce(data_exclusao, '') = ''
AND coalesce(:busca_contas, 'S') = 'S'

UNION

--- CARTOES
select
cartoes_credito.id,
cartoes_credito.id as id_origem,
nome as descricao,
0 as valor,
null as vencimento,
null as lancamento,
null as efetivacao,
data_exclusao,
'CD' as tipo,
'N'  as recorrencia,
''as local,
'' AS obs,
id_profile,
profiles.name as nome_profile,
img_id,
cor,
-1 as tipo_filtro,
0 as match_obs_cat
from cartoes_credito
inner join profiles on profiles.id = id_profile
WHERE coalesce(data_exclusao, '') = ''
AND coalesce(:busca_cartoes, 'S') = 'S'

UNION

-- OBJETIVOS
select
objetivos.id,
objetivos.id as id_origem,
descricao,
0 as valor,
null as vencimento,
null as lancamento,
null as efetivacao,
null as data_exclusao,
'O' as tipo,
'N'  as recorrencia,
''as local,
'' AS obs,
id_profile,
profiles.name as nome_profile,
-1 as img_id,
objetivos.color as cor,
-1 as tipo_filtro,
0 as match_obs_cat
from objetivos
inner join profiles on profiles.id = id_profile
WHERE coalesce(:busca_objetivos, 'S') = 'S'

UNION

--- FILTROS
select
filtros.id,
filtros.id as id_origem,
descricao,
0 as valor,
null as vencimento,
null as lancamento,
null as efetivacao,
null as data_exclusao,
'F' as tipo,
'N'  as recorrencia,
''as local,
'' AS obs,
id_profile,
profiles.name as nome_profile,
-1 as img_id,
-1 as cor,
tipo as tipo_filtro,
0 as match_obs_cat
from filtros
inner join profiles on profiles.id = id_profile
WHERE coalesce(:busca_filtros, 'S') = 'S'
) as dados
INNER JOIN profiles on profiles.id = id_profile
WHERE
(coalesce(profiles.pin, '') = '' OR id_profile = :id_profile)
{params}
LIMIT 500
