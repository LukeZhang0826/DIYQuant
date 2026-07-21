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
    max_baseline_age_hours: float = 120.0


class ExecutionConfig(BaseModel):
    broker: str
    ledger_path: str
    sim_db_path: str = "data/sim_broker.sqlite"
    starting_cash: float = 100_000.0


class SentimentConfig(BaseModel):
    enabled: bool
    lookback_hours: int
    half_life_hours: float
    gate_threshold: float
    sources: list[str]


class AlertsConfig(BaseModel):
    enabled: bool = True
    timeout_seconds: float = 10.0


class Settings(BaseModel):
    universe: dict
    data: DataConfig
    strategy: StrategyConfig
    backtest: BacktestConfig
    execution: ExecutionConfig
    sentiment: SentimentConfig
    risk: RiskConfig
    alerts: AlertsConfig = AlertsConfig()


@lru_cache
def get_secrets() -> Secrets:
    return Secrets()


@lru_cache
def get_settings() -> Settings:
    with open(PROJECT_ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return Settings(**yaml.safe_load(f))
