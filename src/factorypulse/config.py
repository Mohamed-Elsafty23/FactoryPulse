"""Central configuration. The only place that knows local paths from Azure paths."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    """Which environment the code is running against."""

    LOCAL = "local"
    AZURE_DEV = "azure_dev"
    AZURE_PROD = "azure_prod"


class Settings(BaseSettings):
    """Validated settings, loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Env = Env.LOCAL

    storage_bucket: str = "factorypulse"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"

    adls_account: str = ""
    adls_container: str = "lake"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "factorypulse"
    postgres_user: str = "factorypulse"
    postgres_password: str = "factorypulse"

    sim_machines: int = 20
    sim_months: int = 12
    sim_rows: int = 10_000_000
    sim_defect_rate: float = Field(default=0.01, ge=0.0, le=0.5)
    sim_seed: int = 42

    downtime_cost_eur_per_hour: float = 2400.0

    @property
    def is_local(self) -> bool:
        return self.env == Env.LOCAL

    @property
    def catalog(self) -> str:
        """Unity Catalog name. Local Spark has no UC, so this is unused there."""
        return {
            Env.LOCAL: "spark_catalog",
            Env.AZURE_DEV: "factorypulse_dev",
            Env.AZURE_PROD: "factorypulse_prod",
        }[self.env]

    @property
    def _root(self) -> str:
        """Root URI of the lake for this environment."""
        if self.is_local:
            return f"s3a://{self.storage_bucket}"
        return f"abfss://{self.adls_container}@{self.adls_account}.dfs.core.windows.net"

    def landing_path(self, dataset: str) -> str:
        """Where ADF (or the simulator) drops raw files before Bronze reads them."""
        return f"{self._root}/landing/{dataset}"

    def bronze_path(self, table: str) -> str:
        return f"{self._root}/bronze/{table}"

    def silver_path(self, table: str) -> str:
        return f"{self._root}/silver/{table}"

    def gold_path(self, table: str) -> str:
        return f"{self._root}/gold/{table}"

    def quarantine_path(self, table: str) -> str:
        return f"{self._root}/quarantine/{table}"

    @property
    def ops_path(self) -> str:
        return f"{self._root}/ops/pipeline_runs"

    @property
    def jdbc_url(self) -> str:
        return f"jdbc:postgresql://{self.postgres_host}:{self.postgres_port}" f"/{self.postgres_db}"

    @property
    def jdbc_properties(self) -> dict[str, str]:
        return {
            "user": self.postgres_user,
            "password": self.postgres_password,
            "driver": "org.postgresql.Driver",
        }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Settings are read once per process."""
    return Settings()


settings = get_settings()
