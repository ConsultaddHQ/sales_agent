-- Phase 3 — Business Intelligence. Idempotent: safe to re-run. Postgres 15.
-- Run in the Supabase SQL editor (after create_observability_tables.sql).
--
-- Sources:
--   conversations.data_collection  (ElevenLabs data-collection results, see docs/observability-runbook.md)
--   conversation_turns.tool_calls   (what the shopper looked at / added)
--   search_latency                  (zero-result searches, raw query text)
--   assisted_orders                 (Shopify orders/create webhook, tagged with the TeamPop conversation)
-- Row-level "event" views keep a time column so Grafana can apply $__timeFilter;
-- the aggregate v_bi_* views are all-time convenience rollups.

-- ── Orders attributed to a TeamPop conversation ────────────────────────────
CREATE TABLE IF NOT EXISTS assisted_orders (
    order_id        text PRIMARY KEY,
    shop_domain     text,
    conversation_id text,
    total_price     numeric,
    currency        text,
    line_items      jsonb,
    created_at      timestamptz,
    received_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assisted_orders_conversation_idx ON assisted_orders (conversation_id);
CREATE INDEX IF NOT EXISTS assisted_orders_created_idx ON assisted_orders (created_at DESC);
ALTER TABLE assisted_orders ENABLE ROW LEVEL SECURITY;  -- no policies: service role only
DROP POLICY IF EXISTS grafana_read ON assisted_orders;
CREATE POLICY grafana_read ON assisted_orders FOR SELECT TO grafana_ro USING (true);

-- ── Helpers ────────────────────────────────────────────────────────────────
-- tool_calls[].params is a JSON *string*; never let one malformed row break a view.
CREATE OR REPLACE FUNCTION bi_try_jsonb(p text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN p::jsonb;
EXCEPTION WHEN others THEN
    RETURN NULL;
END $$;

-- ── One row per conversation, data-collection values typed ─────────────────
CREATE OR REPLACE VIEW v_conversation_signals AS
WITH turn_flags AS (
    SELECT
        t.conversation_id,
        bool_or(
            EXISTS (SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.tool_calls) = 'array' THEN t.tool_calls ELSE '[]'::jsonb END) c
                    WHERE c->>'tool_name' = 'add_to_cart')
            AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.tool_results) = 'array' THEN t.tool_results ELSE '[]'::jsonb END) r
                            WHERE r->>'tool_name' = 'add_to_cart' AND coalesce((r->>'is_error')::boolean, false))
        ) AS cart_added,
        bool_or(
            EXISTS (SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.tool_calls) = 'array' THEN t.tool_calls ELSE '[]'::jsonb END) c
                    WHERE c->>'tool_name' = 'go_to_cart')
        ) AS checkout,
        sum((SELECT count(*) FROM jsonb_array_elements(CASE WHEN jsonb_typeof(t.tool_calls) = 'array' THEN t.tool_calls ELSE '[]'::jsonb END) c
             WHERE c->>'tool_name' = 'get_product_details')) AS products_detailed
    FROM conversation_turns t
    GROUP BY t.conversation_id
)
SELECT
    c.conversation_id,
    c.started_at,
    c.agent_id,
    c.branch_id,
    nullif(trim(c.data_collection #>> '{shopper_need,value}'), '')                   AS shopper_need,
    nullif(lower(trim(c.data_collection #>> '{product_category,value}')), '')        AS product_category,
    CASE WHEN jsonb_typeof(c.data_collection #> '{need_met,value}') = 'boolean'
         THEN (c.data_collection #>> '{need_met,value}')::boolean END                AS need_met,
    nullif(trim(c.data_collection #>> '{unmet_need,value}'), '')                     AS unmet_need,
    nullif(trim(c.data_collection #>> '{shopper_terms,value}'), '')                  AS shopper_terms,
    CASE WHEN jsonb_typeof(c.data_collection #> '{budget_mentioned,value}') = 'boolean'
         THEN (c.data_collection #>> '{budget_mentioned,value}')::boolean END        AS budget_mentioned,
    CASE WHEN jsonb_typeof(c.data_collection #> '{budget_amount_inr,value}') = 'number'
         THEN (c.data_collection #>> '{budget_amount_inr,value}')::numeric END       AS budget_amount_inr,
    CASE WHEN jsonb_typeof(c.data_collection #> '{price_objection,value}') = 'boolean'
         THEN (c.data_collection #>> '{price_objection,value}')::boolean END         AS price_objection,
    nullif(lower(trim(c.data_collection #>> '{drop_off_reason,value}')), '')         AS drop_off_reason,
    coalesce(f.cart_added, false)                                                    AS cart_added,
    coalesce(f.checkout, false)                                                      AS checkout,
    coalesce(f.products_detailed, 0)::int                                            AS products_detailed,
    coalesce(c.user_turns, 0)                                                        AS user_turns
FROM conversations c
LEFT JOIN turn_flags f USING (conversation_id);

-- ── 1. Unmet needs ─────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_bi_unmet_events AS
SELECT started_at AS occurred_at,
       lower(trim(regexp_replace(unmet_need, '\s+', ' ', 'g'))) AS need,
       'agent_reported'::text AS source,
       conversation_id
FROM v_conversation_signals
WHERE unmet_need IS NOT NULL
UNION ALL
SELECT created_at,
       lower(trim(regexp_replace(query, '\s+', ' ', 'g'))),
       'zero_result_search',
       conversation_id
FROM search_latency
WHERE endpoint = 'search' AND result_count = 0 AND nullif(trim(query), '') IS NOT NULL;

CREATE OR REPLACE VIEW v_bi_top_unmet_needs AS
SELECT need,
       count(*)                                  AS mentions,
       count(DISTINCT conversation_id)           AS conversations,
       count(*) FILTER (WHERE source = 'agent_reported')      AS agent_reported,
       count(*) FILTER (WHERE source = 'zero_result_search')  AS zero_result_searches,
       max(occurred_at)                          AS last_seen
FROM v_bi_unmet_events
GROUP BY need
ORDER BY mentions DESC, last_seen DESC;

-- ── 2. Requested categories / products ─────────────────────────────────────
CREATE OR REPLACE VIEW v_bi_requested_categories AS
SELECT product_category,
       count(*) AS conversations,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS share_pct
FROM v_conversation_signals
WHERE product_category IS NOT NULL
GROUP BY product_category
ORDER BY conversations DESC;

CREATE OR REPLACE VIEW v_bi_product_events AS
SELECT t.created_at AS occurred_at,
       t.conversation_id,
       c->>'tool_name' AS action,
       p.id AS product_id,
       p.name AS product_name
FROM conversation_turns t
CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(t.tool_calls) = 'array' THEN t.tool_calls ELSE '[]'::jsonb END) c
JOIN products p
  ON p.id::text = bi_try_jsonb(c->>'params')->>'product_id'
WHERE c->>'tool_name' IN ('get_product_details', 'add_to_cart');

CREATE OR REPLACE VIEW v_bi_requested_products AS
SELECT product_id,
       product_name,
       count(*) FILTER (WHERE action = 'get_product_details') AS detail_views,
       count(*) FILTER (WHERE action = 'add_to_cart')         AS cart_adds,
       count(DISTINCT conversation_id)                        AS conversations,
       max(occurred_at)                                       AS last_seen
FROM v_bi_product_events
GROUP BY product_id, product_name
ORDER BY 3 + 4 DESC;

-- ── 3. Vocabulary gap: words shoppers use that the catalog never says ──────
-- Tokens come from the agent's shopper_terms and from raw search queries.
-- A token is a "gap" when it (or its singular) is absent from every product
-- name/description. Catalog is treated as one corpus (conversations carry no store_id).
CREATE OR REPLACE VIEW v_bi_vocab_events AS
WITH catalog AS (
    SELECT lower(coalesce(string_agg(coalesce(name, '') || ' ' || coalesce(description, ''), ' '), '')) AS txt
    FROM products
),
raw_terms AS (
    SELECT started_at AS occurred_at, shopper_terms AS txt, 'shopper_terms'::text AS source, conversation_id
    FROM v_conversation_signals WHERE shopper_terms IS NOT NULL
    UNION ALL
    SELECT created_at, query, 'search_query', conversation_id
    FROM search_latency WHERE endpoint = 'search' AND nullif(trim(query), '') IS NOT NULL
),
tokens AS (
    SELECT r.occurred_at, r.source, r.conversation_id, tok AS term
    FROM raw_terms r
    CROSS JOIN LATERAL regexp_split_to_table(lower(r.txt), '[^a-z0-9]+') AS tok
    WHERE length(tok) >= 3
      AND tok NOT IN ('the','and','for','with','you','your','that','this','have','are','not','can','any','please',
                      'looking','want','need','show','something','some','one','get','good','best','like','what',
                      'which','about','from','all','too','also','should','would','could','how')
)
SELECT t.occurred_at, t.source, t.conversation_id, t.term
FROM tokens t CROSS JOIN catalog c
WHERE position(t.term IN c.txt) = 0
  AND position(regexp_replace(t.term, 's$', '') IN c.txt) = 0;

CREATE OR REPLACE VIEW v_bi_vocabulary_gap AS
SELECT term,
       count(*)                                           AS mentions,
       count(DISTINCT conversation_id)                    AS conversations,
       count(*) FILTER (WHERE source = 'shopper_terms')   AS as_shopper_term,
       count(*) FILTER (WHERE source = 'search_query')    AS as_search_query,
       max(occurred_at)                                   AS last_seen
FROM v_bi_vocab_events
GROUP BY term
ORDER BY mentions DESC;

-- ── 4. Conversion by category ──────────────────────────────────────────────
CREATE OR REPLACE VIEW v_bi_conversion_by_category AS
SELECT coalesce(product_category, 'unknown') AS product_category,
       count(*)                                                   AS conversations,
       count(*) FILTER (WHERE cart_added)                         AS cart_added,
       count(*) FILTER (WHERE checkout)                           AS checkout,
       round(100.0 * count(*) FILTER (WHERE cart_added) / count(*), 1) AS cart_rate_pct,
       round(100.0 * count(*) FILTER (WHERE checkout) / count(*), 1)   AS checkout_rate_pct
FROM v_conversation_signals
GROUP BY 1
ORDER BY conversations DESC;

-- ── 5. Drop-off ────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_bi_dropoff_turn AS
SELECT user_turns,
       count(*) AS dropped_conversations,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS share_pct
FROM v_conversation_signals
WHERE NOT cart_added
GROUP BY user_turns
ORDER BY user_turns;

CREATE OR REPLACE VIEW v_bi_dropoff_reason AS
SELECT coalesce(drop_off_reason, 'unknown') AS drop_off_reason,
       count(*) AS conversations,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS share_pct
FROM v_conversation_signals
WHERE NOT cart_added
GROUP BY 1
ORDER BY conversations DESC;

-- ── 6. Price sensitivity (long format: kind / label / n / pct) ─────────────
CREATE OR REPLACE VIEW v_bi_price_sensitivity AS
WITH s AS (SELECT * FROM v_conversation_signals),
bucketed AS (
    SELECT CASE WHEN budget_amount_inr < 300  THEN '1. under 300'
                WHEN budget_amount_inr < 600  THEN '2. 300-599'
                WHEN budget_amount_inr < 1000 THEN '3. 600-999'
                WHEN budget_amount_inr < 2000 THEN '4. 1000-1999'
                ELSE '5. 2000+' END AS label
    FROM s WHERE budget_amount_inr IS NOT NULL
)
SELECT 'rate'::text AS kind, 'budget_mentioned'::text AS label,
       count(*) FILTER (WHERE budget_mentioned) AS n,
       round(100.0 * count(*) FILTER (WHERE budget_mentioned) / nullif(count(*) FILTER (WHERE budget_mentioned IS NOT NULL), 0), 1) AS pct
FROM s
UNION ALL
SELECT 'rate', 'price_objection',
       count(*) FILTER (WHERE price_objection),
       round(100.0 * count(*) FILTER (WHERE price_objection) / nullif(count(*) FILTER (WHERE price_objection IS NOT NULL), 0), 1)
FROM s
UNION ALL
SELECT 'budget_bucket', label, count(*),
       round(100.0 * count(*) / sum(count(*)) OVER (), 1)
FROM bucketed GROUP BY label;

-- ── 7. Catalog coverage per ISO week ───────────────────────────────────────
CREATE OR REPLACE VIEW v_bi_catalog_coverage_weekly AS
SELECT date_trunc('week', started_at) AS week_start,
       to_char(started_at, 'IYYY-"W"IW') AS iso_week,
       count(*)                                    AS product_seeking_conversations,
       count(*) FILTER (WHERE need_met)            AS need_met,
       round(100.0 * count(*) FILTER (WHERE need_met) / nullif(count(*) FILTER (WHERE need_met IS NOT NULL), 0), 1) AS coverage_score_pct
FROM v_conversation_signals
WHERE shopper_need IS NOT NULL OR product_category IS NOT NULL
GROUP BY 1, 2
ORDER BY 1;

-- ── 8. Purchase lag (conversation -> Shopify order) ────────────────────────
CREATE OR REPLACE VIEW v_bi_assisted_orders AS
SELECT o.order_id,
       o.conversation_id,
       o.created_at,
       o.total_price,
       o.currency,
       c.started_at,
       round((extract(epoch FROM (o.created_at - c.started_at)) / 3600.0)::numeric, 2) AS lag_hours,
       CASE WHEN c.started_at IS NULL THEN 'unattributed'
            WHEN o.created_at - c.started_at < interval '1 hour'  THEN '<1h'
            WHEN o.created_at - c.started_at < interval '1 day'   THEN '1-24h'
            WHEN o.created_at - c.started_at < interval '7 days'  THEN '1-7d'
            ELSE '>7d' END AS lag_bucket
FROM assisted_orders o
LEFT JOIN conversations c ON c.conversation_id = o.conversation_id;

CREATE OR REPLACE VIEW v_bi_purchase_lag AS
SELECT lag_bucket,
       count(*)                       AS orders,
       coalesce(sum(total_price), 0)  AS revenue,
       max(currency)                  AS currency
FROM v_bi_assisted_orders
GROUP BY lag_bucket
ORDER BY CASE lag_bucket WHEN '<1h' THEN 1 WHEN '1-24h' THEN 2 WHEN '1-7d' THEN 3 WHEN '>7d' THEN 4 ELSE 5 END;

-- ── Grafana read-only role ─────────────────────────────────────────────────
GRANT SELECT ON
    assisted_orders, v_conversation_signals,
    v_bi_unmet_events, v_bi_top_unmet_needs,
    v_bi_requested_categories, v_bi_product_events, v_bi_requested_products,
    v_bi_vocab_events, v_bi_vocabulary_gap,
    v_bi_conversion_by_category, v_bi_dropoff_turn, v_bi_dropoff_reason,
    v_bi_price_sensitivity, v_bi_catalog_coverage_weekly,
    v_bi_assisted_orders, v_bi_purchase_lag
TO grafana_ro;
