"""
Central config. Loads everything from .env — nothing hardcoded, nothing
guessed. If a required key is missing, we fail loudly at startup instead
of silently trading with a broken config.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name, default=None, required=False, cast=str):
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required env var: {name}. Check your .env file.")
    if val is None:
        return None
    try:
        return cast(val)
    except (ValueError, TypeError):
        raise RuntimeError(f"Env var {name}='{val}' could not be parsed as {cast.__name__}")


def _get_bool(name, default="true"):
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "on")


def _get_any(names, default=None, required=False, cast=str):
    if not isinstance(names, (list, tuple)):
        names = (names,)
    for name in names:
        val = os.getenv(name, None)
        if val is not None and str(val).strip() != "":
            return _get(name, default=default, required=False, cast=cast)
    if required:
        raise RuntimeError(f"Missing required env var. Set one of: {', '.join(names)}")
    return _get(names[0], default=default, required=False, cast=cast)


class Config:
    # Binance
    BINANCE_API_KEY = _get_any(("BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_KEY", "BINANCE_API_KEY"), required=True)
    BINANCE_API_SECRET = _get_any(("BINANCE_TESTNET_API_SECRET", "BINANCE_TESTNET_SECRET", "BINANCE_API_SECRET"), required=True)
    USE_FUTURES = _get_bool("BINANCE_USE_FUTURES", "true")
    USE_SPOT = _get_bool("BINANCE_USE_SPOT", "true")

    SPOT_BASE_URL = "https://testnet.binance.vision"
    FUTURES_BASE_URL = "https://testnet.binancefuture.com"

    # Telegram
    TELEGRAM_BOT_TOKEN = _get_any(("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"), required=False)
    TELEGRAM_CHAT_ID = _get_any(("TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID"), required=False)

    # AI
    GROQ_API_KEY = _get("GROQ_API_KEY", required=False)
    GROQ_MODEL = _get("GROQ_MODEL", default="llama-3.3-70b-versatile")
    ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY", required=False)
    ANTHROPIC_MODEL = _get("ANTHROPIC_MODEL", default="claude-haiku-4-5-20251001")

    # GitHub
    GITHUB_TOKEN = _get("GITHUB_TOKEN", required=False)
    GITHUB_REPO_URL = _get("GITHUB_REPO_URL", required=False)
    GITHUB_BRANCH = _get("GITHUB_BRANCH", default="main")

    # Risk
    RISK_PER_TRADE_PCT = _get("RISK_PER_TRADE_PCT", default="1.0", cast=float)
    MIN_RISK_REWARD_RATIO = _get("MIN_RISK_REWARD_RATIO", default="1.25", cast=float)
    DAILY_LOSS_LIMIT_PCT = _get("DAILY_LOSS_LIMIT_PCT", default="5.0", cast=float)
    MAX_CONCURRENT_TRADES = _get("MAX_CONCURRENT_TRADES", default="3", cast=int)
    MAX_TRADES_PER_DAY = _get("MAX_TRADES_PER_DAY", default="40", cast=int)
    MAX_HOLD_MINUTES = _get("MAX_HOLD_MINUTES", default="45", cast=int)

    # Strategy / scanner
    TOP_GAINERS_COUNT = _get("TOP_GAINERS_COUNT", default="15", cast=int)
    MIN_24H_QUOTE_VOLUME_USDT = _get("MIN_24H_QUOTE_VOLUME_USDT", default="5000000", cast=float)
    SCAN_INTERVAL_SECONDS = _get("SCAN_INTERVAL_SECONDS", default="30", cast=int)
    KLINE_INTERVAL = _get("KLINE_INTERVAL", default="5m")

    # Dashboard
    DASHBOARD_PORT = _get("DASHBOARD_PORT", default="5000", cast=int)

    # Symbols to exclude from scanning even if they show up as "top gainers"
    # (leveraged tokens move on rebalancing, not real momentum -> traps for scalpers)
    EXCLUDE_SUBSTRINGS = ("UP", "DOWN", "BULL", "BEAR")


cfg = Config()
