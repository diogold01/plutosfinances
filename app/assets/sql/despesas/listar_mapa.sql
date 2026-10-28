select despesas.id, descricao, despesas.valor, place_id, longitude, latitude, despesas.data, despesas.id_profile as id_profile, despesas_cat.nome, despesas_cat.cor
from despesas
inner join despesas_cat_valor as catmap on catmap.id_despesa = despesas.id
left join despesas_cat ON despesas_cat.id = catmap.id_categoria
 WHERE date(despesas.data) between date(:datainicio) AND date(:datafim)
 AND (latitude is not null and latitude != '' and longitude is not null and longitude != '')
AND recorrencia != 'F'
AND despesas.id_profile = :id_profile
GROUP BY catmap.id_despesa, descricao