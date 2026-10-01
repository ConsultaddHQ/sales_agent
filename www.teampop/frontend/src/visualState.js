export const CONNECTING_MESSAGES = [
  "Connecting...",
  "Setting up your assistant...",
  "Almost ready...",
];
export const CONNECTING_MESSAGE_INTERVAL_MS = 1500;
export const THINKING_SILENCE_MS = 150;
export const SEARCH_FAIL_FALLBACK_MS = 8000;

export function getVisualState({
  status,
  interactionMode,
  isPressActive,
  vadSubState,
  searchFailed = false,
  micBlocked = false,
}) {
  if (status === "connecting") return "CONNECTING";
  // Mic refused (browser "Block", or the Shopify theme-editor iframe, which has
  // no microphone permission) — a distinct, explainable state, not a generic error.
  if (micBlocked && status !== "connected") return "MIC_BLOCKED";
  if (status === "error") return "ERROR";

  if (status === "connected") {
    if (interactionMode === "ptt") {
      if (isPressActive) return "PTT_HOLDING";
      if (searchFailed) return "SEARCH_FAIL";
      return "PTT_MUTED_CONNECTED";
    }
    if (vadSubState === "AGENT_SPEAKING") return "AGENT_SPEAKING";
    if (searchFailed) return "SEARCH_FAIL";
    return vadSubState || "LISTENING";
  }

  return interactionMode === "ptt" ? "PTT_READY" : "IDLE";
}

export function getStatusLabel(visualState, connectingMessageIndex = 0) {
  switch (visualState) {
    case "IDLE":
      return "Talk to AI";
    case "CONNECTING":
      return CONNECTING_MESSAGES[connectingMessageIndex % CONNECTING_MESSAGES.length];
    case "LISTENING":
      return "Listening...";
    case "THINKING":
      return "Thinking...";
    case "AGENT_SPEAKING":
      return "Speaking...";
    case "SEARCH_FAIL":
      return "Couldn't search — try again";
    case "PTT_READY":
      return "Hold to speak";
    case "PTT_MUTED_CONNECTED":
      return "Hold to talk";
    case "PTT_HOLDING":
      return "Listening";
    case "ERROR":
      return "Retry";
    case "MIC_BLOCKED":
      return "Allow mic to talk";
    default:
      return "";
  }
}

/** True when an ElevenLabs/getUserMedia error means the microphone was refused. */
export function isMicPermissionError(error) {
  const text = String(error?.name || "") + " " + String(error?.message || error || "");
  return /NotAllowedError|Permission denied|permission dismissed|not allowed/i.test(text);
}

/** Shopify sets Shopify.designMode inside the theme editor, whose iframe can't use the mic. */
export function isShopifyThemeEditor(win = typeof window !== "undefined" ? window : undefined) {
  return Boolean(win?.Shopify?.designMode);
}
