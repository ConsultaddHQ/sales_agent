import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getVisualState,
  getStatusLabel,
  THINKING_SILENCE_MS,
  SEARCH_FAIL_FALLBACK_MS,
} from "./visualState.js";

describe("getVisualState", () => {
  it("returns SEARCH_FAIL when connected VAD and searchFailed, even if THINKING", () => {
    assert.equal(
      getVisualState({
        status: "connected",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "THINKING",
        searchFailed: true,
      }),
      "SEARCH_FAIL",
    );
  });

  it("lets AGENT_SPEAKING override SEARCH_FAIL so the apology is visible", () => {
    assert.equal(
      getVisualState({
        status: "connected",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "AGENT_SPEAKING",
        searchFailed: true,
      }),
      "AGENT_SPEAKING",
    );
  });

  it("keeps connection ERROR distinct from SEARCH_FAIL", () => {
    assert.equal(
      getVisualState({
        status: "error",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "LISTENING",
        searchFailed: true,
      }),
      "ERROR",
    );
  });

  it("returns THINKING when connected and not failed", () => {
    assert.equal(
      getVisualState({
        status: "connected",
        interactionMode: "vad",
        isPressActive: false,
        vadSubState: "THINKING",
        searchFailed: false,
      }),
      "THINKING",
    );
  });
});

describe("getStatusLabel", () => {
  it("uses dedicated copy for SEARCH_FAIL", () => {
    assert.equal(getStatusLabel("SEARCH_FAIL"), "Couldn't search — try again");
  });
});

describe("timing constants", () => {
  it("cuts silence debounce to 150ms and fallback to cascade 8s", () => {
    assert.equal(THINKING_SILENCE_MS, 150);
    assert.equal(SEARCH_FAIL_FALLBACK_MS, 8000);
  });
});
