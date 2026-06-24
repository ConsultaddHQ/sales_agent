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
const SESSION_HARD_LIMIT_MS = 270000;
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

  if (step === 1) {
    return (
      <motion.div
        key="feedback-step1"
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.95 }}
        style={{ position: "fixed", bottom: "20px", right: "20px" }}
        className="flex flex-col items-center gap-3 p-4 bg-zinc-900 rounded-2xl border border-white/10 shadow-2xl pointer-events-auto w-56"
      >
        <span className="text-white text-sm font-semibold text-center">How was your experience?</span>
        <div className="flex gap-3">
          {[["😍", "positive"], ["😐", "neutral"], ["😕", "negative"]].map(([emoji, r]) => (
            <button
              key={r}
              onClick={() => handleEmoji(r)}
              className="w-12 h-12 rounded-full bg-zinc-800 hover:bg-zinc-700 border border-white/10 hover:border-white/30 transition-all flex items-center justify-center text-2xl hover:scale-110 active:scale-95"
              aria-label={r}
            >
              {emoji}
            </button>
          ))}
        </div>
        <button onClick={onDismiss} className="text-gray-500 text-xs hover:text-gray-300 transition-colors cursor-pointer">
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
      style={{ position: "fixed", bottom: "20px", right: "20px" }}
      className="flex flex-col items-center gap-2 p-4 bg-zinc-900 rounded-2xl border border-white/10 shadow-2xl pointer-events-auto w-56"
    >
      <span className="text-white text-sm font-semibold text-center">{FOLLOW_UP_PROMPTS[rating]}</span>
      <div className="flex flex-col gap-2 w-full">
        {FOLLOW_UP_OPTIONS[rating].map((tag) => (
          <button
            key={tag}
            onClick={() => handleTag(tag)}
            className="w-full px-3 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 border border-white/10 hover:border-white/30 text-gray-200 text-xs text-left transition-all hover:text-white cursor-pointer"
          >
            {tag}
          </button>
        ))}
      </div>
      <button onClick={onDismiss} className="text-gray-500 text-xs hover:text-gray-300 transition-colors mt-1 cursor-pointer">
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

/**
 * Map visual state to shopper-facing status pill text.
 */
function getStatusLabel(visualState) {
  switch (visualState) {
    case "IDLE":                return "Talk to AI";
    case "CONNECTING":          return "Connecting...";
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
  scale = "",
  style = {},
  inactive = false,
}) {
  const statusLabel = getStatusLabel(visualState);
  const isPtt = interactionMode === "ptt";

  const PILL_STYLES = {
    LISTENING:     "bg-green-500/20 text-green-400 border-green-500/30 shadow-[0_0_10px_rgba(34,197,94,0.2)]",
    THINKING:      "bg-cyan-500/20 text-cyan-400 border-cyan-500/30 shadow-[0_0_10px_rgba(6,182,212,0.2)]",
    AGENT_SPEAKING:"bg-purple-500/20 text-purple-400 border-purple-500/30 shadow-[0_0_10px_rgba(168,85,247,0.2)]",
    CONNECTING:    "bg-amber-500/20 text-amber-400 border-amber-500/30 shadow-[0_0_10px_rgba(245,158,11,0.2)]",
    PTT_HOLDING:   "bg-green-500/20 text-green-400 border-green-500/30 shadow-[0_0_10px_rgba(34,197,94,0.2)]",
  };
  const pillStyle = PILL_STYLES[visualState] || "bg-zinc-800/80 text-gray-400 border-white/5";

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
          className={`absolute -top-7 text-[9px] uppercase font-bold tracking-widest px-2 py-0.5 rounded-full whitespace-nowrap transition-all duration-300 border flex items-center gap-1 ${pillStyle}`}
        >
          {visualState === "IDLE" && (
            <svg className="w-2.5 h-2.5 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V20H9v2h6v-2h-2v-2.08A7 7 0 0 0 19 11h-2z"/>
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
          Chat
        </button>
      </div>
    </div>
  );
}

// ─── ProductDetails ───────────────────────────────────────────────────────────

const ProductDetails = ({ product, highlightPrice, isCarted, onShopNow, onAddToCart }) => {
  const [isExpanded, setIsExpanded] = useState(false);
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
        {isCarted ? (
          <button
            disabled
            className="shopping-cta text-center bg-green-700 text-white px-5 py-2 rounded-full font-bold text-sm opacity-80 cursor-default"
          >
            Added ✓
          </button>
        ) : onAddToCart && (
          <button
            onClick={(e) => { e.preventDefault(); onAddToCart(product); }}
            className="shopping-cta text-center bg-green-500 text-white px-5 py-2 rounded-full font-bold text-sm hover:bg-green-600 transition"
          >
            Add to Cart
          </button>
        )}
      </div>
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
  const [cartedIds, setCartedIds] = useState(() => new Set());
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
    },
    onInterruption: (details) => {
      sessionMetricsRef.current.interruptionCount += 1;
      console.log(`[ElevenLabs] onInterruption #${sessionMetricsRef.current.interruptionCount}:`, details);
    },
    onModeChange: (modeObj) => {
      console.log(`[ElevenLabs] onModeChange event at ${Date.now()}:`, modeObj);
    },
    onVadScore: (score) => {
      // Under WebRTC there is no local input analyser (getInputVolume() returns 0),
      // so the rAF loop below can't detect user speech. Drive the LISTENING state from
      // the server's VAD score instead, so the orb still reacts to the user's voice.
      // When the user goes quiet, the rAF loop's THINKING timer takes over.
      if (typeof score === "number" && score > 0.5 && !agentIsSpeakingRef.current) {
        if (thinkingTimerRef.current) { clearTimeout(thinkingTimerRef.current); thinkingTimerRef.current = null; }
        if (vadSubStateRef.current !== "LISTENING") {
          vadSubStateRef.current = "LISTENING";
          setVadSubState("LISTENING");
        }
      }
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

  // ── VAD session helpers ───────────────────────────────────────────────────
  const startVoiceSession = useCallback(() => {
    setChatHistory([]);
    setAgentSubtitle("");
    setHighlightPrice(false);
    setCartedIds(new Set());
    variantCacheRef.current.clear();
    const now = Date.now();
    inactivityRef.current = { startAt: now, lastMeaningfulUserAt: now };
    sessionMetricsRef.current = { startAt: now, productsShown: 0, productsClicked: 0, shopNowClicked: false, chatMessages: 0, endReason: null, conversationId: null, latencyFirstAiMs: null, latencyProductsMs: null, toolCalls: 0, interruptionCount: 0 };
    // Use WebRTC (the SDK's default for voice), NOT websocket. The websocket path
    // dispatches each incoming audio chunk to its output listener the instant it
    // arrives with no buffering — but that listener is only attached AFTER the audio
    // worklet finishes loading (which happens after the socket is already open and
    // receiving). Any first_message audio that arrives in that gap is silently dropped.
    // Low-latency clients (e.g. US → ElevenLabs) lose this race and never hear the
    // opening greeting; high-latency clients (e.g. India) get the audio late enough
    // that the listener is ready. WebRTC plays audio through the browser's own media
    // pipeline (a subscribed track on an <audio autoplay> element), which buffers the
    // stream and is not subject to this drop.
    conversation.startSession({ agentId, connectionType: "webrtc" });
  }, [conversation, agentId]);

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
      feedbackDismissTimerRef.current = setTimeout(() => {
        setActiveView((prev) => prev === "FEEDBACK" ? "NONE" : prev);
      }, 8000);
    } else {
      setActiveView("NONE");
    }
  }, [conversation, setActiveView]);

  // ── Watch agentIsSpeaking to fire farewell-end after speech finishes ─────────
  // Placed here so endSessionAndCollapse is already in scope (avoids TDZ crash).
  useEffect(() => {
    if (!agentIsSpeaking && pendingFarewellEndRef.current) {
      const reason = pendingFarewellEndRef.current;
      pendingFarewellEndRef.current = null;
      if (farewellFallbackTimerRef.current) { clearTimeout(farewellFallbackTimerRef.current); farewellFallbackTimerRef.current = null; }
      setTimeout(() => endSessionAndCollapse(reason), 500);
    }
  }, [agentIsSpeaking, endSessionAndCollapse]);

  // ── Tool: end_session (Task 1 — agent-initiated farewell) ────────────────────
  // Wait for agentIsSpeaking → false (watched in useEffect below), then disconnect.
  // A 5s hard fallback fires if speech never finishes cleanly.
  useConversationClientTool("end_session", (parameters) => {
    const reason = `agent_farewell: ${parameters?.reason || "goodbye"}`;
    console.log("[session] Agent called end_session:", reason);
    // Cancel any pending graceful-end timer so it doesn't race
    if (gracefulEndTimerRef.current) { clearTimeout(gracefulEndTimerRef.current); gracefulEndTimerRef.current = null; }
    pendingFarewellEndRef.current = reason;
    // Hard fallback: disconnect after 5s even if speech event never fires
    if (farewellFallbackTimerRef.current) clearTimeout(farewellFallbackTimerRef.current);
    farewellFallbackTimerRef.current = setTimeout(() => {
      farewellFallbackTimerRef.current = null;
      if (pendingFarewellEndRef.current) {
        console.log("[session] Farewell fallback timer fired — ending now");
        pendingFarewellEndRef.current = null;
        endSessionAndCollapse(reason);
      }
    }, 5000);
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

  // Shared add-to-cart logic used by both the voice tool and the manual button.
  const performAddToCart = useCallback(async (product, variantIndex = 0, quantity = 1) => {
    if (!cartEnabled) {
      return "This store uses Shop Now — open the product link to purchase.";
    }
    // On demo pages simulate success immediately — /cart/add.js doesn't exist here
    // and variant fetch would hit the wrong origin, so skip both.
    if (window.__TEAM_POP_DEMO__) {
      setCartToast("success");
      if (cartToastTimerRef.current) clearTimeout(cartToastTimerRef.current);
      cartToastTimerRef.current = setTimeout(() => setCartToast(null), 3000);
      setCartedIds(prev => { const n = new Set(prev); n.add(String(product.id)); return n; });
      return `Added ${product.name} to cart!`;
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
        body: JSON.stringify({ id: variant.id, quantity }),
      });
      if (!r.ok) throw new Error(await r.text());
      await r.json();
      setCartToast("success");
      if (cartToastTimerRef.current) clearTimeout(cartToastTimerRef.current);
      cartToastTimerRef.current = setTimeout(() => setCartToast(null), 3000);
      setCartedIds(prev => { const n = new Set(prev); n.add(String(product.id)); return n; });
      return `Added ${product.name} to cart!`;
    } catch (err) {
      setCartToast("error");
      if (cartToastTimerRef.current) clearTimeout(cartToastTimerRef.current);
      cartToastTimerRef.current = setTimeout(() => setCartToast(null), 3000);
      return `Could not add to cart. Please try the Shop Now link instead.`;
    }
  }, [cartEnabled, fetchVariants]);

  useConversationClientTool("add_to_cart", (parameters) => {
    if (!cartEnabled) return Promise.resolve("This store uses Shop Now — open the product link to purchase.");
    const { product_id, variant_index = 0, quantity = 1 } = parameters || {};
    const product = latestProductsRef.current.find(p => String(p.id) === String(product_id));
    if (!product) return Promise.resolve("Product not found in current view");
    return performAddToCart(product, variant_index, quantity);
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

      // 1. Hard session limit (270s)
      if (now - r.startAt > SESSION_HARD_LIMIT_MS) {
        console.log("[session] Ending session due to 270s hard limit.");
        gracefulEndSession("Ending session due to 270s hard limit.");
        return;
      }

      // 2. Ignore/reset inactivity conditions
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
    onRightAction: () => setActiveView("CHAT"),
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
                    product={latestProducts[safeIndex]}
                    highlightPrice={highlightPrice}
                    isCarted={cartedIds.has(String(latestProducts[safeIndex]?.id))}
                    onShopNow={() => { sessionMetricsRef.current.shopNowClicked = true; }}
                    onAddToCart={cartEnabled ? (product) => {
                      setCartToast("adding");
                      performAddToCart(product, 0, 1);
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

      {/* ── Feedback card (Task 3) ────────────────────────────────────────── */}
      {activeView === "FEEDBACK" && (
        <FeedbackCard
          onRate={(r, tag) => submitFeedback(r, tag)}
          onDismiss={() => submitFeedback(null, null)}
          onStepChange={() => {
            // User tapped an emoji — cancel the 8s auto-dismiss so step 2 isn't cut short
            if (feedbackDismissTimerRef.current) { clearTimeout(feedbackDismissTimerRef.current); feedbackDismissTimerRef.current = null; }
          }}
        />
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
