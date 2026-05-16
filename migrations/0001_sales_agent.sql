-- ===========================================================================
-- 0001_sales_agent.sql  —  Pop Sales Agent (AI Account Executive)
-- Apply in Supabase SQL editor. Idempotent — safe to re-run.
-- ===========================================================================

-- 1. Per-conversation sales state (the stateful "sales brain" memory).
--    Keyed by the ElevenLabs conversation id so every webhook turn can
--    resume the same session.
create table if not exists public.sales_sessions (
  id              uuid primary key default uuid_generate_v4(),
  conversation_id text not null,
  site            text not null default 'teampop',
  stage           text not null default 'rapport',
  -- Problem Identification Chart: [{technical_problem, business_impact, root_cause}]
  pic             jsonb not null default '[]'::jsonb,
  -- Discovery fields captured for the assisted close (name/email/company/use_case…)
  captured        jsonb not null default '{}'::jsonb,
  objections      jsonb not null default '[]'::jsonb,
  proof_shown     jsonb not null default '[]'::jsonb,
  -- Full running transcript: [{role, text, ts}]
  transcript      jsonb not null default '[]'::jsonb,
  next_move       text,
  booked          boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create unique index if not exists sales_sessions_conversation_idx
  on public.sales_sessions (conversation_id);
create index if not exists sales_sessions_site_idx
  on public.sales_sessions (site);

-- 2. Trust / proof content the agent can surface (admin-editable).
create table if not exists public.sales_proof (
  id          uuid primary key default uuid_generate_v4(),
  site        text not null default 'teampop',
  -- case_study | roi | testimonial | objection_rebuttal
  type        text not null,
  title       text not null,
  body        text not null,
  metric      text,
  tags        text[] not null default '{}',
  active      boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists sales_proof_site_active_idx
  on public.sales_proof (site, active);
create index if not exists sales_proof_type_idx
  on public.sales_proof (type);

-- 3. Lead + transcript capture on the assisted close.
--    Reuses the existing agent_requests table / submit_request flow.
alter table public.agent_requests
  add column if not exists source     text default 'website';
alter table public.agent_requests
  add column if not exists transcript jsonb;
alter table public.agent_requests
  add column if not exists discovery  jsonb;
alter table public.agent_requests
  add column if not exists pic        jsonb;
