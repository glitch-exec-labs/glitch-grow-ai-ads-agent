-- Week 1 memory substrate: session log table for the ads agent.
--
-- Logs every command turn so future recall + dreaming can reason over history.
-- Schema is prepared for Week 2 (active-memory recall via FTS + pgvector MMR)
-- and Week 3 (dreaming cron that promotes rows to per-store MEMORY.md).
--
-- Safe to run multiple times (all CREATE statements are idempotent).
--
-- Apply with:
--   sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_agent_memory.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS ads_agent AUTHORIZATION shopify_app;

-- Ensure shopify_app user can use the schema even if it already existed
GRANT ALL ON SCHEMA ads_agent TO shopify_app;

CREATE TABLE IF NOT EXISTS ads_agent.agent_memory (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_tg_id      BIGINT,
    store_slug      TEXT,                        -- e.g. 'urban', or NULL for non-store commands
    command         TEXT NOT NULL,               -- e.g. 'insights', 'roas', 'tracking_audit', 'ideas'
    args            JSONB NOT NULL DEFAULT '{}'::JSONB,
    reply_text      TEXT,
    key_metrics     JSONB,                       -- flattened summary numbers for fast SQL aggregations
    agent_reasoning TEXT,                        -- optional: LLM CoT or intermediate notes

    -- Week 2: vector recall. Nullable until embeddings populate.
    -- 768-dim = Gemini text-embedding-004. Can migrate to 1536 (OpenAI) later.
    embedding       vector(768),

    -- Lifecycle marker — v1 is always 'insight'; v2 adds 'action_proposed',
    -- 'action_executed', 'lesson_learned', 'alert_fired' etc.
    kind            TEXT NOT NULL DEFAULT 'insight',

    -- FTS for Week 2 hybrid search (FTS + vector)
    reply_tsv       tsvector GENERATED ALWAYS AS (to_tsvector('english', COALESCE(reply_text, ''))) STORED
);

-- Hot-path indexes
CREATE INDEX IF NOT EXISTS agent_memory_ts_idx              ON ads_agent.agent_memory (ts DESC);
CREATE INDEX IF NOT EXISTS agent_memory_store_ts_idx        ON ads_agent.agent_memory (store_slug, ts DESC);
CREATE INDEX IF NOT EXISTS agent_memory_command_ts_idx      ON ads_agent.agent_memory (command, ts DESC);
CREATE INDEX IF NOT EXISTS agent_memory_user_ts_idx         ON ads_agent.agent_memory (user_tg_id, ts DESC);
CREATE INDEX IF NOT EXISTS agent_memory_store_cmd_ts_idx    ON ads_agent.agent_memory (store_slug, command, ts DESC);

-- Week 2 search indexes
CREATE INDEX IF NOT EXISTS agent_memory_reply_tsv_idx       ON ads_agent.agent_memory USING GIN (reply_tsv);
CREATE INDEX IF NOT EXISTS agent_memory_embedding_hnsw_idx  ON ads_agent.agent_memory
    USING hnsw (embedding vector_cosine_ops);

-- Ensure app role can insert/select
GRANT SELECT, INSERT, UPDATE ON ads_agent.agent_memory        TO shopify_app;
GRANT USAGE, SELECT         ON SEQUENCE ads_agent.agent_memory_id_seq TO shopify_app;
