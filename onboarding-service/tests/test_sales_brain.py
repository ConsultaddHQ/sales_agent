"""Phase 1 — the stateful sales brain (pure logic, fake LLM, no network/DB).

The brain is the trained AE. These tests pin the behaviours that make it
"next level" vs a static prompt: it cannot be talked backwards out of the
sale, it accumulates the Problem Identification Chart, it only emits known
directives, it survives a junk LLM response, and it threads session state.
"""

import json

from services.sales_brain import (
    SalesBrain,
    STAGES,
    ALLOWED_DIRECTIVES,
    parse_decision,
    advance_stage,
    merge_pic,
    merge_captured,
    sanitize_directives,
    _MAX_TRANSCRIPT,
)


def fake_llm(payload):
    """Returns a canned raw string; tests set .next per call."""
    return fake_llm.next


def make_brain():
    return SalesBrain(llm=lambda system, user: fake_llm(user), playbook="PLAYBOOK TEXT")


def new_session():
    return {
        "stage": "rapport",
        "pic": [],
        "captured": {},
        "transcript": [],
        "objections": [],
        "proof_shown": [],
        "booked": False,
    }


# ── parse_decision: robust to fences / prose / junk ──────────────────────────

def test_parse_decision_plain_json():
    assert parse_decision('{"stage":"discovery"}') == {"stage": "discovery"}


def test_parse_decision_strips_code_fence_and_prose():
    raw = 'Sure!\n```json\n{"stage": "demo", "say_guidance": "hi"}\n```\nhope that helps'
    assert parse_decision(raw)["stage"] == "demo"


def test_parse_decision_junk_returns_empty():
    assert parse_decision("the model rambled with no json") == {}
    assert parse_decision("") == {}


# ── stage machine: cannot be reset backwards ─────────────────────────────────

def test_advance_stage_moves_forward():
    assert advance_stage("rapport", "discovery") == "discovery"
    assert advance_stage("discovery", "pricing") == "pricing"  # skipping forward ok


def test_advance_stage_blocks_big_backward_jump():
    # LLM hallucinates a reset — brain refuses to lose the sale
    assert advance_stage("pricing", "rapport") == "pricing"


def test_advance_stage_allows_one_step_back_and_objection_anytime():
    assert advance_stage("demo", "quantify_gap") == "quantify_gap"   # one step back ok
    assert advance_stage("close", "objection") == "objection"        # objection anytime
    assert advance_stage("rapport", "not_a_stage") == "rapport"      # unknown clamped


# ── PIC accumulates (Gap Selling core) ───────────────────────────────────────

def test_merge_pic_appends_new_and_enriches_existing():
    existing = [{"technical_problem": "manual SDR outreach", "business_impact": "", "root_cause": ""}]
    update = [
        {"technical_problem": "manual SDR outreach", "business_impact": "20 hrs/wk lost"},
        {"technical_problem": "slow lead response", "business_impact": "leads go cold"},
    ]
    merged = merge_pic(existing, update)
    assert len(merged) == 2
    sdr = next(p for p in merged if p["technical_problem"] == "manual SDR outreach")
    assert sdr["business_impact"] == "20 hrs/wk lost"  # enriched, not duplicated


def test_merge_captured_ignores_empties():
    assert merge_captured({"email": "a@b.com"}, {"name": "Jane", "email": ""}) == {
        "email": "a@b.com",
        "name": "Jane",
    }


# ── directives are whitelisted ───────────────────────────────────────────────

def test_sanitize_directives_drops_unknown_tools_and_bad_shapes():
    raw = [
        {"tool": "surface_proof", "args": {"query": "roi"}},
        {"tool": "rm_rf", "args": {}},          # not allowed
        {"tool": "navigate_site"},               # missing args -> defaulted
        "not even a dict",
    ]
    out = sanitize_directives(raw)
    tools = [d["tool"] for d in out]
    assert tools == ["surface_proof", "navigate_site"]
    assert all(d["tool"] in ALLOWED_DIRECTIVES for d in out)
    assert out[1]["args"] == {}


# ── decide(): threads state, survives junk, can't be reset ───────────────────

def test_decide_happy_path_threads_state_and_directives():
    brain = make_brain()
    fake_llm.next = json.dumps({
        "stage": "discovery",
        "say_guidance": "What does that cost you each month?",
        "next_move": "quantify_gap",
        "pic_update": [{"technical_problem": "manual outreach", "business_impact": "20 hrs/wk"}],
        "captured_fields": {"email": "jane@acme.com"},
        "directives": [{"tool": "surface_proof", "args": {"query": "sdr roi"}}],
    })
    decision, session = brain.decide(new_session(), "We do outreach by hand", activity=None)
    assert decision.stage == "discovery"
    assert decision.directives[0]["tool"] == "surface_proof"
    assert session["captured"]["email"] == "jane@acme.com"
    assert session["pic"][0]["technical_problem"] == "manual outreach"
    # transcript recorded both turns
    roles = [t["role"] for t in session["transcript"]]
    assert roles == ["visitor", "agent"]


def test_decide_junk_llm_falls_back_safely_without_losing_stage():
    brain = make_brain()
    fake_llm.next = "total nonsense, no json here"
    started = new_session()
    started["stage"] = "pricing"
    decision, session = brain.decide(started, "hmm not sure", activity=None)
    assert session["stage"] == "pricing"          # stage preserved
    assert decision.say_guidance                   # still says something useful
    assert decision.directives == []               # no risky actions on junk


def test_decide_refuses_llm_attempt_to_reset_the_sale():
    brain = make_brain()
    fake_llm.next = json.dumps({"stage": "rapport", "say_guidance": "hi again"})
    started = new_session()
    started["stage"] = "close"
    decision, session = brain.decide(started, "anyway", activity=None)
    assert decision.stage == "close"  # advance_stage guard wins


def test_stages_constant_matches_playbook_motion():
    assert STAGES[0] == "rapport" and STAGES[-1] == "booked"
    assert "discovery" in STAGES and "pricing" in STAGES and "close" in STAGES


# ── review remediation: transcript cap (I1) + stage normalization (I2) ───────

def test_transcript_is_capped_to_max():
    """A long voice call must not grow an unbounded persisted transcript."""
    s = new_session()
    s["transcript"] = [{"role": "visitor", "text": f"m{i}"} for i in range(_MAX_TRANSCRIPT * 2)]
    fake_llm.next = json.dumps({"stage": "discovery", "say_guidance": "go on"})
    _, session = brain_decide(s, "newest message")
    assert len(session["transcript"]) == _MAX_TRANSCRIPT
    # newest turns are kept (the just-added agent line is last)
    assert session["transcript"][-1] == {"role": "agent", "text": "go on"}
    assert session["transcript"][-2] == {"role": "visitor", "text": "newest message"}


def test_decide_normalizes_bogus_persisted_stage_so_guard_cannot_be_bypassed():
    """A persisted stage outside STAGES must not make advance_stage accept
    any LLM-proposed stage unconditionally."""
    s = new_session()
    s["stage"] = "garbage_not_a_stage"
    fake_llm.next = json.dumps({"stage": "close", "say_guidance": "hi"})
    decision, session = brain_decide(s, "hello")
    assert decision.stage in STAGES
    assert session["stage"] in STAGES


def brain_decide(session, message):
    return make_brain().decide(session, message)
