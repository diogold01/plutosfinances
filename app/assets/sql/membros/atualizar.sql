update membros SET
nome = :nome,
data_nascimento = :data_nascimento,
parentesco = :parentesco,
url_foto = :url_foto,
foto_doc_id = :foto_doc_id,
id_perfil = :id_perfil,
id_dispositivo = :id_dispositivo,
arquivado = :arquivado
WHERE
id = :id
