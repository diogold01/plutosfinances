update notificacoes
set
texto = :texto,
horario = :horario,
package = :package,
tipo = :tipo,
valor = :valor,
local = :local,
id_profile = :id_profile,
ignorar_similares = :ignorar_similares,
ignorar_package = :ignorar_package
where id = :id
