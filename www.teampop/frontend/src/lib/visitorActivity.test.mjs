// Phase 2 — pure visitor-activity logic. Zero-dep: `node --test`.
// The React/observer glue is thin; THIS is where the real rules live, so
// this is what we test (TDD, per repo mandate — no JS runner existed).

import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  summarizeActivity,
  formatContextualUpdate,
  reduceActivity,
  initialActivityState,
  DEDUPE_MS,
  MIN_INTERVAL_MS,
} from './visitorActivity.js'

test('summarizeActivity renders each event type as a human phrase', () => {
  assert.match(summarizeActivity({ type: 'section', id: 'cta', label: 'pricing' }), /pricing/)
  assert.match(summarizeActivity({ type: 'idle', seconds: 25 }), /idle.*25/)
  assert.match(
    summarizeActivity({ type: 'cta', action: 'hover', label: 'Get a demo' }),
    /hovering.*Get a demo/,
  )
  assert.match(summarizeActivity({ type: 'route', path: '/request' }), /demo request/)
  assert.match(summarizeActivity({ type: 'scroll', depthPct: 90, area: 'how-it-works' }), /how-it-works/)
})

test('formatContextualUpdate tags it and defers to the brain (no forced narration)', () => {
  const m = formatContextualUpdate('looking at pricing')
  assert.match(m, /\[VISITOR ACTIVITY\]/)
  assert.match(m, /looking at pricing/)
  assert.match(m, /sales brain|let the .*decide|do not narrate/i)
})

test('reducer notifies on a fresh activity', () => {
  const r = reduceActivity(initialActivityState(), { type: 'section', id: 'cta', label: 'pricing' }, 1000)
  assert.equal(r.notify, true)
  assert.match(r.message, /\[VISITOR ACTIVITY\]/)
})

test('reducer dedupes the same activity within the dedupe window', () => {
  const evt = { type: 'section', id: 'how-it-works', label: 'how it works' }
  const r1 = reduceActivity(initialActivityState(), evt, 1000)
  const r2 = reduceActivity(r1.state, evt, 1000 + DEDUPE_MS - 1)
  assert.equal(r1.notify, true)
  assert.equal(r2.notify, false) // same key, still within window → suppressed
})

test('reducer throttles non-priority events below the min interval', () => {
  const r1 = reduceActivity(initialActivityState(), { type: 'section', id: 'top', label: 'hero' }, 1000)
  const r2 = reduceActivity(
    r1.state,
    { type: 'section', id: 'how-it-works', label: 'how it works' },
    1000 + MIN_INTERVAL_MS - 1,
  )
  assert.equal(r1.notify, true)
  assert.equal(r2.notify, false) // different activity but too soon → protect the conversation
})

test('priority signals (CTA click, /request) bypass the throttle', () => {
  const r1 = reduceActivity(initialActivityState(), { type: 'section', id: 'top', label: 'hero' }, 1000)
  const r2 = reduceActivity(
    r1.state,
    { type: 'cta', action: 'click', label: 'Get a demo' },
    1500, // well within MIN_INTERVAL
  )
  assert.equal(r2.notify, true) // strong buying signal — worth interrupting for
})

test('escalating idle re-notifies (different bucket), repeated same idle does not', () => {
  const s0 = initialActivityState()
  const a = reduceActivity(s0, { type: 'idle', seconds: 25 }, 1000)
  const b = reduceActivity(a.state, { type: 'idle', seconds: 25 }, 1000 + DEDUPE_MS - 1)
  const c = reduceActivity(b.state, { type: 'idle', seconds: 60 }, 1000 + MIN_INTERVAL_MS + 1)
  assert.equal(a.notify, true)
  assert.equal(b.notify, false) // same idle bucket
  assert.equal(c.notify, true) // escalated idle is new information
})

test('unknown / malformed events are ignored and do not mutate state', () => {
  const s0 = initialActivityState()
  const r = reduceActivity(s0, { type: 'wat' }, 1000)
  assert.equal(r.notify, false)
  assert.deepEqual(r.state, s0)
  const r2 = reduceActivity(s0, null, 1000)
  assert.equal(r2.notify, false)
})
