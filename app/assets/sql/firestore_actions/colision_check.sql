SELECT *
FROM
  actions
WHERE
  status = 'PE'
  AND coalesce(origin, 'local') = 'local'
  AND date < :date
  {params}