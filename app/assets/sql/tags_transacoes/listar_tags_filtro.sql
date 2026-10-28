SELECT t.*
FROM tags t
INNER JOIN filtros_tags filtro ON filtro.id_tag = t.id
WHERE filtro.id_filtro = :id_filtro
AND t.id_profile = :id_profile
{params}