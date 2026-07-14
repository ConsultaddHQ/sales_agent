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
- the real `SUPABASE_KEY` (not the placeholder)
- `onboarding-service/.env`: `ELEVENLABS_VOICE_ID=xoV6iGVuOGYHLWjXhVC7`,
  `ELEVENLABS_TTS_MODEL=eleven_flash_v2`, and prod URLs
  (`SEARCH_API_URL`/`PUBLIC_SEARCH_API_URL`/`WIDGET_SCRIPT_URL`/
  `IMAGE_SERVER_URL` all `https://api.teampop.com`, `ALLOWED_ORIGINS=https://goxfused.com`)

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

## 6. Push the updated agent prompt/voice to ElevenLabs
Code changes to `elevenlabs_agent.py` (prompt, TTS settings) only take effect
on the **next PATCH to the existing agent** — restarting the service does NOT
re-push the prompt to an already-created agent. Run this from the box (inside
the onboarding-service venv) to update xfused's live agent in place:
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
        'store_name': 'Xfused',
        'description': 'skincare store',
        'categories': 'facewash, moisturiser, lip balm',
        'price_range': '₹299–₹399',
        'offers': '10% off first order, free shipping on orders ₹499+, up to 14% off select products',
    },
)
"
deactivate
```
Fill in the real `agent_id` / `store_id` (check Supabase `agent_requests` or
the admin dashboard for xfused's row). This is also where the store_offers
text from this session's WebFetch of goxfused.com actually gets pushed live —
until this runs, the agent is still on its old prompt regardless of what's in
`elevenlabs_agent.py`.

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

`update_agent()` now accepts `voice_id` and `tts_overrides` to PATCH just the
voice on the live agent without touching the prompt logic — swap between them
by re-running with a different `voice_id`:
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

## 7. Point the duplicate theme's widget embed at the right agent
Confirm the duplicate theme's embed snippet (`<script>` block with
`window.__TEAM_POP_*` globals) has:
- `window.__TEAM_POP_AGENT_ID__` = the agent you just updated in step 6
- `window.__TEAM_POP_CART_ENABLED__ = true` (should already be true — it's a
  Shopify store)
- `window.__TEAM_POP_API_URL__` pointing at `https://api.teampop.com`

## 8. Smoke test
- Load the duplicate theme, open the widget, confirm it connects (rotating
  "Connecting... / Setting up your assistant..." messages should show)
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
