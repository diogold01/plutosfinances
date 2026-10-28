select
objetivos_dep.id,
objetivos_dep.id_objetivo,
objetivos_dep.valor,
objetivos_dep.data,
objetivos_dep.mensal,
objetivos_dep.obs
from
objetivos_dep
{join}
where 0=0
{params}
order by data desc