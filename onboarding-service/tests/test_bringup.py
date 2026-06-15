"""Phase 6 — pure bring-up orchestration logic (no processes/network).

bringup.sh wires these to real ngrok/psql/services; the fiddly bits
(pick the https tunnel, order migrations, idempotently rewrite .env,
which secrets are missing) are pure and unit-tested.
"""

import json

from services.bringup import (
    parse_ngrok_url,
    ordered_migrations,
    env_upsert,
    missing_secrets,
)


# ── parse_ngrok_url ──────────────────────────────────────────────────────────

def test_parse_ngrok_url_prefers_https_from_dict():
    api = {
        "tunnels": [
            {"public_url": "http://abc.ngrok-free.app", "proto": "http"},
            {"public_url": "https://abc.ngrok-free.app", "proto": "https"},
        ]
    }
    assert parse_ngrok_url(api) == "https://abc.ngrok-free.app"


def test_parse_ngrok_url_accepts_json_string():
    raw = json.dumps({"tunnels": [{"public_url": "https://x.ngrok.app", "proto": "https"}]})
    assert parse_ngrok_url(raw) == "https://x.ngrok.app"


def test_parse_ngrok_url_none_when_no_https_or_empty():
    assert parse_ngrok_url({"tunnels": [{"public_url": "http://x", "proto": "http"}]}) is None
    assert parse_ngrok_url({"tunnels": []}) is None
    assert parse_ngrok_url("not json") is None


# ── ordered_migrations ───────────────────────────────────────────────────────

def test_ordered_migrations_sorts_by_numeric_prefix():
    files = ["0002_sales_proof_seed.sql", "README.md", "0001_sales_agent.sql", "notes.txt"]
    assert ordered_migrations(files) == ["0001_sales_agent.sql", "0002_sales_proof_seed.sql"]


def test_ordered_migrations_ignores_non_numbered_sql():
    assert ordered_migrations(["hotfix.sql", "0010_x.sql", "0003_y.sql"]) == [
        "0003_y.sql",
        "0010_x.sql",
    ]


# ── env_upsert ───────────────────────────────────────────────────────────────

def test_env_upsert_replaces_existing_key_no_duplicate():
    out = env_upsert("A=1\nSEARCH_API_URL=old\nB=2\n", "SEARCH_API_URL", "https://new")
    assert out.count("SEARCH_API_URL=") == 1
    assert "SEARCH_API_URL=https://new" in out
    assert "A=1" in out and "B=2" in out


def test_env_upsert_appends_when_absent_and_fixes_trailing_newline():
    out = env_upsert("A=1", "VITE_SALES_AGENT_ID", "agent_x")
    assert out.endswith("VITE_SALES_AGENT_ID=agent_x\n")
    assert "A=1\n" in out


def test_env_upsert_does_not_partial_match_similar_keys():
    out = env_upsert("SEARCH_API_URL_OLD=keep\n", "SEARCH_API_URL", "v")
    assert "SEARCH_API_URL_OLD=keep" in out
    assert "SEARCH_API_URL=v" in out


# ── missing_secrets ──────────────────────────────────────────────────────────

def test_missing_secrets_all_present_is_empty():
    env = {
        "SUPABASE_URL": "u", "SUPABASE_KEY": "k",
        "ELEVENLABS_API_KEY": "e", "OPENROUTER_API_KEY": "o",
    }
    assert missing_secrets(env) == []


def test_missing_secrets_lists_absent_and_handles_llm_either():
    env = {"SUPABASE_URL": "u", "ELEVENLABS_API_KEY": "e", "OPENAI_API_KEY": "x"}
    miss = missing_secrets(env)
    assert "SUPABASE_KEY" in miss
    assert "OPENROUTER_API_KEY" not in miss  # OPENAI_API_KEY satisfies the LLM need
    assert missing_secrets({})  # everything missing → non-empty
