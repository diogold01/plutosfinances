SELECT count(1) as qt, id_conta_origem FROM transferencias
WHERE id_conta_destino = :id_destino
AND DATE(COALESCE(data_cadastro, data)) >= DATE('now', '-90 days')
GROUP BY id_conta_origem
ORDER BY qt desc
LIMIT 1
