from pathlib import Path

from backend.app.config import Settings
from backend.app.evals.live_llm_smoke import build_gemini_settings, load_key_env_file


def test_load_key_env_file_reads_only_provider_keys(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgres://secret-db",
                "GOOGLE_API_KEY='google-test-key'",
                'GEMINI_API_KEY="gemini-test-key"',
                "UNRELATED_SECRET=do-not-load",
            ]
        )
    )

    loaded = load_key_env_file(env_file)

    assert loaded == {
        "GOOGLE_API_KEY": "google-test-key",
        "GEMINI_API_KEY": "gemini-test-key",
    }


def test_build_gemini_settings_prefers_process_env_over_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=file-key\nGEMINI_MODEL=ignored-file-model\n")

    settings = build_gemini_settings(
        env_file=env_file,
        process_env={
            "GOOGLE_API_KEY": "process-key",
            "GEMINI_MODEL": "gemini-live-test-model",
            "LLM_MAX_TOKENS": "128",
        },
    )

    assert isinstance(settings, Settings)
    assert settings.llm_provider == "gemini"
    assert settings.google_api_key == "process-key"
    assert settings.gemini_model == "gemini-live-test-model"
    assert settings.llm_max_tokens == 128
