"""Phase 0 — sales agent ElevenLabs config (pure builders, no network).

These assert the contract the live ElevenLabs agent depends on:
tool names must match across config + prompt + widget (project invariant).
"""

from elevenlabs_agent import (
    build_sales_system_prompt,
    get_sales_tool_config,
    build_sales_agent_payload,
)

BRAIN_URL = "https://example.ngrok.app"
SITE = "teampop"

EXPECTED_TOOLS = {
    "sales_brain",
    "surface_proof",
    "navigate_site",
    "show_proof",
    "prefill_demo_form",
    "open_booking",
}


def test_sales_tool_config_has_exact_tool_set():
    tools = get_sales_tool_config(BRAIN_URL, SITE)
    assert {t["name"] for t in tools} == EXPECTED_TOOLS
    assert len(tools) == len(EXPECTED_TOOLS)


def test_brain_and_proof_are_webhooks_pointed_at_sales_routes():
    tools = {t["name"]: t for t in get_sales_tool_config(BRAIN_URL, SITE)}
    brain = tools["sales_brain"]
    proof = tools["surface_proof"]
    assert brain["type"] == "webhook"
    assert proof["type"] == "webhook"
    assert brain["api_schema"]["url"] == f"{BRAIN_URL}/sales/brain"
    assert proof["api_schema"]["url"] == f"{BRAIN_URL}/sales/proof"


def test_action_tools_are_client_tools():
    tools = {t["name"]: t for t in get_sales_tool_config(BRAIN_URL, SITE)}
    for name in ("navigate_site", "show_proof", "prefill_demo_form", "open_booking"):
        assert tools[name]["type"] == "client", name


def test_brain_session_identity_is_constant_not_llm_generated():
    """conversation_id must NOT be an LLM-filled param (LLMs truncate ids —
    same class of bug as the store_id truncation invariant)."""
    brain = {t["name"]: t for t in get_sales_tool_config(BRAIN_URL, SITE)}["sales_brain"]
    props = brain["api_schema"]["request_body_schema"]["properties"]
    assert "constant_value" in props["conversation_id"]
    assert "description" not in props["conversation_id"]  # not LLM-generated
    # Pin the exact ElevenLabs system variable — the §8 load-bearing
    # assumption; it must not silently change.
    assert props["conversation_id"]["constant_value"] == "{{system__conversation_id}}"
    assert props["site"]["constant_value"] == SITE
    # the visitor's words MUST be an LLM-generated param
    assert "description" in props["message"]
    assert "constant_value" not in props["message"]


def test_sales_prompt_encodes_the_non_negotiable_guardrails():
    p = build_sales_system_prompt("Team Pop")
    assert "sales_brain" in p
    low = p.lower()
    assert "every" in low and "turn" in low          # consult brain every turn
    assert "surface_proof" in p                       # proof only via tool
    assert "invent" in low or "make up" in low or "fabricate" in low
    assert "confirm" in low                           # assisted close: confirm before submit


def test_sales_agent_payload_shape_matches_elevenlabs_format():
    payload = build_sales_agent_payload(site=SITE, brain_api_url=BRAIN_URL)
    prompt_cfg = payload["conversation_config"]["agent"]["prompt"]
    assert prompt_cfg["ignore_default_personality"] is True
    assert len(prompt_cfg["tools"]) == len(EXPECTED_TOOLS)
    assert "tts" in payload["conversation_config"]
    assert "turn" in payload["conversation_config"]
    assert payload["conversation_config"]["agent"]["language"] == "en"
