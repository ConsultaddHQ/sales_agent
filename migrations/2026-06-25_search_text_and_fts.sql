-- Migration: 2026-06-25 — enriched search_text column + FTS index + updated hybrid RPC
--
-- What this fixes:
--   • Color, product_type, tags, and variant options lived only in metadata JSONB —
--     invisible to embedding and keyword search. Products with color "White" only in
--     variant options could never be found by "white pants".
--   • plainto_tsquery AND-ed every token: one stray word → zero FTS hits → fell back
--     to fuzzy vector-only, losing color precision.
--   • The old hybrid_search_products in SHOPIFY_FLOW_COMPLETE.md was stale (pure vector).
--     This is the canonical, committed source of truth for the deployed function.
--
-- Run against Supabase SQL editor. Idempotent (IF NOT EXISTS / CREATE OR REPLACE).

-- 1. Add search_text column
alter table public.products add column if not exists search_text text;

-- 2. Backfill existing rows so they aren't dark until re-onboarded
update public.products
  set search_text = coalesce(name, '') || ' ' || coalesce(description, '')
  where search_text is null or search_text = '';

-- 3. FTS index over search_text (covers enriched attributes after re-onboarding)
drop index if exists products_name_gin;
create index if not exists products_search_text_fts
  on public.products
  using gin (to_tsvector('english', coalesce(search_text, name || ' ' || coalesce(description, ''))));

-- 4. Drop ALL existing overloads before recreating (CREATE OR REPLACE only works when
--    the parameter list matches exactly — different orders create extra overloads instead)
drop function if exists public.hybrid_search_products(uuid, text, extensions.vector, integer, double precision, numeric);
drop function if exists public.hybrid_search_products(uuid, text, extensions.vector, numeric, integer, double precision);
drop function if exists public.hybrid_search_products(uuid, text, vector, integer, double precision, numeric);
drop function if exists public.hybrid_search_products(uuid, text, vector, numeric, integer, double precision);

-- 5. Rewrite hybrid_search_products
--    Changes vs previous version:
--    • FTS CTE uses websearch_to_tsquery (OR-friendly, tolerates extra words) over search_text
--    • Vector CTE uses HNSW top-K pattern (ORDER BY <=> LIMIT candidates) — preserves HNSW use
--    • Combined via RRF (Reciprocal Rank Fusion, k=60) — no hard min_score filter in Stage 1,
--      favoring recall so the reranker in search-service can recover precision
--    • Returns metadata + local_image_path so the reranker can build richer doc text
--    • Signature backward-compatible: same required params, same return shape (+ new columns)
create or replace function hybrid_search_products(
  p_store_id        uuid,
  p_query           text,
  p_query_embedding vector(384),
  p_limit           int     default 10,
  p_min_score       float   default 0.15,   -- lowered; Stage-1 favors recall
  p_max_price       numeric default null
)
returns table (
  id               uuid,
  store_id         uuid,
  name             text,
  description      text,
  price            numeric,
  image_url        text,
  local_image_path text,
  product_url      text,
  metadata         jsonb,
  similarity       float
)
language plpgsql
as $$
begin
  return query
  with
  -- Vector candidates: use HNSW top-K pattern (ORDER BY + LIMIT, not WHERE filter)
  vector_matches as (
    select
      p.id,
      row_number() over (order by p.embedding <=> p_query_embedding) as rn,
      (1 - (p.embedding <=> p_query_embedding)) as vec_score
    from public.products p
    where p.store_id = p_store_id
      and p.embedding is not null
      and (p_max_price is null or p.price <= p_max_price)
    order by p.embedding <=> p_query_embedding
    limit 50
  ),

  -- Full-text candidates: websearch_to_tsquery tolerates OR / extra words
  fts_matches as (
    select
      p.id,
      row_number() over (
        order by ts_rank_cd(
          to_tsvector('english', coalesce(p.search_text, p.name || ' ' || coalesce(p.description, ''))),
          websearch_to_tsquery('english', p_query)
        ) desc
      ) as rn
    from public.products p
    where p.store_id = p_store_id
      and (p_max_price is null or p.price <= p_max_price)
      and to_tsvector('english', coalesce(p.search_text, p.name || ' ' || coalesce(p.description, '')))
          @@ websearch_to_tsquery('english', p_query)
  ),

  -- Reciprocal Rank Fusion (k=60)
  rrf as (
    select
      coalesce(v.id, f.id) as id,
      coalesce(1.0 / (60 + v.rn), 0) + coalesce(1.0 / (60 + f.rn), 0) as rrf_score,
      coalesce(v.vec_score, 0) as vec_score
    from vector_matches v
    full outer join fts_matches f on v.id = f.id
  )

  select
    p.id,
    p.store_id,
    p.name,
    p.description,
    p.price,
    p.image_url,
    p.local_image_path,
    p.product_url,
    p.metadata,
    r.rrf_score as similarity
  from rrf r
  join public.products p on p.id = r.id
  where r.vec_score >= p_min_score or r.vec_score = 0  -- keep FTS-only hits (vec_score=0 means no vector match but FTS hit)
  order by r.rrf_score desc
  limit p_limit;
end;
$$;
