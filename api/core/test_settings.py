import pytest

from api.core.settings import ConfigError, load_settings

ALL_KEYS = [
    "ARCANA_LLM_MODE",
    "ARCANA_EMBED_MODE",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "LLM_MONTHLY_CAP_USD",
    "ARCANA_DATA_DIR",
    "LOG_LEVEL",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for key in ALL_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_fakes_are_the_default_and_need_no_key():
    s = load_settings(env_file=None)
    assert s.arcana_llm_mode == "fake"
    assert s.arcana_embed_mode == "fake"
    assert s.missing_for_mode() == []


def test_live_llm_without_anthropic_key_names_the_variable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARCANA_LLM_MODE", "live")
    with pytest.raises(ConfigError) as exc:
        load_settings(env_file=None)
    message = str(exc.value)
    assert "ANTHROPIC_API_KEY" in message
    assert "refdocs/guides/env_setup.md" in message


def test_live_llm_reports_every_missing_variable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARCANA_LLM_MODE", "live")
    with pytest.raises(ConfigError) as exc:
        load_settings(env_file=None)
    names = {name for name, _ in exc.value.missing}
    assert names == {"ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "LLM_MONTHLY_CAP_USD"}


def test_live_embed_requires_openai_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARCANA_EMBED_MODE", "live")
    with pytest.raises(ConfigError) as exc:
        load_settings(env_file=None)
    assert "OPENAI_API_KEY" in str(exc.value)


def test_blank_key_counts_as_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARCANA_EMBED_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    with pytest.raises(ConfigError):
        load_settings(env_file=None)


def test_non_positive_cap_counts_as_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARCANA_LLM_MODE", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k2")
    monkeypatch.setenv("LLM_MONTHLY_CAP_USD", "0")
    with pytest.raises(ConfigError) as exc:
        load_settings(env_file=None)
    assert [n for n, _ in exc.value.missing] == ["LLM_MONTHLY_CAP_USD"]


def test_fully_configured_live_mode_loads(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARCANA_LLM_MODE", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k2")
    monkeypatch.setenv("LLM_MONTHLY_CAP_USD", "5")
    s = load_settings(env_file=None)
    assert s.llm_monthly_cap_usd == 5


def test_secrets_do_not_appear_in_repr(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-do-not-print")
    s = load_settings(env_file=None)
    assert "sk-do-not-print" not in repr(s)
    assert "sk-do-not-print" not in str(s)
