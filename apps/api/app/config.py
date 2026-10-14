from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://tapedeck:tapedeck@localhost:5432/tapedeck"
    redis_url: str = "redis://localhost:6379/0"

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_feed: str = "sip"

    cors_origins: list[str] = ["http://localhost:3000"]

    auth_enabled: bool = False
    admin_username: str = "admin"
    admin_password: str = "changeme"
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 720

    starting_cash: float = 100_000.0
    risk_free_rate: float = 0.04
    stock_slippage_bps: float = 1.0
    option_slippage_pct: float = 0.01
    stock_commission_per_share: float = 0.0
    option_commission_per_contract: float = 0.65


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
