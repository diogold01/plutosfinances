INSERT INTO cartoes_credito_mes
 (id_cartao,
 mes,
 ano,
 limite,
 dia_venc,
 dia_fecha,
 id_conta,
 conta_vinculada,
 fatura_paga,
 attach_path,
 attach_size
 )
  VALUES (
  :id_cartao,
  :mes,
  :ano,
  :limite,
  :dia_venc,
  :dia_fecha,
  :id_conta,
  :conta_vinculada,
  :fatura_paga,
  :attach_path,
  :attach_size
  )