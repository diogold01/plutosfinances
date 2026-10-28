SELECT tags.*, COUNT(tt.id_tag) AS n
FROM tags
LEFT JOIN tags_transacoes AS tt ON tt.id_tag = tags.id
GROUP BY tags.id
ORDER BY n DESC, tags.nome ASC