import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  useConversation,
  useConversationClientTool,
  useConversationMode,
} from "@elevenlabs/react";
import "../styles/AvatarWidget.css";
import "../styles/ptt.css";
import { useVoiceMode } from "../hooks/useVoiceMode";
// eslint-disable-next-line no-unused-vars -- motion is used as <motion.div> in JSX
import { motion, AnimatePresence, useMotionValue } from "framer-motion";
import { usePttInteraction } from "../hooks/usePttInteraction";

// Served from the widget mount (onboarding-service mounts dist/ at /widget),
// not the page root — a bare "/image.png" 404s against the host origin.
const DUMMY_IMAGE = "/widget/image.png";
const USER_INACTIVITY_TIMEOUT_MS = 30000;
const SESSION_HARD_LIMIT_MS = 420000;

// Session continuity — client ask: if the agent or shopper closes the session
// (accidentally, or via the hard/inactivity limit), a reconnect within this
// window should pick up where it left off instead of starting cold. Scoped to
// sessionStorage (tab-lifetime, not persisted across browser restarts) and
// consumed once on restore so a later, unrelated session doesn't inherit stale
// context.
const SESSION_CONTEXT_STORAGE_KEY = "team-pop-session-context";
const SESSION_CONTEXT_TTL_MS = 10 * 60 * 1000; // 10 minutes

function loadSessionContext() {
  try {
    const raw = sessionStorage.getItem(SESSION_CONTEXT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.savedAt || Date.now() - parsed.savedAt > SESSION_CONTEXT_TTL_MS) {
      sessionStorage.removeItem(SESSION_CONTEXT_STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch (_e) {
    return null;
  }
}

function clearSessionContext() {
  try { sessionStorage.removeItem(SESSION_CONTEXT_STORAGE_KEY); } catch (_e) { /* ignore */ }
}

// Best-effort: keep the THEME's own header cart icon/badge in sync immediately after
// an add-to-cart driven by voice/the carousel button. Shopify themes normally only
// refresh their cart icon in response to THEIR OWN JS calling /cart/add.js — an
// external caller like this widget leaves it stale until the shopper navigates to
// /cart (a full page load, which is server-rendered and always correct). Two layers,
// each a no-op if it doesn't apply to the live theme:
//  1. Dawn (Shopify's default OS2.0 theme, and most themes forked from it) exposes a
//     dedicated #cart-icon-bubble section — refetch + swap its HTML via the Section
//     Rendering API (`?sections=`), the same mechanism Dawn's own cart.js uses.
//  2. Generic fallback: patch common cart-count selectors' text directly so
//     non-Dawn themes at least show the right number without a full re-render.
async function syncThemeCartBadge(cart) {
  if (!cart) return;
  try {
    const r = await fetch('/?sections=cart-icon-bubble');
    if (r.ok) {
      const data = await r.json();
      const html = data?.['cart-icon-bubble'];
      const el = html && document.getElementById('cart-icon-bubble');
      if (el) { el.innerHTML = html; return; }
    }
  } catch (_e) { /* theme has no cart-icon-bubble section — fall through to generic patch */ }

  const count = cart.item_count ?? 0;
  // .js-cart-count confirmed live on goxfused.com (2026-07-14) — renders as "(0)" in
  // the header and plain "0" in the mini-cart drawer, so preserve whatever non-digit
  // wrapper (parens, etc.) is already there instead of blindly overwriting textContent.
  const selectors = ['.js-cart-count', '.cart-count-bubble', '[data-cart-count]', '.cart-count', '#CartCount', '.cart-link__bubble'];
  selectors.forEach((sel) => {
    document.querySelectorAll(sel).forEach((el) => {
      el.textContent = /\d/.test(el.textContent)
        ? el.textContent.replace(/\d+/, String(count))
        : String(count);
    });
  });
}

// Voice transport: "websocket" | "webrtc". Single toggle for the whole widget.
//
// - "websocket": streams raw PCM (no lossy Opus codec, no WebRTC DSP). On a
//   stable network this is the CLEANEST agent audio — no compression artifacts,
//   no jitter-buffer time-stretching. Trade-off: no built-in echo cancellation /
//   noise suppression, and less resilient to packet loss on poor mobile networks.
//   The first_message audio-drop race that forced us off WebSocket was a bug in the
//   OLD SDK (@elevenlabs/client 1.1.1) and is FIXED in 1.13 (pendingAudioEvents buffer),
//   so WebSocket is safe again on the current SDK.
// - "webrtc": Opus over a LiveKit transport with echo cancellation + noise removal +
//   packet-loss concealment. Best for noisy/mobile, but Opus + PLC can sound grainy or
//   "elongated" (time-stretched) when the network jitters.
//
// getInputVolume() (orb LISTENING driver) works under BOTH on @elevenlabs/client ≥1.13.
//
// DEFAULT webrtc (2026-07-07). The mid-conversation volume collapse initially blamed
// on websocket ducking turned out to be the VOICE (Anya: -36dB collapse on descriptive
// text, proven by RMS A/B — see decisions.md); webrtc is kept as default for its
// native echo cancellation (websocket raw-PCM playback has none — echo risk on
// speaker+mic setups) and congestion handling (a 9s update_products stall was
// observed under websocket backpressure). Overridable at runtime for A/B testing:
//   ?transport=websocket|webrtc  (URL param, wins)
//   window.__TEAM_POP_TRANSPORT__ = "websocket"|"webrtc"  (embed global)
// websocket trades AEC for cleaner raw-PCM audio on stable wired networks.
const CONNECTION_TYPE = (() => {
  try {
    const p = new URLSearchParams(window.location.search).get("transport");
    if (p === "websocket" || p === "webrtc") return p;
  } catch { /* SSR/no-window: fall through */ }
  const g = typeof window !== "undefined" ? window.__TEAM_POP_TRANSPORT__ : null;
  if (g === "websocket" || g === "webrtc") return g;
  return "webrtc";
})();
const IGNORED_SILENCE_TRANSCRIPTS = new Set([
  "ah",
  "aha",
  "alright",
  "hmm",
  "hm",
  "mm",
  "mmhmm",
  "mm hmm",
  "ok",
  "okay",
  "uh",
  "um",
  "yeah",
  "yep",
  "yes",
]);
const WIDGET_LAYER_STYLE = {
  position: "fixed",
  bottom: "0",
  left: "0",
  width: "100%",
  height: "100%",
  zIndex: 2147483647,
  pointerEvents: "none",
  isolation: "isolate",
};

// ─── ShoppingCard ─────────────────────────────────────────────────────────────

const ShoppingCard = ({ product, isActive, highlightPrice, onShopNow }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`shopping-card ${isActive ? "card-active" : "card-dimmed"}`}
    >
      <div className="shopping-card-info">
        <div className="shopping-card-title">{product.name}</div>
        {product.description && (
          <div className="flex flex-col gap-1">
            <div
              className={`shopping-card-desc text-sm text-gray-600 transition-all ${!isExpanded ? "line-clamp-2" : ""}`}
            >
              {product.description}
            </div>
            <button
              onClick={(e) => {
                e.preventDefault();
                setIsExpanded(!isExpanded);
              }}
              className="text-xs text-blue-400 self-start font-semibold mt-1"
            >
              {isExpanded ? "Show less" : "Read more"}
            </button>
          </div>
        )}
        <div
          className={`shopping-card-price text-xl font-bold mt-2 ${isActive && highlightPrice ? "price-glow text-green-400" : "text-green-300"}`}
        >
          {product.price
            ? `₹${Number(product.price).toLocaleString("en-IN")}`
            : "Check Price"}
        </div>
        <a
          href={product.product_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={onShopNow}
          className="shopping-cta mt-3 text-center bg-white text-black px-6 py-2 rounded-full font-bold text-sm hover:bg-gray-200 transition"
        >
          Shop Now
        </a>
      </div>
    </div>
  );
};

// ─── FeedbackCard ─────────────────────────────────────────────────────────────

const FOLLOW_UP_OPTIONS = {
  positive: ["Found what I wanted", "Great recommendations", "Fun to talk to", "Fast & responsive"],
  neutral:  ["Didn't find my product", "Too slow", "Answers weren't helpful", "Just browsing"],
  negative: ["Couldn't understand me", "Wrong products shown", "Too many questions", "Technical issue"],
};
const FOLLOW_UP_PROMPTS = {
  positive: "What did you like most?",
  neutral:  "What could be better?",
  negative: "What went wrong?",
};

function FeedbackCard({ onRate, onDismiss, onStepChange }) {
  const [step, setStep] = useState(1);
  const [rating, setRating] = useState(null);

  const handleEmoji = (r) => {
    setRating(r);
    setStep(2);
    onStepChange?.(); // notify parent to cancel/extend auto-dismiss timer
  };

  const handleTag = (tag) => {
    onRate(rating, tag);
  };

  // Rendered inside the full feedback panel (see activeView === "FEEDBACK") —
  // sized up per client feedback 2026-07-15: the old small bottom-right card
  // was too easy to miss.
  if (step === 1) {
    return (
      <motion.div
        key="feedback-step1"
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.95 }}
        className="flex flex-col items-center gap-5 p-8 bg-zinc-900 rounded-3xl border border-white/10 shadow-2xl pointer-events-auto w-80 max-w-[90%]"
      >
        <span className="text-white text-lg font-bold text-center">How was your experience?</span>
        <div className="flex gap-5">
          {[["😍", "positive"], ["😐", "neutral"], ["😕", "negative"]].map(([emoji, r]) => (
            <button
              key={r}
              onClick={() => handleEmoji(r)}
              className="w-16 h-16 rounded-full bg-zinc-800 hover:bg-zinc-700 border border-white/10 hover:border-white/30 transition-all flex items-center justify-center text-3xl hover:scale-110 active:scale-95"
              aria-label={r}
            >
              {emoji}
            </button>
          ))}
        </div>
        <button onClick={onDismiss} className="text-gray-400 text-sm hover:text-gray-200 transition-colors cursor-pointer">
          Skip
        </button>
      </motion.div>
    );
  }

  return (
    <motion.div
      key="feedback-step2"
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.95 }}
      className="flex flex-col items-center gap-4 p-8 bg-zinc-900 rounded-3xl border border-white/10 shadow-2xl pointer-events-auto w-80 max-w-[90%]"
    >
      <span className="text-white text-lg font-bold text-center">{FOLLOW_UP_PROMPTS[rating]}</span>
      <div className="flex flex-col gap-2.5 w-full">
        {FOLLOW_UP_OPTIONS[rating].map((tag) => (
          <button
            key={tag}
            onClick={() => handleTag(tag)}
            className="w-full px-4 py-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 border border-white/10 hover:border-white/30 text-gray-200 text-sm text-left transition-all hover:text-white cursor-pointer"
          >
            {tag}
          </button>
        ))}
      </div>
      <button onClick={onDismiss} className="text-gray-400 text-sm hover:text-gray-200 transition-colors mt-1 cursor-pointer">
        Skip
      </button>
    </motion.div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const formatMessage = (text) => {
  if (!text) return "";
  let formatted = text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br />");
  formatted = formatted.replace(/(\d+\.)\s/g, "<br/>$1 ");
  return formatted;
};

const isMeaningfulUserSpeech = (text) => {
  const normalized = String(text || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!normalized) return false;
  if (IGNORED_SILENCE_TRANSCRIPTS.has(normalized)) return false;
  return normalized.length >= 2;
};

/**
 * Derive a single visual-state token from conversation + PTT state.
 * This is the source of truth for orb CSS class and status pill copy.
 *
 * VAD states  : IDLE | CONNECTING | LISTENING | THINKING | AGENT_SPEAKING | ERROR
 * PTT states  : PTT_READY | CONNECTING | PTT_MUTED_CONNECTED | PTT_HOLDING | ERROR
 */
function getVisualState({ status, interactionMode, isPressActive, vadSubState }) {
  if (status === "connecting") return "CONNECTING";
  if (status === "error") return "ERROR";

  if (status === "connected") {
    if (interactionMode === "ptt") {
      return isPressActive ? "PTT_HOLDING" : "PTT_MUTED_CONNECTED";
    }
    return vadSubState || "LISTENING";
  }

  // disconnected
  return interactionMode === "ptt" ? "PTT_READY" : "IDLE";
}

// Rotated while visualState === "CONNECTING" so the handshake (a few seconds,
// like a phone call connecting) reads as active progress rather than a stalled
// spinner. See CONNECTING_MESSAGE_INTERVAL_MS for the rotation cadence.
const CONNECTING_MESSAGES = [
  "Connecting...",
  "Setting up your assistant...",
  "Almost ready...",
];
const CONNECTING_MESSAGE_INTERVAL_MS = 1500;

/**
 * Map visual state to shopper-facing status pill text.
 * connectingMessageIndex only matters for the CONNECTING state (see OrbDock).
 */
function getStatusLabel(visualState, connectingMessageIndex = 0) {
  switch (visualState) {
    case "IDLE":                return "Talk to AI";
    case "CONNECTING":          return CONNECTING_MESSAGES[connectingMessageIndex % CONNECTING_MESSAGES.length];
    case "LISTENING":           return "Listening...";
    case "THINKING":            return "Thinking...";
    case "AGENT_SPEAKING":      return "Speaking...";
    case "PTT_READY":           return "Hold to speak";
    case "PTT_MUTED_CONNECTED": return "Hold to talk";
    case "PTT_HOLDING":         return "Listening";
    case "ERROR":               return "Retry";
    default:                    return "";
  }
}

// ─── PanelSessionScreen ──────────────────────────────────────────────────────
// Full-panel status screen rendered in the products panel's empty area while a
// session is connecting / connected-but-no-products-yet (client feedback
// 2026-07-15: the small status pill was too easy to miss — this makes the
// connection state unmissable, the way the ElevenLabs widget does it).
function PanelSessionScreen({ visualState }) {
  const [msgIndex, setMsgIndex] = useState(0);
  const isConnecting = visualState === "CONNECTING";

  useEffect(() => {
    if (!isConnecting) { setMsgIndex(0); return undefined; }
    const id = setInterval(
      () => setMsgIndex((i) => (i + 1) % CONNECTING_MESSAGES.length),
      CONNECTING_MESSAGE_INTERVAL_MS,
    );
    return () => clearInterval(id);
  }, [isConnecting]);

  if (isConnecting) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-zinc-900 pointer-events-auto pt-16">
        <div className="panel-session-orb panel-session-orb--connecting mb-8" aria-hidden="true" />
        <h2 className="text-xl font-bold text-amber-300 mb-3 tracking-wide flex items-center justify-center gap-2.5">
          <svg className="connecting-spinner w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
            <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
          </svg>
          <span aria-live="polite">{CONNECTING_MESSAGES[msgIndex]}</span>
        </h2>
        <p className="text-gray-400 text-sm max-w-[250px] mx-auto leading-relaxed">
          Getting your assistant on the line — usually takes a few seconds.
        </p>
      </div>
    );
  }

  // Connected, but no products shown yet — invite the shopper to speak so the
  // window doesn't feel dead between connect and the first search result.
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-zinc-900 pointer-events-auto pt-16">
      <div className="panel-session-orb panel-session-orb--live mb-8" aria-hidden="true" />
      <h2 className="text-xl font-bold text-emerald-300 mb-3 tracking-wide">I'm listening!</h2>
      <p className="text-gray-300 text-sm max-w-[260px] mx-auto leading-relaxed">
        Just say what you're looking for — like &ldquo;show me a facewash&rdquo; or &ldquo;something for dry skin&rdquo;.
      </p>
    </div>
  );
}

// ─── OrbDock ─────────────────────────────────────────────────────────────────

/**
 * Shared orb dock capsule used in both the closed-dock view (NONE)
 * and the products-overlay dock (PRODUCTS).
 *
 * Props:
 *   visualState      — from getVisualState()
 *   interactionMode  — "vad" | "ptt"
 *   setMode          — toggles interactionMode
 *   isConnected      — conversation.status === "connected"
 *   onOrbClick       — VAD tap handler
 *   onPointerDown    — PTT press begin
 *   onPointerUp      — PTT press end
 *   onPointerCancel  — PTT press cancel
 *   onKeyDown        — keyboard hold start
 *   onKeyUp          — keyboard hold end
 *   onEndSession     — explicit end-session (PTT mode)
 *   onRightAction    — right-side dock button (e.g. Chat)
 *   scale            — optional CSS scale string for orb-wrapper (e.g. "scale-75")
 *   style            — optional inline styles for the dock container
 */
function OrbDock({
  visualState,
  interactionMode,
  setMode,
  isConnected,
  onOrbClick,
  onPointerDown,
  onPointerUp,
  onPointerCancel,
  onKeyDown,
  onKeyUp,
  onEndSession,
  onRightAction,
  rightLabel = "Chat",
  scale = "",
  style = {},
  inactive = false,
}) {
  const [connectingMessageIndex, setConnectingMessageIndex] = useState(0);
  useEffect(() => {
    if (visualState !== "CONNECTING") {
      setConnectingMessageIndex(0);
      return;
    }
    const id = setInterval(() => {
      setConnectingMessageIndex((i) => i + 1);
    }, CONNECTING_MESSAGE_INTERVAL_MS);
    return () => clearInterval(id);
  }, [visualState]);
  const statusLabel = getStatusLabel(visualState, connectingMessageIndex);
  const isPtt = interactionMode === "ptt";

  const PILL_STYLES = {
    LISTENING:     "bg-green-500/20 text-green-400 border-green-500/30 shadow-[0_0_10px_rgba(34,197,94,0.2)]",
    THINKING:      "bg-cyan-500/20 text-cyan-400 border-cyan-500/30 shadow-[0_0_10px_rgba(6,182,212,0.2)]",
    AGENT_SPEAKING:"bg-purple-500/20 text-purple-400 border-purple-500/30 shadow-[0_0_10px_rgba(168,85,247,0.2)]",
    // Bolder than the other states — client feedback: the connecting pill wasn't
    // noticeable enough to signal "actively working on it". Higher opacity fill,
    // brighter border, plus the status-pill-connecting breathing glow (CSS).
    CONNECTING:    "bg-amber-500/30 text-amber-300 border-amber-400/70 shadow-[0_0_14px_rgba(245,158,11,0.4)] status-pill-connecting",
    PTT_HOLDING:   "bg-green-500/20 text-green-400 border-green-500/30 shadow-[0_0_10px_rgba(34,197,94,0.2)]",
  };
  const pillStyle = PILL_STYLES[visualState] || "bg-zinc-800/80 text-gray-400 border-white/5";
  const isConnecting = visualState === "CONNECTING";

  return (
    <div className={`orb-dock ${inactive ? "inactive" : ""}`} style={style}>
      {/* Left — mode toggle */}
      <div className="flex-1 flex justify-start items-center">
        <div className="mode-toggle" role="group" aria-label="Voice mode">
          <button
            className={`mode-toggle-btn ${interactionMode === "vad" ? "active" : ""}`}
            onClick={() => setMode("vad")}
            aria-pressed={interactionMode === "vad"}
          >
            Auto
          </button>
          <button
            className={`mode-toggle-btn ${interactionMode === "ptt" ? "active" : ""}`}
            onClick={() => setMode("ptt")}
            aria-pressed={interactionMode === "ptt"}
          >
            Hold
          </button>
        </div>
      </div>

      {/* Center — orb */}
      <div className="relative flex-shrink-0 flex flex-col items-center justify-center">
        <span
          className={`absolute uppercase font-bold tracking-widest rounded-full whitespace-nowrap transition-all duration-300 border flex items-center gap-1.5 ${
            isConnecting ? "-top-8 text-[11px] px-3 py-1" : "-top-7 text-[9px] px-2 py-0.5"
          } ${pillStyle}`}
        >
          {visualState === "IDLE" && (
            <svg className="w-2.5 h-2.5 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V20H9v2h6v-2h-2v-2.08A7 7 0 0 0 19 11h-2z"/>
            </svg>
          )}
          {isConnecting && (
            <svg className="w-3 h-3 flex-shrink-0 connecting-spinner" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.25" />
              <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          )}
          {statusLabel}
        </span>

        <button
          className={`orb-wrapper ${visualState} ${scale} cursor-pointer`}
          style={{ background: "none", border: "none", padding: 0, marginTop: scale ? "4px" : undefined }}
          /* VAD: regular click */
          onClick={!isPtt ? onOrbClick : undefined}
          /* PTT: pointer hold events */
          onPointerDown={isPtt ? onPointerDown : undefined}
          onPointerUp={isPtt ? onPointerUp : undefined}
          onPointerCancel={isPtt ? onPointerCancel : undefined}
          /* Keyboard: hold for PTT, activate for VAD */
          onKeyDown={onKeyDown}
          onKeyUp={isPtt ? onKeyUp : undefined}
          aria-label={isPtt ? "Hold to talk" : statusLabel}
          /* Prevent text selection during hold */
          onDragStart={(e) => e.preventDefault()}
        >
          <div className="orb-core orb-pearl" />
        </button>
      </div>

      {/* Right — Chat or End */}
      <div className="flex-1 flex justify-end items-center gap-2">
        {isPtt && isConnected && (
          <button className="end-session-btn" onClick={onEndSession}>
            End
          </button>
        )}
        <button
          className="dock-action text-[11px] font-bold text-gray-300 hover:text-white uppercase tracking-wider"
          onClick={onRightAction}
        >
          {rightLabel}
        </button>
      </div>
    </div>
  );
}

// ─── ProductDetails ───────────────────────────────────────────────────────────

const ProductDetails = ({ product, highlightPrice, cartedCount = 0, onShopNow, onAddToCart }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [qty, setQty] = useState(1);

  const price = product.price
    ? `₹${Number(product.price).toLocaleString("en-IN")}`
    : "Check Price";

  return (
    <div className="flex flex-col gap-2 text-white">
      <div className="font-bold text-base leading-tight">{product.name}</div>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div
          className={`text-xl font-bold ${highlightPrice ? "price-glow text-green-400" : "text-green-300"}`}
        >
          {price}
        </div>
        <a
          href={product.product_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={onShopNow}
          className="shopping-cta text-center bg-white text-black px-5 py-2 rounded-full font-bold text-sm hover:bg-gray-200 transition"
        >
          Shop Now
        </a>
        {onAddToCart && (
          <div className="flex items-center gap-2">
            <div className="flex items-center border border-white/25 rounded-full overflow-hidden">
              <button
                onClick={(e) => { e.preventDefault(); setQty((q) => Math.max(1, q - 1)); }}
                className="w-7 h-7 flex items-center justify-center text-white text-sm hover:bg-white/10 transition"
                aria-label="Decrease quantity"
              >
                −
              </button>
              <span className="w-6 text-center text-sm font-semibold">{qty}</span>
              <button
                onClick={(e) => { e.preventDefault(); setQty((q) => Math.min(10, q + 1)); }}
                className="w-7 h-7 flex items-center justify-center text-white text-sm hover:bg-white/10 transition"
                aria-label="Increase quantity"
              >
                +
              </button>
            </div>
            <button
              onClick={(e) => { e.preventDefault(); onAddToCart(product, qty); }}
              className="shopping-cta text-center bg-green-500 text-white px-5 py-2 rounded-full font-bold text-sm hover:bg-green-600 transition"
            >
              {cartedCount > 0 ? "Add more" : "Add to Cart"}
            </button>
          </div>
        )}
      </div>
      {cartedCount > 0 && (
        <div className="text-xs text-green-400 font-semibold">In cart: {cartedCount}</div>
      )}
      {product.description && (
        <div className="flex flex-col gap-1">
          <div
            className={`text-sm text-gray-400 transition-all ${!isExpanded ? "line-clamp-2" : ""}`}
          >
            {product.description}
          </div>
          <button
            onClick={(e) => { e.preventDefault(); setIsExpanded(!isExpanded); }}
            className="text-xs text-blue-400 self-start font-semibold"
          >
            {isExpanded ? "Show less" : "Read more"}
          </button>
        </div>
      )}
    </div>
  );
};

// ─── FirstVisitNudge ──────────────────────────────────────────────────────────

function FirstVisitNudge({ onDismiss }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 6000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <motion.div
      key="nudge"
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, scale: 0.9 }}
      style={{ position: "fixed", bottom: "100px", right: "20px" }}
      className="flex items-start gap-2 px-3 py-2.5 bg-zinc-900/95 backdrop-blur-md rounded-2xl border border-white/10 shadow-2xl pointer-events-auto max-w-[210px]"
    >
      <svg className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V20H9v2h6v-2h-2v-2.08A7 7 0 0 0 19 11h-2z"/>
      </svg>
      <span className="text-white text-xs leading-snug flex-1">
        Tap me! I'm your AI shopping assistant.
      </span>
      <button
        onClick={onDismiss}
        className="text-gray-500 hover:text-white transition-colors ml-1 flex-shrink-0 cursor-pointer"
        aria-label="Dismiss"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </motion.div>
  );
}

// ─── AvatarInner ─────────────────────────────────────────────────────────────

function AvatarInner({
  agentId,
  activeView,
  setActiveView,
  latestProducts,
  setLatestProducts,
  activeIndex,
  setActiveIndex,
  carouselRef,
  handleCarouselScroll,
  dragX,
  dragY,
  dragConstraintsRef,
  saveDragPosition,
}) {
  const [agentSubtitle, setAgentSubtitle] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [highlightPrice, setHighlightPrice] = useState(false);

  const priceTimerRef = useRef(null);
  const subtitleTimerRef = useRef(null);
  const chatContainerRef = useRef(null);
  const isSessionTransitioningRef = useRef(false);
  const latestProductsRef = useRef([]);
  const isSyntheticMessageRef = useRef(false);
  const syncDebounceRef = useRef(null);
  const inactivityRef = useRef({ startAt: 0, lastMeaningfulUserAt: 0 });
  const lastAgentActivityRef = useRef(0);
  const connectedAtRef = useRef(0);
  const hasAgentSpokenRef = useRef(false);
  const isToolPendingRef = useRef(false);
  const muteDelayTimerRef = useRef(null);
  // Task 1: graceful session ending
  const isEndingRef = useRef(false);
  const gracefulEndTimerRef = useRef(null);
  const pendingFarewellEndRef = useRef(null); // set when agent calls end_session, cleared on disconnect
  const farewellFallbackTimerRef = useRef(null); // 5s hard fallback if speech never finishes
  const navigateAfterFarewellRef = useRef(false); // go_to_cart: navigate to /cart once the farewell-end fires
  const pendingFarewellAtRef = useRef(0); // when the farewell was requested — enforce a min speak window
  const farewellSettleTimerRef = useRef(null); // settle-and-recheck timer (TTS chunk gaps flicker isSpeaking)
  // Task 2: drag vs tap discrimination
  const isDraggingRef = useRef(false);
  // VAD sub-states for connected mode: LISTENING | THINKING | AGENT_SPEAKING
  const [vadSubState, setVadSubState] = useState("LISTENING");
  const vadSubStateRef = useRef("LISTENING");
  const thinkingTimerRef = useRef(null);
  const rafVolRef = useRef(null);
  const agentIsSpeakingRef = useRef(false);
  // Nudge — always show on page load; dismissed within the session only
  const [showNudge, setShowNudge] = useState(true);
  const dismissNudge = useCallback(() => { setShowNudge(false); }, []);
  const [cartToast, setCartToast] = useState(null); // null | "adding" | "success" | "error"
  const cartToastTimerRef = useRef(null);
  // Map<productId, qty added this session> — drives the per-product "In cart: N" /
  // "Add N more" wording. The authoritative cart badge (cartCount/cartSubtotalCents)
  // comes from Shopify's own /cart.js, not from this map.
  const [cartedQty, setCartedQty] = useState(() => new Map());
  const [cartCount, setCartCount] = useState(0);
  const [cartSubtotalCents, setCartSubtotalCents] = useState(0);
  // Mirror chatHistory/cartedQty into refs so onDisconnect (captured once inside
  // the useConversation config below) can read the LATEST values instead of
  // whatever was in scope when the callback closed over them.
  const chatHistoryRef = useRef([]);
  useEffect(() => { chatHistoryRef.current = chatHistory; }, [chatHistory]);
  const cartedQtyRef = useRef(new Map());
  useEffect(() => { cartedQtyRef.current = cartedQty; }, [cartedQty]);
  const demoCartCountRef = useRef(0); // simulated cart count on off-store demo/test pages
  const variantCacheRef = useRef(new Map());
  const cartEnabled = window.__TEAM_POP_CART_ENABLED__ !== false;
  // Task 3: session metrics for feedback
  const sessionMetricsRef = useRef({ startAt: null, productsShown: 0, productsClicked: 0, shopNowClicked: false, chatMessages: 0, endReason: null, toolCalls: 0, interruptionCount: 0 });
  const feedbackDismissTimerRef = useRef(null);
  const conversationIdRef = useRef(null);

  const { isSpeaking: agentIsSpeaking } = useConversationMode();

  // Keep track of when the agent is speaking/active
  useEffect(() => {
    if (agentIsSpeaking) {
      lastAgentActivityRef.current = Date.now();
      hasAgentSpokenRef.current = true;
    }
  }, [agentIsSpeaking]);

  // Keep ref in sync for safe access inside rAF callbacks
  useEffect(() => { agentIsSpeakingRef.current = agentIsSpeaking; }, [agentIsSpeaking]);

  /** Reset the inactivity tracker — call on any real user interaction */
  const resetInactivity = useCallback(() => {
    inactivityRef.current.lastMeaningfulUserAt = Date.now();
  }, []);

  // ── Mode (VAD / PTT) ──────────────────────────────────────────────────────
  const [interactionMode, setInteractionMode] = useVoiceMode();

  // ── Latency instrumentation ───────────────────────────────────────────────
  const latencyRef = useRef({ userSpeechAt: null, firstAiAt: null, productsAt: null, cycle: 0 });

  function _startLatencyTimer(userText) {
    const now = performance.now();
    latencyRef.current = { userSpeechAt: now, firstAiAt: null, productsAt: null, cycle: latencyRef.current.cycle + 1 };
    console.log(`%c⏱ [Cycle ${latencyRef.current.cycle}] User spoke: "${userText.slice(0, 50)}"`, "color: #4fc3f7; font-weight: bold");
  }

  function _markFirstAi() {
    const lc = latencyRef.current;
    if (lc.userSpeechAt && !lc.firstAiAt) {
      lc.firstAiAt = performance.now();
      const ms = Math.round(lc.firstAiAt - lc.userSpeechAt);
      console.log(`%c⏱ [Cycle ${lc.cycle}] First AI response: ${ms}ms`, "color: #81c784; font-weight: bold");
      sessionMetricsRef.current.latencyFirstAiMs = ms;
    }
  }

  function _markProductsArrived(count) {
    const lc = latencyRef.current;
    if (lc.userSpeechAt) {
      lc.productsAt = performance.now();
      const totalMs = Math.round(lc.productsAt - lc.userSpeechAt);
      const fromAi = lc.firstAiAt ? Math.round(lc.productsAt - lc.firstAiAt) : "N/A";
      console.log(
        `%c⏱ [Cycle ${lc.cycle}] Products in carousel (${count} items): ${totalMs}ms total | ${fromAi}ms after first AI`,
        "color: #ffb74d; font-weight: bold; font-size: 13px"
      );
      console.log(
        `%c⏱ [Cycle ${lc.cycle}] BREAKDOWN → User→AI: ${lc.firstAiAt ? Math.round(lc.firstAiAt - lc.userSpeechAt) : "?"}ms | User→Products: ${totalMs}ms`,
        "color: #ce93d8; font-weight: bold; font-size: 14px"
      );
      sessionMetricsRef.current.latencyProductsMs = totalMs;
    }
  }

  // Persist a short session summary (recent messages + cart) so a reconnect within
  // SESSION_CONTEXT_TTL_MS can resume instead of starting cold (client ask: survive
  // an accidental close or the agent's own hard/inactivity limit). Reads from refs,
  // not state, so it always sees the latest values regardless of when this closure
  // (captured once by useConversation's onDisconnect) last re-rendered.
  function saveSessionContext() {
    try {
      const recentMessages = chatHistoryRef.current.slice(-10).map((m) => ({ source: m.source, text: m.text }));
      const cartItems = Array.from(cartedQtyRef.current.entries()).map(([productId, qty]) => {
        const product = latestProductsRef.current.find((p) => String(p.id) === String(productId));
        return { productId, qty, name: product?.name || null };
      });
      if (recentMessages.length === 0 && cartItems.length === 0) {
        clearSessionContext();
        return;
      }
      sessionStorage.setItem(SESSION_CONTEXT_STORAGE_KEY, JSON.stringify({
        savedAt: Date.now(),
        messages: recentMessages,
        cartItems,
      }));
      console.log("[session] Saved session context for possible reconnect within 10min.");
    } catch (_e) { /* sessionStorage unavailable — skip persistence */ }
  }

  // ── ElevenLabs conversation ───────────────────────────────────────────────
  const conversation = useConversation({
    onMessage: (message) => {
      const source = message?.source;
      const text =
        typeof message?.message === "string"
          ? message.message
          : typeof message?.text === "string"
            ? message.text
            : typeof message?.content === "string"
              ? message.content
              : "";

      if (source === "user" && isSyntheticMessageRef.current) {
        isSyntheticMessageRef.current = false;
        return;
      }

      if (source === "user" && text) {
        _startLatencyTimer(text);
        if (isMeaningfulUserSpeech(text)) {
          resetInactivity();
          sessionMetricsRef.current.chatMessages += 1;
        } else {
          console.log("[inactivity] Ignoring likely silence transcript:", text);
        }
      }

      if (text) {
        setChatHistory((prev) => {
          const msgId = message?.id || message?.message_id;
          if (msgId) {
            const existingIdx = prev.findIndex((m) => m.id === msgId);
            if (existingIdx !== -1) {
              const updated = [...prev];
              updated[existingIdx] = { ...updated[existingIdx], text };
              return updated;
            }
            return [...prev, { id: msgId, source, text }];
          }
          if (prev.length > 0 && prev[prev.length - 1].text === text) return prev;
          return [...prev, { id: Date.now(), source, text }];
        });
      }

      if (source === "ai") {
        console.log(`[ElevenLabs] AI message received at ${Date.now()} (time since connect: ${connectedAtRef.current ? (Date.now() - connectedAtRef.current) + 'ms' : 'unknown'})`);
        _markFirstAi();
        setAgentSubtitle(text);
        if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
        subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 3000);

        const lower = text.toLowerCase();
        if (
          lower.includes("price") ||
          lower.includes("₹") ||
          lower.includes("rupees") ||
          lower.includes("cost")
        ) {
          if (priceTimerRef.current) clearTimeout(priceTimerRef.current);
          setHighlightPrice(true);
          priceTimerRef.current = setTimeout(() => setHighlightPrice(false), 2500);
        }
      }
    },
    onError: (error) => console.error("ElevenLabs error:", error),
    onDisconnect: (details) => {
      console.log(
        "[ElevenLabs] Disconnected from WebSocket:",
        "reason=", details?.reason,
        "closeCode=", details?.closeCode,
        "closeReason=", details?.closeReason,
        "message=", details?.message,
        "context=", details?.context,
      );
      saveSessionContext();
    },
    onInterruption: (details) => {
      sessionMetricsRef.current.interruptionCount += 1;
      console.log(`[ElevenLabs] onInterruption #${sessionMetricsRef.current.interruptionCount}:`, details);
    },
    onModeChange: (modeObj) => {
      console.log(`[ElevenLabs] onModeChange event at ${Date.now()}:`, modeObj);
    },
    onVadScore: (score) => {
      // @elevenlabs/client ≥1.13 has a native WebRTC input analyser (inputAnalyser +
      // inputVolumeProvider); getInputVolume() works under WebRTC. LISTENING state is
      // now driven by the rAF loop below — this callback is only kept for diagnostics.
      console.log("[ElevenLabs] onVadScore:", score);
    },
    onConversationMetadata: (metadata) => {
      console.log("[ElevenLabs] onConversationMetadata:", metadata);
    },
    onAgentToolRequest: (req) => {
      sessionMetricsRef.current.toolCalls += 1;
      console.log(`[ElevenLabs] tool request #${sessionMetricsRef.current.toolCalls}:`, req?.tool_name ?? req);
    },
    onAgentToolResponse: (res) => {
      console.log("[ElevenLabs] tool response:", res?.tool_name ?? res, "→", res?.response_type ?? "");
    },
  });

  // Destructure mute control. setMuted(true) = mic off, setMuted(false) = mic on.
  const setMuted = conversation.setMuted ?? (() => {});

  // Capture conversation ID once connected (cannot call getId in onConnect due to TDZ)
  useEffect(() => {
    if (conversation.status === "connected") {
      try {
        const cid = conversation.getId?.();
        if (cid) { conversationIdRef.current = cid; console.log("[session] conversation_id:", cid); }
      } catch (_e) {}
    }
  }, [conversation.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── VAD sub-state: LISTENING / THINKING / AGENT_SPEAKING ─────────────────
  // Placed here (after conversation declaration) to avoid TDZ on conversation.status.

  // Immediately switch vadSubState when agent starts/stops speaking
  useEffect(() => {
    if (agentIsSpeaking) {
      if (thinkingTimerRef.current) { clearTimeout(thinkingTimerRef.current); thinkingTimerRef.current = null; }
      vadSubStateRef.current = "AGENT_SPEAKING";
      setVadSubState("AGENT_SPEAKING");
    } else if (conversation.status === "connected") {
      vadSubStateRef.current = "LISTENING";
      setVadSubState("LISTENING");
    }
  }, [agentIsSpeaking, conversation.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Volume-reactive rAF loop: detects user speech (input vol) to distinguish LISTENING vs THINKING
  useEffect(() => {
    if (conversation.status !== "connected") {
      if (rafVolRef.current) { cancelAnimationFrame(rafVolRef.current); rafVolRef.current = null; }
      if (thinkingTimerRef.current) { clearTimeout(thinkingTimerRef.current); thinkingTimerRef.current = null; }
      return;
    }
    const ALPHA = 0.25;
    const INPUT_THRESHOLD = 0.04;
    let smoothedIn = 0;
    const tick = () => {
      rafVolRef.current = requestAnimationFrame(tick);
      if (agentIsSpeakingRef.current) return;
      const rawIn = conversation.getInputVolume?.() ?? 0;
      smoothedIn = smoothedIn * (1 - ALPHA) + rawIn * ALPHA;
      if (smoothedIn > INPUT_THRESHOLD) {
        if (thinkingTimerRef.current) { clearTimeout(thinkingTimerRef.current); thinkingTimerRef.current = null; }
        if (vadSubStateRef.current !== "LISTENING") {
          vadSubStateRef.current = "LISTENING";
          setVadSubState("LISTENING");
        }
      } else if (!thinkingTimerRef.current && vadSubStateRef.current === "LISTENING") {
        thinkingTimerRef.current = setTimeout(() => {
          thinkingTimerRef.current = null;
          if (!agentIsSpeakingRef.current) {
            vadSubStateRef.current = "THINKING";
            setVadSubState("THINKING");
          }
        }, 500);
      }
    };
    rafVolRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafVolRef.current) { cancelAnimationFrame(rafVolRef.current); rafVolRef.current = null; }
      if (thinkingTimerRef.current) { clearTimeout(thinkingTimerRef.current); thinkingTimerRef.current = null; }
    };
  }, [conversation.status, conversation.getInputVolume]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── PTT interaction hook ──────────────────────────────────────────────────
  const ptt = usePttInteraction({ setMuted });

  // Keep PTT status mirror in sync
  useEffect(() => {
    ptt.syncStatus(conversation.status);
  }, [conversation.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Notify PTT hook of lifecycle transitions
  const prevStatusRef = useRef(conversation.status);
  useEffect(() => {
    const prev = prevStatusRef.current;
    const curr = conversation.status;
    prevStatusRef.current = curr;

    if (curr === "connected" && prev !== "connected" && interactionMode === "ptt") {
      ptt.onConnected();
    }
    if ((curr === "disconnected" || curr === "error") && interactionMode === "ptt") {
      ptt.onDisconnected();
    }
  }); // intentionally runs on every render to catch all status transitions

  // Reset inactivity tracking and handle VAD startup mute delay when session connects
  useEffect(() => {
    if (conversation.status === "connected") {
      const now = Date.now();
      inactivityRef.current = { startAt: now, lastMeaningfulUserAt: now };
      connectedAtRef.current = now;
      hasAgentSpokenRef.current = false;

      if (interactionMode === "vad") {
        console.log("[VAD Startup] Connected. Starting muted, setting fallback timer to unmute...");
        setMuted(true);

        if (muteDelayTimerRef.current) clearTimeout(muteDelayTimerRef.current);
        muteDelayTimerRef.current = setTimeout(() => {
          console.log("[VAD Startup] Fallback timeout reached (2.5s). Unmuting mic...");
          setMuted(false);
          muteDelayTimerRef.current = null;
        }, 2500);
      } else {
        setMuted(true);
      }
    } else if (conversation.status === "disconnected" || conversation.status === "error") {
      if (muteDelayTimerRef.current) {
        clearTimeout(muteDelayTimerRef.current);
        muteDelayTimerRef.current = null;
      }
    }
  }, [conversation.status, interactionMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Unmute VAD early if the agent starts speaking before fallback timeout
  useEffect(() => {
    if (agentIsSpeaking && interactionMode === "vad" && conversation.status === "connected") {
      hasAgentSpokenRef.current = true;
      if (muteDelayTimerRef.current) {
        console.log("[VAD Startup] Agent started speaking. Clearing fallback timer and unmuting mic...");
        clearTimeout(muteDelayTimerRef.current);
        muteDelayTimerRef.current = null;
        setMuted(false);
      }
    }
  }, [agentIsSpeaking, interactionMode, conversation.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // Handle manual interaction mode toggles mid-conversation
  useEffect(() => {
    if (conversation.status === "connected") {
      if (interactionMode === "ptt") {
        if (muteDelayTimerRef.current) {
          clearTimeout(muteDelayTimerRef.current);
          muteDelayTimerRef.current = null;
        }
        setMuted(true);
      } else if (interactionMode === "vad") {
        // If we switch to VAD mid-conversation and agent has already spoken or we are past connection delay, unmute
        const isPastInitialConnection = (Date.now() - connectedAtRef.current) > 2500;
        if (hasAgentSpokenRef.current || isPastInitialConnection) {
          setMuted(false);
        }
      }
    }
  }, [interactionMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Derived visual state ──────────────────────────────────────────────────
  const visualState = getVisualState({
    status: conversation.status,
    interactionMode,
    isPressActive: ptt.isPressActiveRef.current,
    vadSubState,
  });

  // ── Tool: update_products ─────────────────────────────────────────────────
  useConversationClientTool("update_products", (parameters) => {
    isToolPendingRef.current = true;
    console.log("Update tool called : ", parameters);
    const products = Array.isArray(parameters?.products) ? parameters.products : [];

    _markProductsArrived(products.length);
    sessionMetricsRef.current.productsShown += products.length;

    setLatestProducts(products);
    latestProductsRef.current = products;
    setActiveView("PRODUCTS");
    setActiveIndex(0);
    setAgentSubtitle(`Found ${products.length} products for you`);
    if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
    subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 3000);
    isToolPendingRef.current = false;
    return "UI updated successfully";
  });

  useConversationClientTool("update_carousel_main_view", (parameters) => {
    isToolPendingRef.current = true;
    // Coerce string→number (some LLMs emit "2" instead of 2), then clamp to valid range.
    const raw = parameters?.index;
    const index = typeof raw === "string" ? parseInt(raw, 10) : raw;
    const len = latestProductsRef.current.length;
    const safeIdx = Number.isFinite(index) && len > 0 ? Math.max(0, Math.min(index, len - 1)) : 0;
    if (Number.isFinite(index) && len > 0) {
      setActiveIndex(safeIdx);
    }
    isToolPendingRef.current = false;
    // Return JSON so the agent can extract product_id reliably for get_similar_products.
    const focused = latestProductsRef.current[safeIdx];
    return focused ? JSON.stringify({ product_name: focused.name, product_id: String(focused.id) }) : "ok";
  });

  const { sendUserMessage } = conversation;

  // Refresh the cart badge from Shopify's own cart (source of truth — also picks up
  // items added before the widget opened, or via the product page's own Add to Cart).
  // On demo/test pages /cart.js doesn't exist, so mirror the locally-simulated count.
  // Declared here (before startVoiceSession) so it's initialized by the time
  // startVoiceSession's body/deps reference it — a TDZ crash when it lived below.
  const refreshCartState = useCallback(async () => {
    if (window.__TEAM_POP_DEMO__) {
      setCartCount(demoCartCountRef.current);
      return null;
    }
    try {
      const r = await fetch('/cart.js');
      if (!r.ok) return null;
      const data = await r.json();
      setCartCount(data.item_count ?? 0);
      setCartSubtotalCents(data.total_price ?? 0);
      return data;
    } catch (_e) { return null; /* ignore — cart bar just stays hidden/stale */ }
  }, []);

  // ── VAD session helpers ───────────────────────────────────────────────────
  const startVoiceSession = useCallback(() => {
    setAgentSubtitle("");
    setHighlightPrice(false);
    // Open the full panel immediately so the connecting state is unmissable
    // (client feedback 2026-07-15: the small pill was too easy to overlook).
    // The panel's empty-state area renders the connecting/listening screen
    // until the first update_products call fills it with the carousel.
    setActiveView("PRODUCTS");
    refreshCartState(); // pick up any pre-existing cart contents (e.g. added before opening the widget)
    variantCacheRef.current.clear();

    // Reconnect-within-10min: restore chat + cart-badge state and hand the agent a
    // short recap via dynamicVariables (see "# Session Continuity" in PROMPT_CLAUDE).
    // Consumed once so a later, unrelated session doesn't inherit stale context.
    const saved = loadSessionContext();
    let sessionContextText = "";
    if (saved) {
      console.log("[session] Restoring session context from a reconnect within 10min.");
      setChatHistory((saved.messages || []).map((m, i) => ({ id: `restored-${i}`, source: m.source, text: m.text })));
      setCartedQty(new Map((saved.cartItems || []).map((ci) => [String(ci.productId), ci.qty])));
      const cartSummary = saved.cartItems?.length
        ? saved.cartItems.map((ci) => `${ci.qty}x ${ci.name || "an item"}`).join(", ")
        : "nothing yet";
      const recentTurns = (saved.messages || []).slice(-4).map((m) => `${m.source}: ${m.text}`).join(" | ");
      sessionContextText = `Shopper reconnected after a brief disconnect. Cart so far: ${cartSummary}. Recent conversation: ${recentTurns}`;
      clearSessionContext();
    } else {
      setChatHistory([]);
      setCartedQty(new Map());
    }

    const now = Date.now();
    inactivityRef.current = { startAt: now, lastMeaningfulUserAt: now };
    sessionMetricsRef.current = { startAt: now, productsShown: 0, productsClicked: 0, shopNowClicked: false, chatMessages: 0, endReason: null, conversationId: null, latencyFirstAiMs: null, latencyProductsMs: null, toolCalls: 0, interruptionCount: 0 };
    // Transport is set once via CONNECTION_TYPE (see the constant near the top of the
    // file for the websocket-vs-webrtc audio-quality trade-offs). Currently "websocket"
    // for cleanest agent audio (raw PCM, no Opus/PLC artifacts) — the old first_message
    // drop bug that forced WebRTC is fixed in @elevenlabs/client ≥1.13.
    conversation.startSession({
      agentId,
      connectionType: CONNECTION_TYPE,
      dynamicVariables: { session_context: sessionContextText },
    });
  }, [conversation, agentId, refreshCartState, setActiveView]);

  const endVoiceSession = useCallback(() => {
    console.log("[session] endVoiceSession called manually by user.");
    setActiveView("NONE");
    conversation.endSession();
  }, [conversation, setActiveView]);

  const endSessionAndCollapse = useCallback((reason) => {
    console.log(`[session] endSessionAndCollapse called. Reason: "${reason}"`);
    // Clear any pending graceful-end timer and reset guard
    if (gracefulEndTimerRef.current) { clearTimeout(gracefulEndTimerRef.current); gracefulEndTimerRef.current = null; }
    isEndingRef.current = false;
    if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
    if (priceTimerRef.current) clearTimeout(priceTimerRef.current);
    setAgentSubtitle("");
    setHighlightPrice(false);
    sessionMetricsRef.current.endReason = reason;
    conversation.endSession();

    // Show feedback card only for sessions longer than 10 seconds
    const duration = sessionMetricsRef.current.startAt
      ? Math.round((Date.now() - sessionMetricsRef.current.startAt) / 1000)
      : 0;
    if (duration >= 10) {
      setActiveView("FEEDBACK");
      // 12s (was 8s) — client feedback 2026-07-15: feedback disappeared too fast to notice
      feedbackDismissTimerRef.current = setTimeout(() => {
        setActiveView((prev) => prev === "FEEDBACK" ? "NONE" : prev);
      }, 12000);
    } else {
      setActiveView("NONE");
    }
  }, [conversation, setActiveView]);

  // Navigate to the Shopify cart page — NOT /checkout. The cart page hosts both
  // native checkout AND the merchant's Shiprocket express (UPI/GPay/PhonePe) button;
  // going straight to /checkout would bypass Shiprocket entirely. Defined here (above
  // the farewell watcher) so the watcher can call it without a TDZ crash.
  const goToCart = useCallback(() => {
    console.log("[cart] goToCart() firing — navigating to /cart now.");
    if (window.__TEAM_POP_DEMO__) {
      console.log("[cart] Demo mode — would navigate to /cart here.");
      return;
    }
    window.location.href = '/cart';
  }, []);

  // ── Watch agentIsSpeaking to fire farewell-end after speech finishes ─────────
  // Placed here so endSessionAndCollapse is already in scope (avoids TDZ crash).
  // Handles both end_session and go_to_cart: once the agent's closing line finishes,
  // tear the session down, then (for go_to_cart) navigate to the cart page.
  //
  // Settle-and-recheck: isSpeaking flickers false in TTS chunk gaps, and the tool
  // call often lands BEFORE the closing line's audio starts. Ending on the first
  // falling edge cut the goodbye mid-word (live transcripts showed "taking you to
  // your..." marked interrupted). So on each falling edge we wait 900ms, then only
  // end if (a) speech hasn't resumed and (b) ≥2.2s have passed since the tool call
  // (a not-yet-started closing line gets time to begin; once it begins, resumed
  // speech aborts the attempt and the NEXT falling edge retries).
  useEffect(() => {
    if (!agentIsSpeaking && pendingFarewellEndRef.current) {
      const attempt = () => {
        farewellSettleTimerRef.current = null;
        if (!pendingFarewellEndRef.current) return; // already ended elsewhere
        if (agentIsSpeakingRef.current) return; // speech (re)started — next falling edge retries
        const sinceRequest = Date.now() - (pendingFarewellAtRef.current || 0);
        if (sinceRequest < 2200) {
          farewellSettleTimerRef.current = setTimeout(attempt, 2200 - sinceRequest + 200);
          return;
        }
        const reason = pendingFarewellEndRef.current;
        pendingFarewellEndRef.current = null;
        if (farewellFallbackTimerRef.current) { clearTimeout(farewellFallbackTimerRef.current); farewellFallbackTimerRef.current = null; }
        const navAfter = navigateAfterFarewellRef.current;
        navigateAfterFarewellRef.current = false;
        endSessionAndCollapse(reason);
        if (navAfter) goToCart();
      };
      if (farewellSettleTimerRef.current) clearTimeout(farewellSettleTimerRef.current);
      farewellSettleTimerRef.current = setTimeout(attempt, 900);
    }
  }, [agentIsSpeaking, endSessionAndCollapse, goToCart]);

  // ── Tool: end_session (Task 1 — agent-initiated farewell) ────────────────────
  // Wait for agentIsSpeaking → false (watched in useEffect below), then disconnect.
  // A 5s hard fallback fires if speech never finishes cleanly.
  useConversationClientTool("end_session", (parameters) => {
    const reason = `agent_farewell: ${parameters?.reason || "goodbye"}`;
    console.log("[session] Agent called end_session:", reason);
    // Cancel any pending graceful-end timer so it doesn't race
    if (gracefulEndTimerRef.current) { clearTimeout(gracefulEndTimerRef.current); gracefulEndTimerRef.current = null; }
    pendingFarewellEndRef.current = reason;
    pendingFarewellAtRef.current = Date.now();
    // Hard fallback: disconnect after 6s even if speech event never fires
    if (farewellFallbackTimerRef.current) clearTimeout(farewellFallbackTimerRef.current);
    farewellFallbackTimerRef.current = setTimeout(() => {
      farewellFallbackTimerRef.current = null;
      if (pendingFarewellEndRef.current) {
        console.log("[session] Farewell fallback timer fired — ending now");
        pendingFarewellEndRef.current = null;
        endSessionAndCollapse(reason);
      }
    }, 6000);
    return "session_ending";
  });

  // Fetch variants on-demand from /product-details; results are cached per product.
  const fetchVariants = useCallback(async (productId) => {
    if (variantCacheRef.current.has(String(productId))) return variantCacheRef.current.get(String(productId));
    const storeId = window.__TEAM_POP_STORE_ID__;
    const apiBase = window.__TEAM_POP_API_URL__ || "";
    if (!storeId) return [];
    try {
      const r = await fetch(`${apiBase}/product-details`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ store_id: storeId, product_id: String(productId) }),
      });
      const data = r.ok ? await r.json() : {};
      const variants = data.variants || [];
      variantCacheRef.current.set(String(productId), variants);
      return variants;
    } catch { return []; }
  }, []);

  // Load the shopper's existing cart on widget mount (before any voice session starts) —
  // covers the case where they already added items via the store's own UI (case 9).
  useEffect(() => { refreshCartState(); }, [refreshCartState]);

  // Shared add-to-cart logic used by both the voice tool and the manual button.
  const performAddToCart = useCallback(async (product, variantIndex = 0, quantity = 1) => {
    if (!cartEnabled) {
      return "This store uses Shop Now — open the product link to purchase.";
    }
    const qty = Math.max(1, Number(quantity) || 1);
    // On demo pages simulate success immediately — /cart/add.js doesn't exist here
    // and variant fetch would hit the wrong origin, so skip both.
    if (window.__TEAM_POP_DEMO__) {
      setCartToast("success");
      if (cartToastTimerRef.current) clearTimeout(cartToastTimerRef.current);
      cartToastTimerRef.current = setTimeout(() => setCartToast(null), 3000);
      setCartedQty(prev => { const n = new Map(prev); n.set(String(product.id), (n.get(String(product.id)) || 0) + qty); return n; });
      demoCartCountRef.current += qty;
      refreshCartState();
      return `Added ${qty > 1 ? `${qty} ` : ""}${product.name} to cart!`;
    }
    // Real store: fetch variant ID on demand (variants not included in search results).
    const localVariants = product.metadata?.variants || product.variants || [];
    const variants = localVariants.length > 0 ? localVariants : await fetchVariants(product.id);
    const variant = variants[variantIndex] || variants[0];
    if (!variant?.id) {
      return "No variant available for this product. Please use the Shop Now link instead.";
    }
    try {
      const r = await fetch('/cart/add.js', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: variant.id, quantity: qty }),
      });
      if (!r.ok) throw new Error(await r.text());
      await r.json();
      setCartToast("success");
      if (cartToastTimerRef.current) clearTimeout(cartToastTimerRef.current);
      cartToastTimerRef.current = setTimeout(() => setCartToast(null), 3000);
      setCartedQty(prev => { const n = new Map(prev); n.set(String(product.id), (n.get(String(product.id)) || 0) + qty); return n; });
      const freshCart = await refreshCartState(); // pick up the real Shopify-side count/subtotal
      syncThemeCartBadge(freshCart);
      return `Added ${qty > 1 ? `${qty} ` : ""}${product.name} to cart!`;
    } catch (err) {
      console.warn("[cart] /cart/add.js failed:", err);
      setCartToast("error");
      if (cartToastTimerRef.current) clearTimeout(cartToastTimerRef.current);
      cartToastTimerRef.current = setTimeout(() => setCartToast(null), 3000);
      return `Could not add to cart. Please try the Shop Now link instead.`;
    }
  }, [cartEnabled, fetchVariants, refreshCartState]);

  useConversationClientTool("add_to_cart", (parameters) => {
    if (!cartEnabled) return Promise.resolve("This store uses Shop Now — open the product link to purchase.");
    const { product_id, variant_index = 0, quantity = 1 } = parameters || {};
    const product = latestProductsRef.current.find(p => String(p.id) === String(product_id));
    if (!product) return Promise.resolve("Product not found in current view");
    return performAddToCart(product, variant_index, quantity);
  });

  // Voice-driven cart navigation — routes to /cart (not /checkout) so both native
  // checkout and the merchant's Shiprocket express option stay available. Going to the
  // cart means the shopper is done browsing by voice, so this ENDS the session (after
  // the agent's closing line finishes speaking, watched via agentIsSpeaking) and THEN
  // navigates. On a real store the navigation itself also tears the session down;
  // ending it explicitly is what makes the demo page (nav disabled) close the orb too
  // instead of leaving the mic open — the bug this fixes.
  useConversationClientTool("go_to_cart", () => {
    console.log("[session] Agent called go_to_cart.");
    if (!cartEnabled) return Promise.resolve("This store uses Shop Now — there's no cart to show.");
    navigateAfterFarewellRef.current = true;
    pendingFarewellEndRef.current = "go_to_cart";
    pendingFarewellAtRef.current = Date.now();
    if (farewellFallbackTimerRef.current) clearTimeout(farewellFallbackTimerRef.current);
    // Hard fallback: if the speech-end event never fires, end + navigate after 6s.
    farewellFallbackTimerRef.current = setTimeout(() => {
      farewellFallbackTimerRef.current = null;
      if (pendingFarewellEndRef.current) {
        console.log("[session] go_to_cart fallback timer fired — ending + navigating now");
        pendingFarewellEndRef.current = null;
        const navAfter = navigateAfterFarewellRef.current;
        navigateAfterFarewellRef.current = false;
        endSessionAndCollapse("go_to_cart");
        if (navAfter) goToCart();
      }
    }, 6000);
    return Promise.resolve(
      window.__TEAM_POP_DEMO__
        ? "Opening your cart now — on the live store this takes you to checkout. (Demo: navigation is disabled here.)"
        : "Taking you to your cart now."
    );
  });

  // ── Graceful session end (Task 1 — for timeouts) ─────────────────────────────
  // Sends [SESSION ENDING] so the agent can speak a farewell, then force-ends after 4s.
  const gracefulEndSession = useCallback((reason) => {
    if (isEndingRef.current) return;
    isEndingRef.current = true;
    console.log(`[session] gracefulEndSession called. Reason: "${reason}"`);
    if (conversation.status !== "connected") {
      endSessionAndCollapse(reason);
      return;
    }
    isSyntheticMessageRef.current = true;
    sendUserMessage("[SESSION ENDING]");
    gracefulEndTimerRef.current = setTimeout(() => {
      gracefulEndTimerRef.current = null;
      endSessionAndCollapse(reason);
    }, 4000);
  }, [conversation.status, endSessionAndCollapse, sendUserMessage]);

  // ── Feedback submission (Task 3) ──────────────────────────────────────────────
  const submitFeedback = useCallback((rating, tag) => {
    if (feedbackDismissTimerRef.current) { clearTimeout(feedbackDismissTimerRef.current); feedbackDismissTimerRef.current = null; }
    // Safety net: try to capture conversation id if the connect-time useEffect missed it.
    if (!conversationIdRef.current) {
      try { conversationIdRef.current = conversation.getId?.() ?? null; } catch (_e) {}
    }
    const m = sessionMetricsRef.current;
    const duration = m.startAt ? Math.round((Date.now() - m.startAt) / 1000) : null;

    // ElevenLabs built-in feedback signal (positive/negative boolean)
    if (rating === "positive" || rating === "negative") {
      try { conversation.sendFeedback(rating === "positive"); } catch (_e) { /* not all SDK versions support this */ }
    }

    // Send to our backend (fire-and-forget, never blocks UX)
    const apiBase = window.__TEAM_POP_API_URL__ || "";
    fetch(`${apiBase}/api/session-feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_id: agentId,
        duration_seconds: duration,
        rating: rating || "none",
        feedback_tag: tag || null,
        products_shown: m.productsShown,
        products_clicked: m.productsClicked,
        shop_now_clicked: m.shopNowClicked,
        chat_messages: m.chatMessages,
        end_reason: m.endReason,
        conversation_id: conversationIdRef.current,
        latency_first_ai_ms: m.latencyFirstAiMs ?? null,
        latency_products_ms: m.latencyProductsMs ?? null,
        tool_calls: m.toolCalls ?? 0,
        interruption_count: m.interruptionCount ?? 0,
      }),
    }).catch((e) => console.warn("[feedback] Submission failed (non-blocking):", e));

    setActiveView("NONE");
  }, [agentId, conversation, setActiveView]);

  /** VAD-mode tap: toggle session on/off */
  const handleOrbActivate = useCallback(() => {
    if (isSessionTransitioningRef.current) return;
    if (isDraggingRef.current) return; // Task 2: don't activate if a drag just finished
    if (conversation.status === "connecting") return;
    if (showNudge) dismissNudge();
    resetInactivity();
    isSessionTransitioningRef.current = true;
    if (conversation.status === "connected") {
      endSessionAndCollapse("Ending session from orb tap.");
    } else if (conversation.status === "disconnected" || conversation.status === "error") {
      startVoiceSession();
    }
    setTimeout(() => { isSessionTransitioningRef.current = false; }, 500);
  }, [conversation.status, startVoiceSession, endSessionAndCollapse, resetInactivity, showNudge, dismissNudge]);

  /** PTT pointer/keyboard handlers — forwarded to the orb */
  const handlePttPointerDown = useCallback(
    (e) => {
      resetInactivity();
      ptt.beginPress(e, { agentId, startSession: conversation.startSession });
    },
    [ptt, agentId, conversation.startSession, resetInactivity]
  );

  const handleOrbKeyDown = useCallback(
    (e) => {
      if (interactionMode === "ptt") {
        resetInactivity();
        ptt.handleKeyDown(e, { agentId, startSession: conversation.startSession });
      } else if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        handleOrbActivate();
      }
    },
    [interactionMode, ptt, agentId, conversation.startSession, handleOrbActivate, resetInactivity]
  );

  // ── Carousel sync ─────────────────────────────────────────────────────────
  const safeIndex = Math.min(activeIndex, Math.max(0, latestProducts.length - 1));

  // DISABLED: syncMainProduct previously sent a [CAROUSEL UPDATE] message to the
  // voice agent when the user clicked a thumbnail, prompting the agent to narrate
  // the selected product. Disabled per product decision — clicking a thumbnail
  // should only update the carousel visually, not trigger agent speech.
  // To re-enable: uncomment syncMainProduct(latestProducts[idx]) in the onClick below.
  // eslint-disable-next-line no-unused-vars
  const syncMainProduct = useCallback(
    (product) => {
      if (!product?.id) return;
      resetInactivity(); // carousel interaction = real user activity
      if (conversation.status !== "connected") {
        setAgentSubtitle(
          `${product.name} — ₹${Number(product.price).toLocaleString("en-IN")}`,
        );
        if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
        subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 4000);
        return;
      }

      if (syncDebounceRef.current) clearTimeout(syncDebounceRef.current);
      syncDebounceRef.current = setTimeout(() => {
        console.log("[sync] Sending product context to agent:", product.name);
        isSyntheticMessageRef.current = true;
        sendUserMessage(
          `[CAROUSEL UPDATE] (The user manually selected product: "${product.name}", Price: ₹${Number(product.price).toLocaleString("en-IN")}). Tell me about this one.`
        );
      }, 600);
    },
    [conversation.status, sendUserMessage, resetInactivity],
  );

  useEffect(() => {
    const carouselEl = carouselRef.current;
    if (!carouselEl || !latestProducts[safeIndex]) return;
    console.log(`[Index Changed] safeIndex = ${safeIndex}`);
    const thumbnailEl = carouselEl.children[safeIndex];
    if (thumbnailEl) {
      thumbnailEl.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
    }
  }, [latestProducts, safeIndex, carouselRef]);

  useEffect(() => {
    const activeProduct = latestProducts[safeIndex];
    if (!activeProduct || activeView !== "PRODUCTS") return;
    const label = `${activeProduct.name} — ₹${Number(activeProduct.price || 0).toLocaleString("en-IN")}`;
    setTimeout(() => setAgentSubtitle(label), 0);
    if (subtitleTimerRef.current) clearTimeout(subtitleTimerRef.current);
    subtitleTimerRef.current = setTimeout(() => setAgentSubtitle(""), 4000);
  }, [activeView, latestProducts, safeIndex]);

  useEffect(() => {
    return () => {
      clearTimeout(priceTimerRef.current);
      clearTimeout(subtitleTimerRef.current);
      clearTimeout(syncDebounceRef.current);
      if (muteDelayTimerRef.current) clearTimeout(muteDelayTimerRef.current);
      if (farewellFallbackTimerRef.current) clearTimeout(farewellFallbackTimerRef.current);
      if (farewellSettleTimerRef.current) clearTimeout(farewellSettleTimerRef.current);
      if (feedbackDismissTimerRef.current) clearTimeout(feedbackDismissTimerRef.current);
      if (rafVolRef.current) cancelAnimationFrame(rafVolRef.current);
      if (thinkingTimerRef.current) clearTimeout(thinkingTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [chatHistory]);

  useEffect(() => {
    latestProductsRef.current = latestProducts;
  }, [latestProducts]);

  // ── Smart Inactivity & Hard Limit ──────────────────────────────────────────
  useEffect(() => {
    if (conversation.status !== "connected") return;
    const id = setInterval(() => {
      const r = inactivityRef.current;
      const now = Date.now();

      // 1. Hard session limit (420s / 7 min)
      if (now - r.startAt > SESSION_HARD_LIMIT_MS) {
        console.log("[session] Ending session due to 7-min hard limit.");
        gracefulEndSession("Ending session due to 7-min hard limit.");
        return;
      }

      // 2. Ignore/reset inactivity conditions
      if (document.hidden) {
        // Tab/app is backgrounded — the shopper CAN'T speak (mobile OSes suspend
        // the mic), so don't punish them with the 30s inactivity cutoff. The
        // 7-min hard limit above still caps runaway sessions.
        r.lastMeaningfulUserAt = now;
        return;
      }
      if (agentIsSpeaking) {
        // Reset/push forward inactivity while agent is speaking
        r.lastMeaningfulUserAt = now;
        return;
      }

      const isNewlyConnected = (now - connectedAtRef.current) < 20000;
      const hasAgentSpoken = hasAgentSpokenRef.current;
      if (isNewlyConnected && !hasAgentSpoken) {
        // Give time for connection and first greeting to start
        return;
      }

      const isGraceWindow = (now - lastAgentActivityRef.current) < 10000;
      if (isGraceWindow) {
        // Do not end session during post-speech grace window
        return;
      }

      if (isToolPendingRef.current) {
        // Do not end session if a client tool is actively executing
        return;
      }

      // 3. User inactivity limit (30s)
      if (now - r.lastMeaningfulUserAt >= USER_INACTIVITY_TIMEOUT_MS) {
        console.log(
          `[session] Ending session due to user inactivity. ` +
          `now=${now}, lastUserSpeech=${r.lastMeaningfulUserAt} (${now - r.lastMeaningfulUserAt}ms ago), ` +
          `lastAgentActivity=${lastAgentActivityRef.current} (${now - lastAgentActivityRef.current}ms ago)`
        );
        gracefulEndSession("Ending session: no meaningful user speech for 30s.");
      }
    }, 3000);
    return () => clearInterval(id);
  }, [conversation.status, agentIsSpeaking, gracefulEndSession]);

  // ── Background-tab handling ────────────────────────────────────────────────
  // Mobile OSes suspend microphone capture when the browser app goes to
  // background (shopper switches to WhatsApp etc.) while audio OUTPUT keeps
  // playing — so the agent talks but can't hear. That's an OS privacy policy no
  // web widget can bypass. Mitigation: tell the agent to stop re-prompting into
  // the void, and to greet the shopper naturally when they come back.
  useEffect(() => {
    const onVisibility = () => {
      if (conversation.status !== "connected") return;
      try {
        if (document.hidden) {
          console.log("[visibility] Tab hidden — telling agent to pause prompting.");
          conversation.sendContextualUpdate?.(
            "[system] The shopper switched away from this tab/app. They may still hear you but their microphone is unavailable, so they cannot reply by voice. Finish your current sentence, then stay quiet and wait — do NOT keep prompting or repeating yourself.",
          );
        } else {
          console.log("[visibility] Tab visible again — telling agent the shopper is back.");
          conversation.sendContextualUpdate?.(
            "[system] The shopper is back on this tab and can talk again. If you were waiting on them, briefly and warmly pick the conversation back up (one short line) — don't mention tabs or apps.",
          );
        }
      } catch (e) {
        console.warn("[visibility] Contextual update failed:", e);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [conversation]);

  const isConnected = conversation.status === "connected";

  // ── Shared dock props ─────────────────────────────────────────────────────
  const sharedDockProps = {
    visualState,
    interactionMode,
    setMode: setInteractionMode,
    isConnected,
    onOrbClick: handleOrbActivate,
    onPointerDown: handlePttPointerDown,
    onPointerUp: ptt.endPress,
    onPointerCancel: ptt.endPress,
    onKeyDown: handleOrbKeyDown,
    onKeyUp: ptt.handleKeyUp,
    onEndSession: endVoiceSession,
    onRightAction: activeView === "PRODUCTS"
      ? () => setActiveView("CHAT")
      : activeView === "CHAT" && latestProducts.length > 0
        ? () => setActiveView("PRODUCTS")
        : latestProducts.length > 0
          ? () => setActiveView("PRODUCTS")
          : () => setActiveView("CHAT"),
    rightLabel: activeView === "PRODUCTS"
      ? "Chat"
      : activeView === "CHAT" && latestProducts.length > 0
        ? "← Products"
        : latestProducts.length > 0
          ? "← Products"
          : "Chat",
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <AnimatePresence>
      {/* ── Products overlay view ──────────────────────────────────────────── */}
      {activeView === "PRODUCTS" && (
        <motion.div
          key="products"
          initial={{ opacity: 0, scale: 0.92, y: 24 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 16 }}
          style={{ transformOrigin: "bottom right", left: "auto" }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="shopping-panel flex flex-col bg-black overflow-hidden shadow-2xl pointer-events-auto"
        >
          <div className="flex-none p-4 flex justify-end items-start absolute top-0 w-full z-50 pointer-events-none">
            <button
              className="bg-black/40 hover:bg-black/60 backdrop-blur-md text-white rounded-full w-10 h-10 flex items-center justify-center text-xl shadow-lg transition-all pointer-events-auto"
              onClick={() => setActiveView("NONE")}
            >
              &times;
            </button>
          </div>

          {/* Cart feedback toast */}
          {cartToast && (
            <div
              style={{ position: "absolute", top: "12px", left: "50%", transform: "translateX(-50%)", zIndex: 10 }}
              className={`px-4 py-2 rounded-full text-sm font-semibold text-white shadow-lg ${
                cartToast === "success" ? "bg-green-500" :
                cartToast === "error" ? "bg-red-500" :
                "bg-blue-500"
              }`}
            >
              {cartToast === "success" ? "Added to cart!" :
               cartToast === "error" ? "Couldn't add to cart" :
               "Adding..."}
            </div>
          )}

          {/* Cart bar — appears once the cart is non-empty. Routes to /cart, never
              /checkout, so the merchant's Shiprocket express option stays reachable. */}
          {cartEnabled && cartCount > 0 && (
            <div className="flex-none flex items-center justify-between gap-2 px-4 pt-14 pb-2 bg-black relative z-20">
              <span className="text-white text-xs font-semibold">
                🛒 {cartCount} item{cartCount !== 1 ? "s" : ""}
                {cartSubtotalCents > 0 ? ` · ₹${(cartSubtotalCents / 100).toLocaleString("en-IN")}` : ""}
              </span>
              <button
                onClick={() => {
                  sessionMetricsRef.current.shopNowClicked = true;
                  // Tapping through to the cart ends the voice session too, so the
                  // orb doesn't keep listening after the shopper has moved on.
                  if (conversation.status === "connected") endSessionAndCollapse("go_to_cart_button");
                  goToCart();
                }}
                className="text-xs font-bold text-black bg-white px-3 py-1.5 rounded-full hover:bg-gray-200 transition flex-shrink-0"
              >
                Go to Cart
              </button>
            </div>
          )}

          {latestProducts.length > 0 ? (
            <>
              {/* Image — top 48%, object-contain so full product is visible */}
              <div className="w-full bg-zinc-950 overflow-hidden flex-shrink-0" style={{ height: "48%" }}>
                {latestProducts[safeIndex] && (
                  <img
                    src={latestProducts[safeIndex].local_image_url || latestProducts[safeIndex].image_url || DUMMY_IMAGE}
                    alt={latestProducts[safeIndex].name}
                    className="w-full h-full object-contain"
                    onError={(e) => {
                      const p = latestProducts[safeIndex];
                      if (p && e.target.src !== p.image_url && p.image_url) {
                        e.target.src = p.image_url;
                      } else {
                        e.target.src = "https://placehold.co/400x400?text=No+Image";
                      }
                    }}
                  />
                )}
              </div>

              {/* Details — scrollable bottom section */}
              <div className="flex-1 w-full overflow-y-auto bg-black px-4 pt-3 pb-2 min-h-0 pointer-events-auto">
                {latestProducts[safeIndex] && (
                  <ProductDetails
                    key={latestProducts[safeIndex]?.id}
                    product={latestProducts[safeIndex]}
                    highlightPrice={highlightPrice}
                    cartedCount={cartedQty.get(String(latestProducts[safeIndex]?.id)) || 0}
                    onShopNow={() => { sessionMetricsRef.current.shopNowClicked = true; }}
                    onAddToCart={cartEnabled ? (product, qty) => {
                      setCartToast("adding");
                      performAddToCart(product, 0, qty);
                    } : undefined}
                  />
                )}
                {/* Thumbnails */}
                <div
                  className="w-full flex items-center overflow-x-auto hide-scrollbar gap-3 mt-3 pb-1"
                  ref={carouselRef}
                  onScroll={handleCarouselScroll}
                >
                  {latestProducts.map((p, idx) => (
                    <div
                      key={p.id || idx}
                      className={`flex-shrink-0 transition-all duration-300 cursor-pointer rounded-xl overflow-hidden border-2 ${
                        idx === safeIndex
                          ? "border-blue-500 scale-100 opacity-100"
                          : "border-transparent scale-90 opacity-60 hover:opacity-100"
                      }`}
                      style={{ width: "60px", height: "60px" }}
                      onClick={() => {
                        console.log(`[Thumbnail] Click → index ${idx} (${latestProducts[idx]?.name || "unknown"})`);
                        setActiveIndex(idx);
                        sessionMetricsRef.current.productsClicked += 1;
                      }}
                    >
                      <img
                        src={p.local_image_url || p.image_url || DUMMY_IMAGE}
                        alt={p.name}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          if (p && e.target.src !== p.image_url && p.image_url) {
                            e.target.src = p.image_url;
                          } else {
                            e.target.src = "https://placehold.co/400x400?text=No+Image";
                          }
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </>
          ) : visualState === "CONNECTING" || isConnected ? (
            <PanelSessionScreen visualState={visualState} />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-zinc-900 pointer-events-auto pt-16">
              <div className="w-20 h-20 bg-zinc-800 rounded-full flex items-center justify-center mb-6 border border-zinc-700 shadow-xl">
                <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-white mb-3 tracking-wide">No Products Yet</h2>
              <p className="text-gray-400 text-sm max-w-[250px] mx-auto leading-relaxed">
                Tap the orb below and ask me to find something for you!
              </p>
            </div>
          )}

          {/* Products overlay dock */}
          <div className="flex-none w-full bg-black pb-6 px-4 z-10 pointer-events-auto">
            <div className="w-full flex items-center justify-center mt-2">
              <OrbDock
                {...sharedDockProps}
                scale="scale-75"
                style={{
                  position: "relative",
                  width: "100%",
                  margin: "0",
                  height: "50px",
                  boxShadow: "none",
                  background: "transparent",
                  border: "none",
                  padding: "0",
                }}
              />
            </div>
          </div>
        </motion.div>
      )}

      {/* ── Closed dock view (default) ────────────────────────────────────── */}
      {activeView === "NONE" && (
        <>
          <motion.div
            key="none"
            drag
            dragMomentum={false}
            dragConstraints={dragConstraintsRef}
            dragElastic={0.08}
            style={{ x: dragX, y: dragY, position: 'fixed', bottom: '20px', right: '20px', left: 'auto', width: 'auto' }}
            onDragStart={() => { isDraggingRef.current = true; }}
            onDragEnd={() => { saveDragPosition(dragX.get(), dragY.get()); setTimeout(() => { isDraggingRef.current = false; }, 100); }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="avatar-widget mode-closed"
          >
            <div className="avatar-controls-column">
              <OrbDock
                {...sharedDockProps}
                inactive={conversation.status === "disconnected"}
                style={{ paddingLeft: conversation.status === "disconnected" ? 0 : "16px", paddingRight: conversation.status === "disconnected" ? 0 : "16px", minWidth: conversation.status === "disconnected" ? "80px" : "280px" }}
              />
            </div>
          </motion.div>
          <AnimatePresence>
            {showNudge && conversation.status === "disconnected" && (
              <FirstVisitNudge key="nudge" onDismiss={dismissNudge} />
            )}
          </AnimatePresence>
        </>
      )}

      {/* ── Chat view ─────────────────────────────────────────────────────── */}
      {activeView === "CHAT" && (
        <motion.div
          key="chat"
          initial={{ opacity: 0, scale: 0.92, y: 24 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: 16 }}
          style={{ transformOrigin: "bottom right", left: "auto" }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="avatar-widget mode-open shadow-2xl border border-white/10 bg-zinc-950 overflow-hidden flex flex-col"
        >
          <div className="flex flex-col h-full overflow-hidden relative pointer-events-auto">
            <div className="bubble-header flex-shrink-0 bg-zinc-900 border-b border-white/10 px-4 py-3 flex justify-between items-center z-50">
              <span className="font-semibold text-white tracking-wide text-sm flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${
                    conversation.status === "connected" ? "bg-green-500 animate-pulse" : "bg-gray-500"
                  }`}
                />
                Live Session
              </span>
              <button
                className="text-gray-400 hover:text-white transition-colors cursor-pointer p-1 -mr-1 rounded-md hover:bg-white/10 z-50 pointer-events-auto"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setActiveView("NONE");
                }}
                aria-label="Close Chat"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div
              className="bubble-content chat-history flex-1 overflow-y-auto flex flex-col gap-3 p-4 bg-zinc-900/95"
              ref={chatContainerRef}
            >
              {chatHistory.length === 0 ? (
                <div className="message-bubble assistant-message self-start bg-zinc-800 text-gray-200 p-3 rounded-xl rounded-tl-sm text-sm max-w-[85%] border border-white/5 shadow-sm">
                  Hi! I'm Wrina, your AI shopping assistant. Tap the orb to start a voice conversation.
                </div>
              ) : (
                chatHistory.map((msg) => (
                  <div
                    key={msg.id}
                    className={`message-bubble p-3 text-sm max-w-[85%] shadow-md ${
                      msg.source === "user"
                        ? "user-message self-end bg-blue-600 text-white rounded-2xl rounded-tr-sm border border-blue-500"
                        : "assistant-message self-start bg-zinc-800 text-gray-100 rounded-2xl rounded-tl-sm border border-white/5"
                    }`}
                  >
                    <span dangerouslySetInnerHTML={{ __html: formatMessage(msg.text) }} />
                  </div>
                ))
              )}
            </div>

            {/* Chat View Dock */}
            <div className="flex-none w-full bg-zinc-950 pb-6 px-4 z-10 pointer-events-auto border-t border-white/10">
              <div className="w-full flex items-center justify-center mt-4">
                <OrbDock
                  {...sharedDockProps}
                  scale="scale-75"
                  style={{
                    position: "relative",
                    width: "100%",
                    margin: "0",
                    height: "50px",
                    boxShadow: "none",
                    background: "transparent",
                    border: "none",
                    padding: "0",
                  }}
                />
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* ── Feedback view (Task 3) — full panel so it can't be missed ─────── */}
      {activeView === "FEEDBACK" && (
        <motion.div
          key="feedback"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          style={{ transformOrigin: "bottom right", left: "auto" }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          className="shopping-panel flex flex-col items-center justify-center bg-black/95 overflow-hidden shadow-2xl pointer-events-auto"
        >
          <div className="flex-none p-4 flex justify-end items-start absolute top-0 w-full z-50 pointer-events-none">
            <button
              className="bg-black/40 hover:bg-black/60 backdrop-blur-md text-white rounded-full w-10 h-10 flex items-center justify-center text-xl shadow-lg transition-all pointer-events-auto"
              onClick={() => submitFeedback(null, null)}
            >
              &times;
            </button>
          </div>
          <FeedbackCard
            onRate={(r, tag) => submitFeedback(r, tag)}
            onDismiss={() => submitFeedback(null, null)}
            onStepChange={() => {
              // User tapped an emoji — cancel the auto-dismiss so step 2 isn't cut short
              if (feedbackDismissTimerRef.current) { clearTimeout(feedbackDismissTimerRef.current); feedbackDismissTimerRef.current = null; }
            }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ─── AvatarWidget ─────────────────────────────────────────────────────────────

function AvatarWidget({ agentId, preview = false }) {
  const resolvedAgentId = agentId || window.__TEAM_POP_AGENT_ID__ || "YOUR_ELEVENLABS_AGENT_ID";
  const [activeView, setActiveView] = useState(preview ? "CHAT" : "NONE");
  const [latestProducts, setLatestProducts] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const carouselRef = useRef(null);
  const isProgrammaticScrollRef = useRef(false);
  const scrollEndTimerRef = useRef(null);

  // ── Drag position — always starts at bottom-right on page load (no persistence) ──
  const dragX = useMotionValue(0);
  const dragY = useMotionValue(0);
  const dragConstraintsRef = useRef(null);
  // No-op: drag position is not persisted across page loads
  const saveDragPosition = useCallback(() => {}, []);

  // Clean up scroll end timer on unmount
  useEffect(() => {
    return () => {
      if (scrollEndTimerRef.current) {
        clearTimeout(scrollEndTimerRef.current);
      }
    };
  }, []);

  const handleCarouselScroll = useCallback(() => {
    if (isProgrammaticScrollRef.current) return;
    if (scrollEndTimerRef.current) clearTimeout(scrollEndTimerRef.current);
    scrollEndTimerRef.current = setTimeout(() => {
      if (!carouselRef.current) return;
      const container = carouselRef.current;
      const children = Array.from(container.children);
      if (!children.length) return;
      const containerCenter = container.getBoundingClientRect().left + container.clientWidth / 2;
      let closest = 0;
      let minDist = Infinity;
      children.forEach((child, i) => {
        const rect = child.getBoundingClientRect();
        const childCenter = rect.left + rect.width / 2;
        const dist = Math.abs(childCenter - containerCenter);
        if (dist < minDist) { minDist = dist; closest = i; }
      });
      if (closest !== activeIndex) setActiveIndex(closest);
    }, 150);
  }, [activeIndex]);

  if (!resolvedAgentId || resolvedAgentId === "YOUR_ELEVENLABS_AGENT_ID") {
    return <div className="avatar-widget-error">Missing ElevenLabs Agent ID</div>;
  }

  return (
    // dragConstraintsRef bounds drag to the visible viewport so the widget can never be lost off-screen.
    <div ref={dragConstraintsRef} style={{ position: "fixed", inset: 0, pointerEvents: "none" }}>
      <AvatarInner
        agentId={resolvedAgentId}
        activeView={activeView}
        setActiveView={setActiveView}
        latestProducts={latestProducts}
        setLatestProducts={setLatestProducts}
        activeIndex={activeIndex}
        setActiveIndex={setActiveIndex}
        carouselRef={carouselRef}
        handleCarouselScroll={handleCarouselScroll}
        dragX={dragX}
        dragY={dragY}
        dragConstraintsRef={dragConstraintsRef}
        saveDragPosition={saveDragPosition}
      />
    </div>
  );
}

// ─── Public export ────────────────────────────────────────────────────────────

export default function LayeredAvatarWidget(props) {
  return (
    <div style={WIDGET_LAYER_STYLE}>
      <AvatarWidget {...props} />
    </div>
  );
}
