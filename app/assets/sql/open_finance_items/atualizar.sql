UPDATE open_finance_items
SET
  status = :status,
  execution_status = :execution_status,
  status_detail = :status_detail,
  created_at = :created_at,
  vinculo_manual_at = :vinculo_manual_at,
  reconnect_transactions_from_at = :reconnect_transactions_from_at,
  updated_at = :updated_at,
  disconnected_at = :disconnected_at,
  institution_url = :institution_url,
  image_url = :image_url,
  image_id = :image_id,
  sandbox = :sandbox,
  open_finance = :open_finance,
  primary_color = :primary_color,
  country_connector = :country_connector,
  type_connector = :type_connector,
  name_connector = :name_connector,
  id_connector = :id_connector,
  initial_status_sync = :initial_status_sync,
  status_connector = :status_connector
WHERE
  id = :id;
