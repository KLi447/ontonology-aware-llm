CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.chat_events (
  event_id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.entities (
  entity_id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  source TEXT NOT NULL,
  external_ref JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.memories (
  memory_id BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  embedding vector(1536),
  importance REAL NOT NULL DEFAULT 0.5,
  ttl_days INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.memory_summaries (
  summary_id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  session_window INT NOT NULL,
  summary TEXT NOT NULL,
  embedding vector(1536),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_embedding
  ON app.memories
  USING ivfflat (embedding vector_cosine);

CREATE INDEX IF NOT EXISTS idx_memory_summaries_embedding
  ON app.memory_summaries
  USING ivfflat (embedding vector_cosine);
