SELECT
attach_id,
attach_path,
coalesce(attach_size, 0)  as attach_size,
id as id_transferencia,
id_origem,
'N' as fixo,
null as data
FROM transferencias
WHERE COALESCE(attach_path, '') != ''
AND COALESCE(attach_id, '') = ''
UNION
SELECT
attach_id,
attach_path,
coalesce(attach_size, 0)  as attach_size,
id_transferencia,
id_transferencia as id_origem,
'S' as fixo,
data
FROM transferencias_fixas
WHERE COALESCE(attach_path, '') != ''
AND COALESCE(attach_id, '') = ''