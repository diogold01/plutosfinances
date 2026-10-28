SELECT
attach_id,
attach_path,
coalesce(attach_size, 0) as attach_size,
id as id_despesa,
id_origem,
'N' as fixo,
null as data
FROM despesas
WHERE COALESCE(attach_path, '') != ''
AND COALESCE(attach_id, '') = ''
UNION
SELECT
attach_id,
attach_path,
coalesce(attach_size, 0) as attach_size,
id_despesa,
id_despesa as id_origem,
'S' as fixo,
data
FROM despesas_fixas
WHERE COALESCE(attach_path, '') != ''
AND COALESCE(attach_id, '') = ''