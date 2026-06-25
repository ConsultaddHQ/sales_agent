-- Migration: 2026-06-26 — fuzzy (trigram) matching arm for hybrid_search_products
--
-- What this fixes:
--   • Voice transcription garbles product words (e.g. "trousers" → "flouser"/"flosser",
--     "trowser", "truser"). Neither the vector arm (semantically far) nor the FTS arm
--     (exact lexeme match) can bridge a misspelled/misheard word → 0 results → the agent
--     says the store doesn't carry it even though the product exists.
--   • This adds a THIRD retrieval arm using pg_trgm word_similarity (character-level fuzzy
--     match), fused into the existing RRF. Catches close transcription noise without an
--     LLM round-trip. (Harder mis-hearings like "fl"≠"tr" are also handled at the agent-
--     prompt layer, which re-interprets phonetically and retries before giving up.)
--
-- Supersedes the hybrid_search_products body from 2026-06-25_search_text_and_fts.sql.
-- Run AFTER that migration. Idempotent.

-- 1. Enable trigram extension
create extension if not exists pg_trgm;

-- 2. Drop ALL existing overloads before recreating (CREATE OR REPLACE only replaces an
--    exact param-list match — different orders create extra overloads → PGRST203)
drop function if exists public.hybrid_search_products(uuid, text, extensions.vector, integer, double precision, numeric);
drop function if exists public.hybrid_search_products(uuid, text, extensions.vector, numeric, integer, double precision);
drop function if exists public.hybrid_search_products(uuid, text, vector, integer, double precision, numeric);
drop function if exists public.hybrid_search_products(uuid, text, vector, numeric, integer, double precision);

-- 3. Recreate with a third (trigram) arm
create or replace function hybrid_search_products(
  p_store_id        uuid,
  p_query           text,
  p_query_embedding vector(384),
  p_limit           int     default 10,
  p_min_score       float   default 0.15,
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
  -- Vector candidates (HNSW top-K)
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

  -- Full-text candidates (websearch_to_tsquery, OR-friendly)
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

  -- Fuzzy candidates (pg_trgm word_similarity — catches typos / garbled transcription).
  -- word_similarity(query, text) = best trigram match of the query against any word-boundary
  -- substring of text. Threshold 0.25 catches close mis-hearings ("flouser"~"trousers")
  -- while excluding noise; tune up if false positives appear. This arm only ADDS candidates
  -- that the cross-encoder reranker then re-sorts, so leaning toward recall is low-cost.
  -- At ~250 products/store this seq-scans a tiny set — sub-millisecond.
  trgm_matches as (
    select
      p.id,
      row_number() over (
        order by word_similarity(
          p_query,
          coalesce(p.search_text, p.name || ' ' || coalesce(p.description, ''))
        ) desc
      ) as rn
    from public.products p
    where p.store_id = p_store_id
      and (p_max_price is null or p.price <= p_max_price)
      and word_similarity(
            p_query,
            coalesce(p.search_text, p.name || ' ' || coalesce(p.description, ''))
          ) > 0.25
  ),

  -- Reciprocal Rank Fusion (k=60) across all three arms
  rrf as (
    select
      coalesce(v.id, f.id, t.id) as id,
      (coalesce(1.0 / (60 + v.rn), 0)
        + coalesce(1.0 / (60 + f.rn), 0)
        + coalesce(1.0 / (60 + t.rn), 0))::float as rrf_score,
      coalesce(v.vec_score, 0)::float as vec_score,
      (f.id is not null) as is_fts_match,
      (t.id is not null) as is_trgm_match
    from vector_matches v
    full outer join fts_matches  f on v.id = f.id
    full outer join trgm_matches t on coalesce(v.id, f.id) = t.id
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
  -- Keep every keyword (FTS) and fuzzy (trgm) hit, plus vector hits above the recall
  -- threshold. Stage-1 favors recall; the cross-encoder reranker recovers precision.
  where r.is_fts_match or r.is_trgm_match or r.vec_score >= p_min_score
  order by r.rrf_score desc
  limit p_limit;
end;
$$;
