-- Per-turn and per-search latency tracking.
-- Run once in the Supabase SQL editor to enable granular latency measurement.
--
-- Two tables, two vantage points on the same voice cycle:
--   turn_latency   — widget-side: time from user-stops-speaking to first AI
--                    audio / products-in-carousel. One row per conversational turn.
--   search_latency — search-service-side: embedding/RPC/rerank breakdown for
--                    every /search call, independent of whether the widget's
--                    POST ever arrives (server truth, not client-reported).
--
-- Both carry a `config_variant` tag (see LATENCY_CONFIG_VERSION env var) so
-- rows can be grouped by "which settings were live when this happened" —
-- that's what lets /latency-summary answer "did change X actually help?"

CREATE TABLE IF NOT EXISTS turn_latency (
    id                  UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    agent_id            TEXT        NOT NULL,
    conversation_id     TEXT,
    cycle               INTEGER,
    config_variant      TEXT,
    latency_first_ai_ms INTEGER,
    latency_products_ms INTEGER,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_turn_latency_agent_id    ON turn_latency(agent_id);
CREATE INDEX IF NOT EXISTS idx_turn_latency_conversation ON turn_latency(conversation_id);
CREATE INDEX IF NOT EXISTS idx_turn_latency_variant      ON turn_latency(config_variant);
CREATE INDEX IF NOT EXISTS idx_turn_latency_created_at   ON turn_latency(created_at DESC);

CREATE TABLE IF NOT EXISTS search_latency (
    id             UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    store_id       TEXT        NOT NULL,
    query          TEXT,
    result_count   INTEGER,
    total_ms       INTEGER,
    embedding_ms   INTEGER,
    rpc_ms         INTEGER,
    queue_wait_ms  INTEGER,
    cache_hit      BOOLEAN     DEFAULT false,
    config_variant TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_search_latency_store_id  ON search_latency(store_id);
CREATE INDEX IF NOT EXISTS idx_search_latency_variant   ON search_latency(config_variant);
CREATE INDEX IF NOT EXISTS idx_search_latency_created_at ON search_latency(created_at DESC);

-- Tag existing session_feedback rows going forward with the same variant,
-- so a session's overall rating can be cross-referenced against latency.
ALTER TABLE session_feedback ADD COLUMN IF NOT EXISTS config_variant TEXT;
CREATE INDEX IF NOT EXISTS idx_session_feedback_variant ON session_feedback(config_variant);
