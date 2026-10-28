-- Tabela de agrupamento de orçamentos
CREATE TABLE IF NOT EXISTS orcamentos_agrupamento (
  id_pai    TEXT NOT NULL,
  id_filho  TEXT NOT NULL,

  -- Cada orçamento pode ter no MÁXIMO um pai
  UNIQUE(id_filho),

  -- Evita auto-referência direta
  CHECK (id_pai <> id_filho),

  FOREIGN KEY (id_pai)   REFERENCES orcamentos(id) ON DELETE CASCADE,
  FOREIGN KEY (id_filho) REFERENCES orcamentos(id) ON DELETE CASCADE
);

-- Índices para melhorar buscas por pai/filho
CREATE INDEX IF NOT EXISTS idx_orc_agru_pai
  ON orcamentos_agrupamento(id_pai);

CREATE INDEX IF NOT EXISTS idx_orc_agru_filho
  ON orcamentos_agrupamento(id_filho);
