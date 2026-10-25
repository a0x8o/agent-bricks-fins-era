"""Runtime configuration — everything from env vars, nothing hardcoded."""

from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    def __init__(self) -> None:
        self.app_mode: str = os.getenv("APP_MODE", "live")  # live | mock
        self.auth_mode: str = os.getenv("AUTH_MODE", "obo")  # obo | service_principal
        self.feature_streaming: bool = os.getenv("FEATURE_STREAMING", "true").lower() == "true"
        self.feature_persistence: bool = (
            os.getenv("FEATURE_PERSISTENCE", "false").lower() == "true"
        )
        self.warehouse_id: str = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
        self.genie_space_id: str = os.getenv("GENIE_SPACE_ID", "")
        self.uc_catalog: str = os.getenv("UC_CATALOG", "fins")
        self.uc_schema: str = os.getenv("UC_SCHEMA", "meridian")
        self.host: str = os.getenv("DATABRICKS_HOST", "").rstrip("/")
        self.cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "60"))
        self.genie_poll_timeout: int = int(os.getenv("GENIE_POLL_TIMEOUT", "120"))

    @property
    def mock(self) -> bool:
        return self.app_mode == "mock"

    @property
    def obo(self) -> bool:
        return self.auth_mode == "obo"

    @property
    def fq_prefix(self) -> str:
        return f"`{self.uc_catalog}`.`{self.uc_schema}`"


@lru_cache
def get_settings() -> Settings:
    return Settings()
