select tags.*, count(tt.id_tag) utilizacoes from tags
left join tags_transacoes as tt on tags.id = tt.id_tag
WHERE id_profile = :id_profile
{params}
group by tags.id