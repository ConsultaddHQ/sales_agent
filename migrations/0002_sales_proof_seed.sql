-- ===========================================================================
-- 0002_sales_proof_seed.sql  —  curated proof drafts for the Pop Sales Agent
-- Apply in Supabase SQL editor AFTER 0001. Idempotent (insert-if-absent).
--
-- ⚠️ ILLUSTRATIVE DRAFTS — plausible but NOT verified customer data. They use
-- generic descriptors (no fabricated named customers) so the agent never
-- attributes false claims. Replace with real, signed-off proof via the admin
-- Proof Library before any live prospect traffic. See DESIGN.md §8 Q5.
-- ===========================================================================

insert into public.sales_proof (site, type, title, body, metric, tags, active)
select v.site, v.type, v.title, v.body, v.metric, v.tags, true
from (values
  -- ── Case studies ──
  (
    'teampop', 'case_study',
    'Shopify apparel brand — voice agent on every product page',
    'A ~40-SKU Shopify apparel brand added the Pop voice agent to their storefront. Shoppers asked for styles by occasion ("something for a beach wedding") instead of clicking filters. The agent surfaced matching products and answered sizing questions in the moment.',
    'Add-to-cart rate on agent-assisted sessions ~1.9x site average; setup in under 2 weeks.',
    array['ecommerce','shopify','apparel','conversion','add to cart']
  ),
  (
    'teampop', 'case_study',
    'Enterprise GPU catalog — guided technical discovery',
    'A hardware catalog with hundreds of SKUs used the agent to walk buyers from a workload description ("training a 70B model") to the right configuration, replacing a slow spec-sheet hunt and a delayed sales callback.',
    'Qualified-demo requests up materially; time-to-first-relevant-result cut from minutes to seconds.',
    array['enterprise','hardware','gpu','technical','discovery','b2b']
  ),
  -- ── ROI ──
  (
    'teampop', 'roi',
    'ROI vs. hiring an SDR / live-chat team',
    'One Pop agent runs 24/7, never misses a visitor, and handles unlimited concurrent conversations. Compared with a single SDR (~$5,000+/mo loaded) covering business hours only, the agent covers nights/weekends — when a large share of consumer browsing happens — at a fraction of the cost.',
    'Typically pays for itself if it books even 1–2 incremental meetings per month.',
    array['roi','pricing','cost','sdr','vs hiring','budget','expensive']
  ),
  -- ── Testimonials (generic attribution) ──
  (
    'teampop', 'testimonial',
    'Founder, DTC accessories brand',
    '"It feels like having a great salesperson on every page. Visitors who talk to it convert noticeably better than the ones who just browse."',
    null,
    array['testimonial','ecommerce','conversion','social proof']
  ),
  (
    'teampop', 'testimonial',
    'Head of Growth, marketplace',
    '"Setup was genuinely fast — we were live the same week. The voice experience is far ahead of the chatbots we tried before."',
    null,
    array['testimonial','onboarding','fast','speed','vs chatbot']
  ),
  (
    'teampop', 'testimonial',
    'Ecommerce Manager, home goods',
    '"Our team stopped answering the same product questions over and over. The agent handles it and routes the serious buyers to us."',
    null,
    array['testimonial','support','deflection','time saved']
  ),
  -- ── Objection rebuttals ──
  (
    'teampop', 'objection_rebuttal',
    'Rebuttal — "AI feels risky / not ready for it"',
    'Most teams start with one narrow use case (e.g. product discovery on the top category) and expand once they see the numbers. It is additive to the current site, not a rebuild, and you stay in control of what it can say.',
    null,
    array['objection','not ready','risk','ai fear','land and expand']
  ),
  (
    'teampop', 'objection_rebuttal',
    'Rebuttal — "too expensive"',
    'Anchor to the cost of the problem: missed nights/weekends traffic and repetitive questions your team answers manually. The agent is a fraction of one hire and works every hour. Start small and scale only if the results justify it.',
    null,
    array['objection','expensive','price','budget','cost of inaction']
  ),
  (
    'teampop', 'objection_rebuttal',
    'Rebuttal — "we''ll build it ourselves"',
    'A capable team can, but voice + retrieval + conversation tuning is 6–12 months and ongoing maintenance. Pop is live in weeks and improves continuously. Many teams pilot Pop now and revisit build-vs-buy once they have the data.',
    null,
    array['objection','build it ourselves','in-house','timeline','engineering']
  )
) as v(site, type, title, body, metric, tags)
where not exists (
  select 1 from public.sales_proof p
  where p.site = v.site and p.title = v.title
);
