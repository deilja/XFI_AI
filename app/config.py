import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("XFI_AI_APP_NAME", "XFI AI")
    environment: str = os.getenv("XFI_AI_ENV", "production")
    log_level: str = os.getenv("XFI_AI_LOG_LEVEL", "INFO")


def get_settings() -> Settings:
    return Settings()
