import pytest

from backend.app.config import Settings
from backend.app.llm.anthropic_client import AnthropicLLMClient
from backend.app.llm.mock_client import MockLLMClient
from backend.app.main import create_app


def test_settings_load_llm_provider_from_env():
    settings = Settings.from_env(
        {
            "APP_NAME": "Math Tutor Env",
            "DATABASE_URL": "sqlite:///test.db",
            "LLM_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "ANTHROPIC_MODEL": "claude-test-model",
            "ANTHROPIC_ROUTINE_MODEL": "claude-routine-model",
            "ANTHROPIC_HARD_MODEL": "claude-hard-model",
            "ANTHROPIC_TOP_MODEL": "claude-top-model",
            "ANTHROPIC_VERSION": "2023-06-01",
            "LLM_ROUTING_MODE": "tiered",
            "LLM_MAX_TOKENS": "384",
            "LLM_TIMEOUT_SECONDS": "9",
        }
    )

    assert settings.app_name == "Math Tutor Env"
    assert settings.database_url == "sqlite:///test.db"
    assert settings.llm_provider == "anthropic"
    assert settings.anthropic_api_key == "sk-ant-test"
    assert settings.anthropic_model == "claude-test-model"
    assert settings.anthropic_routine_model == "claude-routine-model"
    assert settings.anthropic_hard_model == "claude-hard-model"
    assert settings.anthropic_top_model == "claude-top-model"
    assert settings.anthropic_version == "2023-06-01"
    assert settings.llm_routing_mode == "tiered"
    assert settings.llm_max_tokens == 384
    assert settings.llm_timeout_seconds == 9


def test_app_uses_mock_llm_unless_provider_is_explicitly_configured():
    app = create_app(Settings(app_name="Math Tutor Test"))

    assert isinstance(app.state.turn_service.llm_client, MockLLMClient)


def test_app_rejects_anthropic_provider_without_api_key():
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        create_app(Settings(app_name="Math Tutor Test", llm_provider="anthropic"))


def test_app_uses_anthropic_client_when_provider_and_key_are_configured():
    app = create_app(
        Settings(
            app_name="Math Tutor Test",
            llm_provider="anthropic",
            anthropic_api_key="sk-ant-test",
        )
    )

    assert isinstance(app.state.turn_service.llm_client, AnthropicLLMClient)


class RecordingTransport:
    def __init__(self):
        self.calls = []

    def post_json(self, *, url, headers, payload, timeout_seconds):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "content": [
                {
                    "type": "tool_use",
                    "name": "emit_tutor_turn",
                    "input": {
                        "teacher_check": {
                            "student_error_tag": "unknown",
                            "next_scaffold_id": "level_1",
                            "leak_risk": "none",
                            "uses_only_authored_scaffold": True,
                            "chosen_pedagogical_move": "offer_heuristic_hint",
                        },
                        "dialogue": "Compare the two coordinates before choosing the rate.",
                        "pedagogical_move": "offer_heuristic_hint",
                        "ui_mode": "chat",
                        "proposed_hint_level": 1,
                    },
                }
            ],
            "stop_reason": "tool_use",
        }


def test_anthropic_client_sends_messages_tool_request_and_maps_tool_input():
    transport = RecordingTransport()
    client = AnthropicLLMClient(
        api_key="sk-ant-test",
        model="claude-test-model",
        transport=transport,
        max_tokens=256,
        timeout_seconds=5,
    )

    response = client.generate(
        check_result="incorrect",
        diagnostic=None,
        presenting_next=False,
        allowed_help_level=1,
    )

    assert response.dialogue == "Compare the two coordinates before choosing the rate."
    assert response.pedagogical_move == "offer_heuristic_hint"
    assert response.ui_mode == "chat"
    assert response.proposed_hint_level == 1
    assert response.teacher_check["leak_risk"] == "none"

    call = transport.calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == "sk-ant-test"
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    assert call["headers"]["content-type"] == "application/json"
    assert call["timeout_seconds"] == 5
    assert call["payload"]["model"] == "claude-test-model"
    assert call["payload"]["max_tokens"] == 256
    assert call["payload"]["messages"][0]["role"] == "user"
    assert call["payload"]["tools"][0]["name"] == "emit_tutor_turn"
    assert call["payload"]["tool_choice"] == {"type": "tool", "name": "emit_tutor_turn"}


def test_anthropic_client_uses_strong_model_for_all_tiers_by_default():
    transport = RecordingTransport()
    client = AnthropicLLMClient(
        api_key="sk-ant-test",
        model="claude-strong-model",
        routine_model="claude-routine-model",
        transport=transport,
    )

    client.generate(
        check_result=None,
        diagnostic=None,
        presenting_next=True,
        allowed_help_level=0,
        tier="routine",
    )

    assert transport.calls[0]["payload"]["model"] == "claude-strong-model"


def test_anthropic_client_uses_configured_tier_only_when_tiered_routing_enabled():
    transport = RecordingTransport()
    client = AnthropicLLMClient(
        api_key="sk-ant-test",
        model="claude-strong-model",
        routine_model="claude-routine-model",
        hard_model="claude-hard-model",
        routing_mode="tiered",
        transport=transport,
    )

    client.generate(
        check_result=None,
        diagnostic=None,
        presenting_next=True,
        allowed_help_level=0,
        tier="routine",
    )

    assert transport.calls[0]["payload"]["model"] == "claude-routine-model"
