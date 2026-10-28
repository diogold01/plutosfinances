CREATE TABLE open_finance_items (
  id TEXT NOT NULL,
  id_perfil TEXT NOT NULL,
  status TEXT NOT NULL,
  owner TEXT NOT NULL,
  execution_status TEXT NOT NULL,
  initial_status_sync TEXT,
  status_detail TEXT,

  created_at DATETIME,
  vinculo_manual_at DATETIME,
  reconnect_transactions_from_at DATETIME,
  updated_at DATETIME,
  disconnected_at DATETIME,

  last_attempt_sync_at DATETIME,
  last_successful_sync_at DATETIME,
  last_successful_sync_action_id TEXT,
  last_successful_sync_source TEXT,
  last_error_message TEXT,
  last_error_at DATETIME,
  last_update_request_at DATETIME,
  update_count_date TEXT,
  update_count_today INTEGER,
  min_update_frequency_hours INTEGER,

  institution_url TEXT,
  image_url TEXT,
  image_id INTEGER,
  sandbox INTEGER,
  open_finance INTEGER,

  primary_color TEXT,
  country_connector TEXT,
  type_connector TEXT,
  status_connector TEXT,

  name_connector TEXT NOT NULL,
  id_connector INTEGER NOT NULL,

  CONSTRAINT unique_id UNIQUE (id)
);
