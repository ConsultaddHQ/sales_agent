/**
 * useVoiceMode — persists VAD/PTT mode selection to localStorage.
 *
 * Modes:
 *   "vad"  — Voice Activity Detection (default): tap to start, tap to stop.
 *   "ptt"  — Push-to-Talk: hold orb to speak, release to mute.
 *
 * To remove PTT support in the future: delete this file and
 * replace all `interactionMode` references in AvatarWidget with the
 * string literal "vad".
 */

import { useState, useEffect } from "react";

const STORAGE_KEY = "team-pop-voice-mode";

export function useVoiceMode() {
  const [mode, setMode] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved === "ptt" ? "ptt" : "vad";
    } catch {
      return "vad";
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // localStorage unavailable (e.g. incognito with storage blocked)
    }
  }, [mode]);

  return [mode, setMode];
}
