from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cataloglab_url: str = ""
    cataloglab_api_key: str = ""
    cataloglab_batch_size: int = 50

    sku_store_url: str = ""
    sku_store_api_key: str = ""

    redis_url: str = "redis://localhost:6379/0"
    manifest_ttl_days: int = 30

    gs1_api_url: str = "https://gepir.gs1.org/index.php/search-by-gtin"
    gs1_api_key: str = ""
    open_food_facts_url: str = "https://world.openfoodfacts.org/api/v2"

    ucb_exploration_c: float = 1.0
    agent_batch_size: int = 3
    min_delta_threshold: float = 2.0
    max_iterations: int = 50

    artifact_dir: str = "./artifacts_local"
    arq_redis_url: str = "redis://localhost:6379/1"
    use_fake_redis: bool = False   # set USE_FAKE_REDIS=true for dev without a real Redis
    use_mock_sources: bool = False # set USE_MOCK_SOURCES=true for dev without network access

    @property
    def use_mock_scorer(self) -> bool:
        return not self.cataloglab_url

    @property
    def use_mock_sku_store(self) -> bool:
        return not self.sku_store_url

    @property
    def manifest_ttl_seconds(self) -> int:
        return self.manifest_ttl_days * 86400


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
