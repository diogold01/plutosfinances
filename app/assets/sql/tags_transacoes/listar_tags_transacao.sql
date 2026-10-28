SELECT t.*
FROM tags t
JOIN tags_transacoes tt
  ON tt.id_tag = t.id
WHERE
tt.id_transacao = :id_transacao
AND tt.tipo_transacao = :tipo_transacao
{params}
ORDER BY t.nome