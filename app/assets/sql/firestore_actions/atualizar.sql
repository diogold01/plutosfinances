UPDATE actions
SET
    retry_count = :retry_count,
    next_retry_time = :next_retry_time,
    status = :status,
    error_message = :error_message
WHERE
    action_id = :action_id;