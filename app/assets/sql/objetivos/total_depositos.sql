select ifnull(SUM(valor),0) total
from
objetivos_dep
where id_objetivo = :id_objetivo
{params}
group by id_objetivo