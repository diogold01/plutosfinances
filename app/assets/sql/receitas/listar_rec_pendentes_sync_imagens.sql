SELECT
attach_id,
attach_path,
coalesce(attach_size , 0) as attach_size,
id as id_receita,
id_origem,
'N' as fixo,
null as data
FROM receitas
WHERE COALESCE(attach_path, '') != ''
AND COALESCE(attach_id, '') = ''
UNION
SELECT
attach_id,
attach_path,
coalesce(attach_size , 0) as attach_size,
id_receita,
id_receita as id_origem,
'S' as fixo,
data
FROM receitas_fixas
WHERE COALESCE(attach_path, '') != ''
AND COALESCE(attach_id, '') = ''