UPDATE open_finance_items
SET
last_attempt_sync_at = :last_attempt_sync_at,
last_successful_sync_at = :last_successful_sync_at,
last_successful_sync_action_id = :last_successful_sync_action_id,
last_successful_sync_source = :last_successful_sync_source,
last_error_message = :last_error_message,
last_error_at = :last_error_at
WHERE
  id = :id;
