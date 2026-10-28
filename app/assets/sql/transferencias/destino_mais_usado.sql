SELECT count(1) as qt, id_conta_destino FROM transferencias
WHERE id_conta_origem = :id_origem
AND id_profile = :id_profile
AND DATE(COALESCE(data_cadastro, data)) >= DATE('now', '-90 days')
GROUP BY id_conta_destino
ORDER BY qt desc
LIMIT 1