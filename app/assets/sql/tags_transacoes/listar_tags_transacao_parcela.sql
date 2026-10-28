-- Tags próprias
SELECT t.*
FROM tags t
JOIN tags_transacoes tt
  ON tt.id_tag = t.id
WHERE
  tt.id_transacao = :id_transacao
  AND tt.tipo_transacao = :tipo_transacao

UNION ALL

-- Tags herdadas do id_origem (se não houver tags próprias)
SELECT t.*
FROM tags t
JOIN tags_transacoes tt
  ON tt.id_tag = t.id
WHERE
  tt.id_transacao_origem = :id_transacao_origem
  AND tt.tipo_transacao = :tipo_transacao
  AND NOT EXISTS (
    SELECT 1
    FROM tags_transacoes tp
    WHERE tp.id_transacao = :id_transacao
      AND tp.tipo_transacao = :tipo_transacao
  )
