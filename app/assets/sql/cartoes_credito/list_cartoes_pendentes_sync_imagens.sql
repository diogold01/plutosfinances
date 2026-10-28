select
id_cartao,
mes,
ano,
attach_path,
attach_size
from cartoes_credito_mes
WHERE COALESCE(attach_path, '') != ''
AND COALESCE(attach_id, '') = ''