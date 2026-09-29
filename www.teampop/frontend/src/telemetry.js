// Widget error reporting — Sentry, scoped to the widget only.
//
// The widget runs inside a merchant's storefront, so we must NOT use
// Sentry.init(): that installs global handlers and would report every error
// the merchant's theme/apps throw. Instead we create an isolated BrowserClient
// + Scope (Sentry's recommended setup for embedded/shared environments) and
// only report what we explicitly capture, plus React render crashes via the
// ErrorBoundary in App.jsx.
//
// Config (all optional — no DSN = telemetry is a no-op):
//   build-time:  VITE_SENTRY_DSN, VITE_SENTRY_ENVIRONMENT, VITE_RELEASE
//   runtime:     window.__TEAM_POP_SENTRY_DSN__ overrides the build-time DSN
//
// Every event is tagged with conversation_id (ElevenLabs), agent_id and the
// storefront host, so a Sentry issue links straight to the conversations row
// / Grafana trace for the same call.

import {
  BrowserClient,
  Scope,
  defaultStackParser,
  getDefaultIntegrations,
  makeFetchTransport,
} from "@sentry/browser";

// Integrations that hook globals (window.onerror, fetch/console breadcrumbs,
// wrapped timers) are dropped — they'd capture merchant-page noise.
const GLOBAL_INTEGRATIONS = new Set(["BrowserApiErrors", "Breadcrumbs", "GlobalHandlers"]);

let scope = null;

function init() {
  const dsn = window.__TEAM_POP_SENTRY_DSN__ || import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return null;
  try {
    const client = new BrowserClient({
      dsn,
      transport: makeFetchTransport,
      stackParser: defaultStackParser,
      integrations: getDefaultIntegrations({}).filter((i) => !GLOBAL_INTEGRATIONS.has(i.name)),
      environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || "production",
      release: import.meta.env.VITE_RELEASE || undefined,
      sendDefaultPii: false,
      sampleRate: 1.0,
    });
    const s = new Scope();
    s.setClient(client);
    client.init();
    s.setTag("storefront", window.location.hostname);
    return s;
  } catch (e) {
    console.warn("[telemetry] Sentry init failed (non-blocking):", e);
    return null;
  }
}

scope = init();

export function setTelemetryContext({ conversationId, agentId } = {}) {
  if (!scope) return;
  if (conversationId !== undefined) scope.setTag("conversation_id", conversationId || "none");
  if (agentId !== undefined) scope.setTag("agent_id", agentId);
}

export function addBreadcrumb(message, data) {
  scope?.addBreadcrumb({ category: "widget", message, data, level: "info" });
}

/** Report a handled error. `context` becomes searchable extra data. */
export function reportError(error, context = {}) {
  if (!scope) return;
  try {
    const err = error instanceof Error ? error : new Error(typeof error === "string" ? error : JSON.stringify(error));
    scope.captureException(err, { captureContext: { extra: context, tags: context.where ? { where: context.where } : {} } });
  } catch { /* never let telemetry break the widget */ }
}

/** Report a notable non-exception condition (e.g. abnormal disconnect). */
export function reportMessage(message, context = {}, level = "warning") {
  if (!scope) return;
  try {
    scope.captureMessage(message, level, { captureContext: { extra: context } });
  } catch { /* ignore */ }
}
