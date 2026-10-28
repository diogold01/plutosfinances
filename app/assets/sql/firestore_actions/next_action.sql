select *
FROM
  actions
WHERE
  status = 'PE'
  AND coalesce(origin, 'local') = 'local'
  AND (next_retry_time IS NULL OR next_retry_time < :next_retry_time)
  AND context = :context
ORDER BY date asc
LIMIT 1