SELECT t.*
FROM tags t
JOIN orcamentos_tags tt
  ON tt.id_tag = t.id
WHERE
tt.id_orcamento = :id_orcamento
{params}
ORDER BY t.nome