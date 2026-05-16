# Migrations

Supabase has no programmatic DDL path from this codebase (the service-role
client cannot run arbitrary `CREATE TABLE`). These `.sql` files are applied
**by a human in the Supabase SQL editor**, same as the original `products` /
`agent_requests` tables (see `SHOPIFY_FLOW_COMPLETE.md` and the roadmap's
"Manual Steps" table).

Files are numbered and **idempotent** (`if not exists` / `add column if not
exists`) so re-running is safe.

| File | Purpose | Applied |
|------|---------|---------|
| `0001_sales_agent.sql` | `sales_sessions`, `sales_proof`, `agent_requests` sales columns (Pop Sales Agent) | ⬜ pending — apply in Supabase SQL editor |

After applying, tick the box above and note it in `docs/agents/roadmap.md`.
