/**
 * usePttInteraction — all PTT hold-to-talk logic, isolated from the widget.
 *
 * Design contract:
 *   - Parent calls syncStatus(status) whenever conversation.status changes.
 *   - Parent calls onConnected() when status transitions TO "connected".
 *   - Parent calls onDisconnected() when status transitions to "disconnected" or "error".
 *   - Orb binds: onPointerDown={beginPress}, onPointerUp={endPress},
 *                onPointerCancel={endPress}, onKeyDown={handleKeyDown}, onKeyUp={handleKeyUp}
 *   - beginPress receives (event, { agentId, startSession }) so this hook
 *     has no direct dependency on the conversation object.
 *
 * To remove PTT: delete this file and remove all `ptt.*` references in AvatarWidget.
 * To remove VAD: keep this file, remove handleInteraction from AvatarWidget.
 */

import { useRef, useCallback } from "react";

export function usePttInteraction({ setMuted }) {
  // Whether a press gesture is currently active
  const isPressActiveRef = useRef(false);

  // True when a press triggered session start and we are waiting for onConnected
  // to know whether to unmute (press still held) or stay muted (released early)
  const isAwaitingConnectRef = useRef(false);

  // Debounce guard against rapid session transitions
  const isTransitioningRef = useRef(false);

  // Mirror of conversation.status, kept current via syncStatus()
  const statusRef = useRef("disconnected");

  /**
   * Sync the internal status mirror. Call from a useEffect watching
   * conversation.status in the parent component.
   */
  const syncStatus = useCallback((status) => {
    statusRef.current = status;
  }, []);

  /**
   * Call when conversation.status transitions TO "connected".
   * Unmutes mic if the user is still holding, otherwise stays muted.
   */
  const onConnected = useCallback(() => {
    if (isAwaitingConnectRef.current) {
      isAwaitingConnectRef.current = false;
      if (isPressActiveRef.current) {
        setMuted(false); // press still held → open mic now
      }
      // else: user released before connect completed → stay muted
    }
  }, [setMuted]);

  /**
   * Call when conversation.status transitions to "disconnected" or "error".
   * Cleans up any in-progress hold state.
   */
  const onDisconnected = useCallback(() => {
    isPressActiveRef.current = false;
    isAwaitingConnectRef.current = false;
  }, []);

  /**
   * Pointer down handler — begin a hold gesture.
   * @param {PointerEvent} event
   * @param {{ agentId: string, startSession: Function }} sessionCtx
   */
  const beginPress = useCallback(
    (event, { agentId, startSession }) => {
      // Ignore non-primary mouse buttons (right-click, middle-click)
      if (event.pointerType === "mouse" && event.button !== 0) return;
      // Ignore if already in a hold
      if (isPressActiveRef.current) return;
      // Ignore rapid re-presses during session transition
      if (isTransitioningRef.current) return;

      isPressActiveRef.current = true;

      // Pointer capture keeps pointerup/cancel firing on this element
      // even when the pointer moves outside — critical for reliable release.
      if (event.currentTarget?.setPointerCapture && event.pointerId != null) {
        try {
          event.currentTarget.setPointerCapture(event.pointerId);
        } catch {
          // setPointerCapture can fail on some elements; proceed without it
        }
      }

      const status = statusRef.current;

      if (status === "disconnected" || status === "error") {
        // Start a new session. Mic stays muted; onConnected() will unmute
        // only if the press is still active when connection completes.
        isTransitioningRef.current = true;
        isAwaitingConnectRef.current = true;
        startSession({ agentId, connectionType: "websocket" });
        setTimeout(() => {
          isTransitioningRef.current = false;
        }, 500);
      } else if (status === "connected") {
        // Already connected — open mic immediately
        setMuted(false);
      }
      // status === "connecting": just record the press; onConnected() handles it
    },
    [setMuted]
  );

  /**
   * Pointer up / cancel handler — end a hold gesture and mute mic.
   */
  const endPress = useCallback(() => {
    if (!isPressActiveRef.current) return;
    isPressActiveRef.current = false;
    isAwaitingConnectRef.current = false;
    setMuted(true);
  }, [setMuted]);

  /**
   * Keyboard keydown — Space or Enter starts a hold (no repeat).
   */
  const handleKeyDown = useCallback(
    (event, sessionCtx) => {
      if (event.key !== " " && event.key !== "Enter") return;
      if (event.repeat) return;
      event.preventDefault();
      // Synthesise a pointer-like event shape for beginPress
      beginPress(
        { pointerType: "keyboard", button: 0, currentTarget: event.currentTarget, pointerId: null },
        sessionCtx
      );
    },
    [beginPress]
  );

  /**
   * Keyboard keyup — Space or Enter ends the hold.
   */
  const handleKeyUp = useCallback((event) => {
    if (event.key !== " " && event.key !== "Enter") return;
    event.preventDefault();
    endPress();
  }, [endPress]);

  return {
    isPressActiveRef,
    syncStatus,
    onConnected,
    onDisconnected,
    beginPress,
    endPress,
    handleKeyDown,
    handleKeyUp,
  };
}
