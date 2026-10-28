select
 objetivos.id,
 descricao,
 meta,
 id_profile,
 id_conta,
 coalesce(SUM(valor), 0.0) as alcancado,
 expec,
 data_cadastro,
 data_realizado,
 saldo_inicial,
 ifnull(icon_id, -1) as icon_id,
 ifnull(objetivos.color, -1) as color,
 motivacao,
 realizado
 from objetivos
 left join objetivos_dep on objetivos.id = objetivos_dep.id_objetivo
where
0=0
{params}
 group by objetivos.id
 order by realizado, data_realizado desc, expec, data_cadastro desc, descricao