"""Phase 5 — pure preflight logic (no network/DB).

The scripts wire these to real Supabase/ElevenLabs I/O; the decision
logic (what's required, is the brain URL reachable, do we go) is pure.
"""

from services.preflight import (
    resolve_brain_url,
    env_checks,
    overall_ok,
    PASS,
    WARN,
    FAIL,
)


def test_resolve_brain_url_missing_is_fail():
    c = resolve_brain_url({})
    assert c.status == FAIL


def test_resolve_brain_url_localhost_is_warn():
    c = resolve_brain_url({"SEARCH_API_URL": "http://localhost:8005"})
    assert c.status == WARN
    assert "ngrok" in c.detail or "reach" in c.detail


def test_resolve_brain_url_https_public_is_pass_and_returns_url():
    c = resolve_brain_url({"SEARCH_API_URL": "https://abc.ngrok-free.app/"})
    assert c.status == PASS
    assert c.detail == "https://abc.ngrok-free.app"  # trailing slash trimmed


def test_sales_brain_url_overrides_search_api_url():
    c = resolve_brain_url({
        "SEARCH_API_URL": "https://search.example.com",
        "SALES_BRAIN_URL": "https://brain.ngrok-free.app",
    })
    assert c.detail == "https://brain.ngrok-free.app"


def test_non_https_public_is_warn():
    c = resolve_brain_url({"SEARCH_API_URL": "http://abc.ngrok-free.app"})
    assert c.status == WARN


def test_env_checks_all_present_pass():
    env = {
        "SUPABASE_URL": "https://x.supabase.co",
        "SUPABASE_KEY": "k",
        "ELEVENLABS_API_KEY": "e",
        "OPENROUTER_API_KEY": "o",
    }
    checks = env_checks(env)
    assert all(c.status == PASS for c in checks)


def test_env_checks_missing_key_is_fail():
    checks = {c.name: c for c in env_checks({"SUPABASE_URL": "u", "ELEVENLABS_API_KEY": "e", "OPENROUTER_API_KEY": "o"})}
    assert checks["SUPABASE_KEY"].status == FAIL


def test_llm_key_accepts_either_provider():
    base = {"SUPABASE_URL": "u", "SUPABASE_KEY": "k", "ELEVENLABS_API_KEY": "e"}
    only_openai = {c.name: c for c in env_checks({**base, "OPENAI_API_KEY": "x"})}
    none = {c.name: c for c in env_checks(base)}
    assert only_openai["LLM_API_KEY"].status == PASS
    assert none["LLM_API_KEY"].status == FAIL


def test_overall_ok_false_on_any_fail():
    base = {"SUPABASE_URL": "u", "SUPABASE_KEY": "k", "ELEVENLABS_API_KEY": "e", "OPENROUTER_API_KEY": "o"}
    assert overall_ok(env_checks(base)) is True
    assert overall_ok(env_checks({"SUPABASE_URL": "u"})) is False
