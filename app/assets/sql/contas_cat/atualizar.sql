UPDATE contas_cat
SET
    descricao = :descricao,
    padrao = :padrao,
    cor = :cor,
    icon_id = :icon_id,
    not_dash = :not_dash,
    not_resume = :not_resume,
    not_balance = :not_balance
WHERE id = :id