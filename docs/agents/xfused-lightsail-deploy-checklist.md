# Xfused Lightsail Deploy Checklist — 2026-07-14 session

Deploys the cart/checkout/prompt/voice/session-persistence fixes (this session's
commits on `release/xfused-pilot`) plus the reverted `.env` (xfused Supabase
project `jchigqerypjwmszslzke`, prod URLs, Muskaan voice) to the AWS Lightsail
Mumbai box. Run these as the `ubuntu` user on the box via SSH.

## 0. Before you start
- Confirm `SUPABASE_KEY` has been filled into both `.env` files (they currently
  have `REPLACE_ME_SUPABASE_SERVICE_ROLE_KEY` placeholders locally — must be
  the real key before this deploy, or both services will fail to boot).
- Confirm you're testing against a **duplicate/unpublished xfused theme**, not
  the live storefront, since this pushes straight to the production Lightsail
  box (there's no separate staging box per `docs/agents/memory.md`).

## 1. Pull the code
```bash
ssh ubuntu@<lightsail-ip>
cd /home/ubuntu/sales_agent
git fetch origin
git checkout release/xfused-pilot
git pull origin release/xfused-pilot
```

## 2. Sync .env files
The `.env` files are gitignored — they don't come through `git pull`. Copy the
updated local files to the box (from your laptop, not the box):
```bash
scp onboarding-service/.env ubuntu@<lightsail-ip>:/home/ubuntu/sales_agent/onboarding-service/.env
scp search-service/.env ubuntu@<lightsail-ip>:/home/ubuntu/sales_agent/search-service/.env
```
Or edit directly on the box with `nano`/`vim` if scp isn't convenient — just
make sure both end up with:
- `SUPABASE_URL=https://jchigqerypjwmszslzke.supabase.co`
  ⚠️ (2026-07-16) the LOCAL `search-service/.env` still has the OLD project
  `gbaqppxjrfqgnmhunhbb` and an old ngrok `IMAGE_SERVER_URL` — fix it before
  scp'ing, or skip scp for that file and edit on the box directly.
- the real `SUPABASE_KEY` (not the placeholder)
- BOTH `.env` files: `ALLOWED_ORIGINS=https://goxfused.com,https://6rl39pelkbakvtf9-78719418621.shopifypreview.com`
  (the shopifypreview.com origin is the shareable test link for people without
  store access — note Shopify rotates these preview subdomains, so when the
  link expires, add the new one here and restart both services)
- `onboarding-service/.env`: `ELEVENLABS_VOICE_ID=xoV6iGVuOGYHLWjXhVC7`,
  `ELEVENLABS_TTS_MODEL=eleven_flash_v2`, and prod URLs
  (`SEARCH_API_URL`/`PUBLIC_SEARCH_API_URL`/`WIDGET_SCRIPT_URL`/
  `IMAGE_SERVER_URL` all `https://api.teampop.com`)

CORS is read once at startup — restart both services after any
`ALLOWED_ORIGINS` change (§5).

## 3. Rebuild the widget
```bash
cd /home/ubuntu/sales_agent/www.teampop/frontend
npm install   # only if package.json changed
npm run build
```
Confirm `dist/widget.js` timestamp updated — onboarding-service serves it
straight from there, no separate copy step.

## 4. Install any new Python deps (skip if none changed)
```bash
cd /home/ubuntu/sales_agent/onboarding-service && source .venv/bin/activate && pip install -r requirements.txt && deactivate
cd /home/ubuntu/sales_agent/search-service && source .venv/bin/activate && pip install -r requirements.txt && deactivate
```

## 5. Restart services
```bash
sudo systemctl restart tp-onboard.service
sudo systemctl restart tp-search.service
sudo systemctl status tp-onboard.service tp-search.service --no-pager
```
Watch for clean startup — no `SUPABASE_KEY` auth errors, no `ELEVENLABS_API_KEY`
errors. `journalctl -u tp-onboard -n 50 --no-pager` if something looks wrong.

## 6. Push the updated agent prompt/voice to ElevenLabs — RUN THIS AFTER EVERY DEPLOY
Code changes to `elevenlabs_agent.py` (prompt, TTS settings) only take effect
on the **next PATCH to the existing agent** — restarting the service does NOT
re-push the prompt to an already-created agent.

**⚠️ This run is also the fix for the "promotions disappeared" regression
(2026-07-15):** the old `update_agent()` rebuilt the prompt with default store
context on EVERY call, so each §6b voice swap silently wiped the offers, store
name, and categories ("No active promotions to mention", "this store"). That
bug is fixed in code — voice-only calls no longer touch the prompt — but the
live agent still has the wiped prompt until you re-run this full-context PATCH.

Offers below verified against the live goxfused.com homepage on 2026-07-15.
```bash
cd /home/ubuntu/sales_agent/onboarding-service && source .venv/bin/activate
python3 -c "
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'))   # main.py does this automatically; a standalone script must do it explicitly
from elevenlabs_agent import ElevenLabsAgentCreator
creator = ElevenLabsAgentCreator()
creator.update_agent(
    agent_id='agent_4901kwna71tve5nbyy85c8v20yre',
    store_id='9cec7cd0-9252-4aa2-985b-71c2a42018cb',
    store_context={
        'store_name': 'Xfused',   # brand name — NEVER the domain-derived 'Goxfused'
        'description': 'skincare store',
        'categories': 'facewash, moisturiser, lip balm',
        'price_range': '₹299–₹399',
        'offers': 'Catalog prices are ALREADY the discounted offer prices: facewashes and moisturisers Rs 349 (12% off, regular Rs 399); lip balms Rs 299 (14% off, regular Rs 349). Checkout extras on top: extra 10% off first order, free shipping on orders ₹499+.',
    },
)
"
deactivate
```

### 6a. (Optional) Push the "Shopping Buddy" greeting
The greeting (first_message) is separate from the prompt and was edited by
hand in the ElevenLabs dashboard — check it there first. If it still needs
updating, `update_agent()` now supports patching it:
```python
creator.update_agent(
    agent_id='agent_4901kwna71tve5nbyy85c8v20yre',
    store_id='9cec7cd0-9252-4aa2-985b-71c2a42018cb',
    first_message=(
        \"Hi, welcome to Xfused! I'm your Xfused Shopping Buddy. \"
        \"You can also talk to me in Hinglish or Tamil — just speak in your language. \"
        \"What are you looking for today?\"
    ),
)
```
Note: if the agent's default language is now Hindi (dashboard change,
2026-07-15), the Hindi preset greeting in the dashboard's language settings is
what shoppers actually hear — update that one there too if needed
("Main hoon aapki Xfused Shopping Buddy").

## 6b. A/B test the voice candidates
Client flagged the current voice (Muskaan) as too high-pitched even after the
2026-07-14 TTS tuning pass. Four candidates from the ElevenLabs shared library,
all already added to the account this session:
- `dVTC43Yewy5fAIcmsISI` — "Anvi - Warm, Emotional Girlfriend": soft, young,
  hi-IN native, conversational/companion use-case
- `o6qTxWUeRyzRYZyUNDVJ` — "Irina - Energetic E-commerce Girl": young, hi-IN
  native, explicitly tuned for e-commerce/product-guidance conversations
- `1Z7Y8o9cvUeWq8oLKgMY` — "Tripti - Calm and Clear": middle-aged, hi-IN
  native, built specifically for Hindi customer-support/IVR/virtual-agent bots
  — closest persona fit to Wrina's role of the four
- `uYqzKDmOqxa1GrgoORxz` — "Pooja - Soft, Empathetic Therapy Voice": young,
  hi-IN native, built for mental-health/therapy companions — softest/calmest
  tone of the four, but check it doesn't read as too slow/gentle for a
  shopping context

`update_agent()` accepts `voice_id` and `tts_overrides` to PATCH just the
voice on the live agent — swap between them by re-running with a different
`voice_id`. **As of 2026-07-15 voice-only calls are guaranteed not to touch
the prompt** (the old version rebuilt it with blank store context on every
call, wiping the offers — that's why promotions vanished after voice swaps).
Make sure the deployed code includes that fix BEFORE running voice swaps, and
run §6 once after your last swap anyway, as a belt-and-braces restore:
```bash
cd /home/ubuntu/sales_agent/onboarding-service && source .venv/bin/activate
python3 -c "
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env'))
from elevenlabs_agent import ElevenLabsAgentCreator
creator = ElevenLabsAgentCreator()
creator.update_agent(
    agent_id='agent_4901kwna71tve5nbyy85c8v20yre',
    store_id='9cec7cd0-9252-4aa2-985b-71c2a42018cb',
    voice_id='o6qTxWUeRyzRYZyUNDVJ',  # or 'dVTC43Yewy5fAIcmsISI' / '1Z7Y8o9cvUeWq8oLKgMY' / 'uYqzKDmOqxa1GrgoORxz'
    tts_overrides={'stability': 0.6, 'similarity_boost': 0.68, 'speed': 0.97},
)
"
deactivate
```
Listen on both English and Hinglish turns each time — accent/pitch character
can shift noticeably between languages for the same voice. Once you pick one,
update `ELEVENLABS_VOICE_ID` in `onboarding-service/.env` too, so the NEXT full
`create_agent`/`update_agent` run (e.g. after any prompt change) doesn't
silently fall back to Muskaan.

## 6c. Session-metrics migration (2026-07-16 — run once in Supabase)
The widget now reports business/funnel metrics per session. Run this in the
xfused Supabase project's SQL editor (until then, the backend automatically
falls back to storing the legacy columns only, so nothing breaks):
```sql
alter table session_feedback
  add column if not exists searches int default 0,
  add column if not exists products_focused int default 0,
  add column if not exists cart_adds int default 0,
  add column if not exists cart_add_failures int default 0,
  add column if not exists cart_value_paise bigint default 0,
  add column if not exists checkout_initiated boolean default false,
  add column if not exists resumed_session boolean default false;
```
Related behavior change: the feedback panel now SURVIVES the go_to_cart
navigation (shown by the widget on the /cart page, restored from
sessionStorage) and never auto-dismisses — it stays until the shopper rates,
skips, or closes it. Successful adds also tag the Shopify cart with
`TeamPop Assisted` / `TeamPop Conversation` attributes, which appear on the
resulting ORDER in Shopify admin → the client can count and value
agent-assisted orders (Orders → filter/export by additional details).

## 7. Point the duplicate theme's widget embed at the right agent
**Performance (2026-07-15):** add `defer` to the widget script tag in the
theme's embed snippet — `<script src="https://api.teampop.com/widget/widget.js"
defer></script>` — so the ~375 KB (gzip) bundle downloads in parallel and only
executes AFTER the store page finishes parsing. Without `defer`, a plain
`<script src>` blocks the merchant page's HTML parsing while it downloads.
New snippets from `/onboard` include `defer` automatically now, but the
already-pasted snippet in the xfused theme must be edited by hand.

Confirm the duplicate theme's embed snippet (`<script>` block with
`window.__TEAM_POP_*` globals) has:
- `window.__TEAM_POP_AGENT_ID__` = the agent you just updated in step 6
- `window.__TEAM_POP_CART_ENABLED__ = true` (should already be true — it's a
  Shopify store)
- `window.__TEAM_POP_API_URL__` pointing at `https://api.teampop.com`

## 8. Smoke test
- Load the duplicate theme, tap the orb → the FULL panel window should open
  immediately with a large connecting screen (big pulsing orb + rotating
  "Setting up your assistant..." messages), then flip to "Connected — say
  what you're looking for" once live, then show products on first search
- Ask about offers ("kya offers hain?") → agent must mention the real xfused
  promotions (10% first order, free shipping ₹499+, 12–14% off) — regression
  test for the prompt-wipe bug: run a §6b voice swap, ask again, offers must
  STILL be there
- Ask for something off-portfolio ("do you have shampoo?") → agent searches,
  finds nothing, says it's not carried — and never PROACTIVELY offers
  haircare/wellness categories on its own
- Ask for details on "the second one" → the product it TALKS about must be
  the product FOCUSED on screen (detox-vs-drench mismatch check). If it still
  mismatches, pull the last few conversations in the ElevenLabs dashboard and
  check whether update_carousel_main_view was called with the wrong index
- End a session (≥10s) → feedback card should now be the large full-panel
  version and stay ~12s
- On a PHONE: start a session, switch to another app, come back → the agent
  should NOT have kept re-prompting into silence, and should acknowledge you're
  back (background-tab mitigation; mic-while-backgrounded itself is an OS
  limitation and cannot work)
- Add a product to cart by voice → confirm the header cart icon/badge updates
  IMMEDIATELY (not just after navigating to /cart) — this is the
  `syncThemeCartBadge` fix; if the theme's badge still doesn't move but `/cart`
  shows the right items, the theme isn't Dawn-based and doesn't match any of
  the generic selectors tried — inspect the real badge element's class/id and
  add it to the `selectors` list in `syncThemeCartBadge` (AvatarWidget.jsx)
- Say "checkout" → confirm it navigates to `/cart` within ~2-6s, and does NOT
  just end the session silently
- Speak a Hindi sentence → confirm it switches WITHIN THAT SAME reply (not one
  turn late), and without extraneous "are" fillers
- Ask about discounts → confirm the agent mentions the real xfused offers
- Disconnect mid-conversation (close tab) and reopen within 10 min → confirm
  cart badge + a brief "picking up where we left off" acknowledgment
