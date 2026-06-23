-- Session feedback table
-- Run once in Supabase SQL editor to enable feedback collection.
CREATE TABLE IF NOT EXISTS session_feedback (
    id                  UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    agent_id            TEXT        NOT NULL,
    duration_seconds    INTEGER,
    rating              TEXT        CHECK (rating IN ('positive', 'neutral', 'negative', 'none')),
    feedback_tag        TEXT,
    products_shown      INTEGER     DEFAULT 0,
    products_clicked    INTEGER     DEFAULT 0,
    shop_now_clicked    BOOLEAN     DEFAULT false,
    chat_messages       INTEGER     DEFAULT 0,
    end_reason          TEXT,
    conversation_id     TEXT,
    latency_first_ai_ms INTEGER,
    latency_products_ms INTEGER,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_session_feedback_agent_id      ON session_feedback(agent_id);
CREATE INDEX IF NOT EXISTS idx_session_feedback_created_at    ON session_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_session_feedback_conversation  ON session_feedback(conversation_id);

-- Migration: run this if the table already exists
ALTER TABLE session_feedback ADD COLUMN IF NOT EXISTS conversation_id     TEXT;
ALTER TABLE session_feedback ADD COLUMN IF NOT EXISTS latency_first_ai_ms INTEGER;
ALTER TABLE session_feedback ADD COLUMN IF NOT EXISTS latency_products_ms INTEGER;
