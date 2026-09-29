-- Observability / RCA tables (2026-09-29). Run once in the Supabase SQL editor,
-- AFTER create_latency_tracking_table.sql. Safe to re-run (IF NOT EXISTS everywhere).
--
-- Correlation key everywhere: conversation_id (ElevenLabs' ID for one call).
--   conversations       one row per call   — from the post-call webhook
--   conversation_turns  one row per turn   — LLM TTFB, tool latency, tool errors
--   search_latency      one row per search — now carries conversation_id
--   turn_latency        widget-side timing — now also connect / image timings
-- v_conversation_timeline merges all of them: filter by conversation_id to see
-- one call end to end (this is the "paste an ID, get the story" RCA view).

-- ── search_latency: join columns ──────────────────────────────────────────
ALTER TABLE search_latency ADD COLUMN IF NOT EXISTS conversation_id TEXT;
ALTER TABLE search_latency ADD COLUMN IF NOT EXISTS request_id      TEXT;
ALTER TABLE search_latency ADD COLUMN IF NOT EXISTS rerank_ms       INTEGER;
ALTER TABLE search_latency ADD COLUMN IF NOT EXISTS endpoint        TEXT DEFAULT 'search';
CREATE INDEX IF NOT EXISTS idx_search_latency_conversation ON search_latency(conversation_id);

-- ── turn_latency: widget-side extras ──────────────────────────────────────
-- cycle = 0 rows are session start: connect_ms = click → connected,
-- latency_first_ai_ms = click → greeting audio starts.
ALTER TABLE turn_latency ADD COLUMN IF NOT EXISTS connect_ms     INTEGER;
ALTER TABLE turn_latency ADD COLUMN IF NOT EXISTS image_ms       INTEGER; -- products shown → main image painted
ALTER TABLE turn_latency ADD COLUMN IF NOT EXISTS network_rtt_ms INTEGER; -- ElevenLabs ping RTT (onPing, SDK ≥1.10)
ALTER TABLE turn_latency ADD COLUMN IF NOT EXISTS context_tokens INTEGER; -- LLM prompt size of the turn (onContextUsage) — watch for growth

-- ── conversations ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id     TEXT PRIMARY KEY,
    agent_id            TEXT,
    branch_id           TEXT,
    version_id          TEXT,
    status              TEXT,
    started_at          TIMESTAMPTZ,
    duration_secs       INTEGER,
    termination_reason  TEXT,
    main_language       TEXT,
    cost                NUMERIC,
    call_successful     TEXT,
    transcript_summary  TEXT,
    evaluation_results  JSONB,
    data_collection     JSONB,   -- business signals (unmet need, budget, category…) — Phase 3
    turn_count          INTEGER,
    user_turns          INTEGER,
    interruptions       INTEGER,
    tool_error_count    INTEGER,
    llm_ttfb_p50_ms     INTEGER,
    llm_ttfb_p95_ms     INTEGER,
    tool_latency_p95_ms INTEGER,
    tool_latency_max_ms INTEGER,
    error               JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversations_agent_started ON conversations(agent_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_branch        ON conversations(branch_id);

-- ── conversation_turns ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_turns (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id     TEXT NOT NULL,
    turn_index          INTEGER NOT NULL,
    role                TEXT,
    message             TEXT,
    time_in_call_secs   NUMERIC,
    interrupted         BOOLEAN DEFAULT false,
    llm_ttfb_ms         INTEGER,
    llm_ttf_sentence_ms INTEGER,
    tool_calls          JSONB,
    tool_results        JSONB,
    max_tool_latency_ms INTEGER,
    has_tool_error      BOOLEAN DEFAULT false,
    turn_metrics        JSONB,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (conversation_id, turn_index)
);
CREATE INDEX IF NOT EXISTS idx_conversation_turns_conv ON conversation_turns(conversation_id);

-- Backend-only tables: RLS on with no policies = anon key gets nothing,
-- service-role (our services) bypasses RLS. Transcripts must never be public.
ALTER TABLE conversations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_turns ENABLE ROW LEVEL SECURITY;

-- ── RCA timeline: one call, every vantage point, in time order ────────────
CREATE OR REPLACE VIEW v_conversation_timeline AS
SELECT c.conversation_id,
       c.started_at + make_interval(secs => t.time_in_call_secs) AS at,
       'turn'::text                                              AS source,
       t.role                                                    AS kind,
       t.message                                                 AS detail,
       t.llm_ttfb_ms                                             AS llm_ttfb_ms,
       t.max_tool_latency_ms                                     AS duration_ms,
       t.has_tool_error                                          AS is_error,
       t.tool_results                                            AS extra
FROM conversation_turns t
JOIN conversations c USING (conversation_id)
UNION ALL
SELECT s.conversation_id, s.created_at, 'search', s.endpoint,
       s.query || ' → ' || s.result_count || ' results' || CASE WHEN s.cache_hit THEN ' (cache)' ELSE '' END,
       NULL, s.total_ms, false,
       jsonb_build_object('embedding_ms', s.embedding_ms, 'rpc_ms', s.rpc_ms,
                          'rerank_ms', s.rerank_ms, 'queue_wait_ms', s.queue_wait_ms,
                          'request_id', s.request_id)
FROM search_latency s
WHERE s.conversation_id IS NOT NULL
UNION ALL
SELECT w.conversation_id, w.created_at, 'widget', 'cycle ' || w.cycle,
       'first_ai=' || coalesce(w.latency_first_ai_ms::text, '?') || 'ms products=' ||
       coalesce(w.latency_products_ms::text, '?') || 'ms',
       NULL, w.latency_products_ms, false,
       jsonb_build_object('connect_ms', w.connect_ms, 'image_ms', w.image_ms,
                          'network_rtt_ms', w.network_rtt_ms, 'context_tokens', w.context_tokens,
                          'config_variant', w.config_variant)
FROM turn_latency w
WHERE w.conversation_id IS NOT NULL;

-- ── 30-day retention (agreed 2026-09-29) ──────────────────────────────────
CREATE OR REPLACE FUNCTION purge_observability_older_than_30d() RETURNS void
LANGUAGE sql AS $$
    DELETE FROM conversation_turns WHERE created_at < now() - interval '30 days';
    DELETE FROM conversations      WHERE created_at < now() - interval '30 days';
    DELETE FROM search_latency     WHERE created_at < now() - interval '30 days';
    DELETE FROM turn_latency       WHERE created_at < now() - interval '30 days';
$$;

-- Schedule daily at 03:00 UTC. Needs the pg_cron extension (Supabase:
-- Database → Extensions → pg_cron). If it isn't enabled, this block is skipped;
-- enable it and re-run this file.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.unschedule(jobid) FROM cron.job WHERE jobname = 'purge-observability-30d';
        PERFORM cron.schedule('purge-observability-30d', '0 3 * * *',
                              'SELECT purge_observability_older_than_30d()');
    ELSE
        RAISE NOTICE 'pg_cron not enabled — retention job NOT scheduled';
    END IF;
END $$;
