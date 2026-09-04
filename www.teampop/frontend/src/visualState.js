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
}) {
  if (status === "connecting") return "CONNECTING";
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
    default:
      return "";
  }
}
