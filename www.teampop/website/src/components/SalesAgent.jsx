import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

/**
 * Embeds the <team-pop-agent> voice widget on Team Pop's own marketing site
 * and exposes window.__TEAM_POP_HOST__ — the seam the agent's in-page action
 * tools (navigate_site / open_booking / prefill_demo_form) call into.
 *
 * The widget is the built IIFE served by onboarding-service at
 * /widget/widget.js (never the Vite dev build — project invariant).
 *
 * Phase 0: embed + host bridge scaffold. Phases 2/4 wire awareness +
 * the assisted close on top of this same bridge.
 */
const AGENT_ID = import.meta.env.VITE_SALES_AGENT_ID || ''
const WIDGET_URL =
  import.meta.env.VITE_WIDGET_URL || 'http://localhost:8005/widget/widget.js'

// Known navigation targets → in-page anchor id (see Landing.jsx) or route.
const ROUTE_TARGETS = { 'request-demo': '/request', request: '/request', demo: '/request' }
const SECTION_IDS = {
  top: 'top',
  'how-it-works': 'how-it-works',
  how: 'how-it-works',
  faq: 'faq',
  cta: 'cta',
  pricing: 'cta', // no dedicated pricing section yet — CTA is closest
}

function scrollToSection(id) {
  const el = document.getElementById(id)
  if (!el) return false
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return true
}

function highlightSection(id) {
  const el = document.getElementById(id)
  if (!el) return
  el.classList.add('teampop-highlight')
  setTimeout(() => el.classList.remove('teampop-highlight'), 2600)
}

export default function SalesAgent() {
  const navigate = useNavigate()

  useEffect(() => {
    if (!AGENT_ID) {
      console.warn('[TeamPop] VITE_SALES_AGENT_ID not set — sales agent not embedded.')
      return
    }

    // 1. Host bridge — the agent's in-page action tools call into this.
    window.__TEAM_POP_HOST__ = {
      navigate(target, { highlight = false } = {}) {
        const key = String(target || '').toLowerCase().trim()
        if (ROUTE_TARGETS[key]) {
          navigate(ROUTE_TARGETS[key])
          return { ok: true, kind: 'route', target: ROUTE_TARGETS[key] }
        }
        const sectionId = SECTION_IDS[key] || key
        // Section lives on the landing route; go there first if elsewhere.
        if (window.location.pathname !== '/') {
          navigate('/')
          setTimeout(() => {
            scrollToSection(sectionId)
            if (highlight) highlightSection(sectionId)
          }, 350)
          return { ok: true, kind: 'route+section', target: sectionId }
        }
        const found = scrollToSection(sectionId)
        if (found && highlight) highlightSection(sectionId)
        return { ok: found, kind: 'section', target: sectionId }
      },
      highlight(target) {
        highlightSection(SECTION_IDS[String(target || '').toLowerCase()] || target)
      },
      // Assisted close (fully wired in Phase 4). Stash prefill so RequestPage
      // can read it; never auto-submits.
      prefillDemoForm(fields = {}) {
        try {
          sessionStorage.setItem('teampop_demo_prefill', JSON.stringify(fields))
        } catch (e) {
          console.warn('[TeamPop] prefill stash failed', e)
        }
        return { ok: true }
      },
      openBooking(fields = {}) {
        try {
          sessionStorage.setItem('teampop_demo_prefill', JSON.stringify(fields))
        } catch {
          /* non-fatal */
        }
        navigate('/request')
        return { ok: true }
      },
    }

    // 2. Inject the widget once.
    window.__TEAM_POP_AGENT_ID__ = AGENT_ID
    if (!document.querySelector('team-pop-agent')) {
      if (!document.querySelector(`script[src="${WIDGET_URL}"]`)) {
        const s = document.createElement('script')
        s.src = WIDGET_URL
        s.async = true
        document.body.appendChild(s)
      }
      document.body.appendChild(document.createElement('team-pop-agent'))
    }

    return () => {
      delete window.__TEAM_POP_HOST__
    }
  }, [navigate])

  return null
}
