"""Central configuration: secrets from .env, parameters from config/settings.yaml."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Secrets(BaseSettings):
    """Loaded from .env / environment. Never hardcode these."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    discord_webhook_url: str = ""
    anthropic_api_key: str = ""


class StrategyConfig(BaseModel):
    name: str
    params: dict


class DataConfig(BaseModel):
    provider: str
    store_path: str
    start: str


class BacktestConfig(BaseModel):
    cost_bps: float
    slippage_bps: float


class RiskConfig(BaseModel):
    max_daily_drawdown_pct: float
    max_position_pct: float


class Settings(BaseModel):
    universe: dict
    data: DataConfig
    strategy: StrategyConfig
    backtest: BacktestConfig
    risk: RiskConfig


@lru_cache
def get_secrets() -> Secrets:
    return Secrets()


@lru_cache
def get_settings() -> Settings:
    with open(PROJECT_ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return Settings(**yaml.safe_load(f))
