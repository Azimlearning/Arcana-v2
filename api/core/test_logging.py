import json

import pytest
import structlog

from api.core.logging import configure_logging, get_logger
from api.core.settings import Settings


@pytest.fixture(autouse=True)
def reset_structlog():
    """configure_logging binds structlog globally to this test's captured stderr. Without a reset,
    later tests that log would write to that closed stream."""
    yield
    structlog.reset_defaults()


def test_logs_are_structured_json_when_not_a_tty(capsys: pytest.CaptureFixture[str]):
    configure_logging("INFO")
    get_logger("t").info("retrieved", signal="dense", hits=3)
    line = capsys.readouterr().err.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "retrieved"
    assert record["hits"] == 3
    assert record["level"] == "info"


def test_level_filters_lower_severity(capsys: pytest.CaptureFixture[str]):
    configure_logging("WARNING")
    get_logger("t").info("quiet")
    assert capsys.readouterr().err == ""


def test_logging_settings_does_not_reveal_keys(capsys: pytest.CaptureFixture[str]):
    configure_logging("INFO")
    s = Settings(_env_file=None, anthropic_api_key="sk-leak-check")  # pyright: ignore[reportCallIssue]
    get_logger("t").info("settings", settings=repr(s))
    assert "sk-leak-check" not in capsys.readouterr().err
