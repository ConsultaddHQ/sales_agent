/**
 * Phase 2 — visitor-activity awareness (pure logic, framework-free).
 *
 * The host site detects raw activity (section in view, idle, CTA hover,
 * route, scroll) and emits it. The widget runs THIS reducer to decide
 * whether the sales agent should be told — with dedupe + throttling so we
 * inform the brain without spamming the live conversation.
 *
 * We only ever produce a contextual update (ambient context for the next
 * turn). We never force the agent to speak — the sales brain decides the
 * next move. That is what keeps this from regressing into the duplicate
 * narration the carousel path had to guard against.
 */

// Same activity won't re-notify within this window.
export const DEDUPE_MS = 20000
// Floor between two ambient notifications (protects the conversation).
// Strong buying signals bypass this.
export const MIN_INTERVAL_MS = 15000

export function initialActivityState() {
  return { lastKey: null, lastNotifyAt: -Infinity }
}

function idleBucket(seconds) {
  if (seconds < 45) return 'short'
  if (seconds < 90) return 'medium'
  return 'long'
}

export function summarizeActivity(evt) {
  if (!evt || typeof evt !== 'object') return ''
  switch (evt.type) {
    case 'section':
      return `looking at the ${evt.label || evt.id} section`
    case 'idle':
      return `idle for ${evt.seconds}s — may be losing interest`
    case 'cta':
      return `${evt.action === 'click' ? 'clicked' : 'hovering'} the "${evt.label}" button`
    case 'route':
      return evt.path === '/request'
        ? 'on the demo request page'
        : `on the ${evt.path} page`
    case 'scroll':
      return `scrolled ~${evt.depthPct}% through ${evt.area}`
    default:
      return ''
  }
}

export function formatContextualUpdate(summary) {
  return (
    `[VISITOR ACTIVITY] The visitor is ${summary}. ` +
    `Use this only if it helps the sale — do not narrate it; ` +
    `let the sales brain decide the next move.`
  )
}

function keyOf(evt) {
  if (!evt || typeof evt !== 'object') return null
  switch (evt.type) {
    case 'section':
      return `section:${evt.id}`
    case 'idle':
      return `idle:${idleBucket(evt.seconds)}`
    case 'cta':
      return `cta:${evt.action}:${evt.label}`
    case 'route':
      return `route:${evt.path}`
    case 'scroll':
      return `scroll:${evt.area}:${Math.round((evt.depthPct || 0) / 25) * 25}`
    default:
      return null
  }
}

function isPriority(evt) {
  return (
    (evt.type === 'cta' && evt.action === 'click') ||
    (evt.type === 'route' && evt.path === '/request')
  )
}

/**
 * @returns {{ state: object, notify: boolean, message: string|null }}
 * `state` is unchanged (same reference) when nothing is emitted.
 */
export function reduceActivity(state, evt, now) {
  const key = keyOf(evt)
  if (key === null) return { state, notify: false, message: null }

  const sinceLast = now - state.lastNotifyAt

  // Dedupe: identical activity still inside the window — stay quiet.
  if (key === state.lastKey && sinceLast < DEDUPE_MS) {
    return { state, notify: false, message: null }
  }

  // Throttle: too soon since the last update, and not a strong signal.
  if (!isPriority(evt) && sinceLast < MIN_INTERVAL_MS) {
    return { state, notify: false, message: null }
  }

  const message = formatContextualUpdate(summarizeActivity(evt))
  return {
    state: { lastKey: key, lastNotifyAt: now },
    notify: true,
    message,
  }
}
