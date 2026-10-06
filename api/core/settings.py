"""Typed settings from the environment.

Every variable is documented in refdocs/guides/env_setup.md. Fakes are the default, so with
ARCANA_LLM_MODE=fake and ARCANA_EMBED_MODE=fake (the P0 default) no key is needed. A key that a
live mode requires but is missing raises ConfigError at startup, naming each variable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_SETUP_DOC = "refdocs/guides/env_setup.md"

Mode = Literal["fake", "live"]


class ConfigError(Exception):
    """Startup configuration is unusable. The message names every missing variable."""

    def __init__(self, missing: list[tuple[str, str]]):
        self.missing = missing
        lines = [f"  {name}: {why}" for name, why in missing]
        super().__init__(
            "Missing required configuration:\n"
            + "\n".join(lines)
            + f"\nSee {ENV_SETUP_DOC} for where to get each value."
        )


class Settings(BaseSettings):
    """Field names are the environment variable names, case-insensitively."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    arcana_llm_mode: Mode = "fake"
    arcana_embed_mode: Mode = "fake"
    arcana_data_dir: Path = Path("./data")
    arcana_ledger_path: Path | None = None
    """Where the spend ledger lives. Unset: in a live mode it is ./data/ledger.db, ONE file whatever the
    data directory is, so the monthly cap covers every run (the API and the eval share it); in fake mode it
    stays beside the data."""
    log_level: str = "INFO"

    anthropic_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    llm_monthly_cap_usd: float | None = None

    def missing_for_mode(self) -> list[tuple[str, str]]:
        """Variables the selected modes require but the environment did not supply."""
        missing: list[tuple[str, str]] = []
        if self.arcana_llm_mode == "live":
            if not _has(self.anthropic_api_key):
                missing.append(("ANTHROPIC_API_KEY", "required when ARCANA_LLM_MODE=live"))
            if not _has(self.openrouter_api_key):
                missing.append(("OPENROUTER_API_KEY", "required when ARCANA_LLM_MODE=live"))
        if self.arcana_embed_mode == "live" and not _has(self.openai_api_key):
            missing.append(("OPENAI_API_KEY", "required when ARCANA_EMBED_MODE=live"))
        if "live" in (self.arcana_llm_mode, self.arcana_embed_mode) and (
            self.llm_monthly_cap_usd is None or self.llm_monthly_cap_usd <= 0
        ):
            # Any paid call needs the cap: live embeddings with a fake LLM spend money too (constraint 8).
            missing.append(
                (
                    "LLM_MONTHLY_CAP_USD",
                    "required (a positive number) when ARCANA_LLM_MODE or ARCANA_EMBED_MODE is live",
                )
            )
        return missing


def _has(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    """Build settings and fail loudly if a live mode lacks its keys.

    Tests pass env_file=None so a developer's real .env never leaks into them.
    """
    settings = Settings(_env_file=env_file)  # pyright: ignore[reportCallIssue]
    missing = settings.missing_for_mode()
    if missing:
        raise ConfigError(missing)
    return settings
