"""
Finds the current top-gaining USDT pairs, filtered for:
  - quote asset == USDT only (keeps R:R math simple and comparable)
  - minimum 24h quote volume (excludes illiquid pairs prone to slippage/spoofing)
  - excludes leveraged tokens (UP/DOWN/BULL/BEAR) — these move on rebalancing
    mechanics, not organic momentum, and are a classic scalper trap
  - excludes symbols with obviously broken/stale data (price or volume == 0)

This directly avoids survivorship bias in one specific sense relevant here:
we do NOT hardcode a fixed "watchlist" of coins that happened to perform well
historically. The scan is done fresh every cycle against live 24hr ticker
data, so delisted / dead / rug-pulled pairs simply fall out of the universe
naturally rather than being cherry-picked in hindsight.
"""
from config import cfg


def _is_excluded(symbol: str) -> bool:
    return any(tag in symbol for tag in cfg.EXCLUDE_SUBSTRINGS)


def get_top_gainers(client, top_n=None, min_quote_volume=None):
    top_n = top_n or cfg.TOP_GAINERS_COUNT
    min_quote_volume = min_quote_volume if min_quote_volume is not None else cfg.MIN_24H_QUOTE_VOLUME_USDT

    tickers = client.ticker_24hr()
    candidates = []
    for t in tickers:
        symbol = t.get("symbol", "")
        if not symbol.endswith("USDT"):
            continue
        if _is_excluded(symbol):
            continue
        try:
            last_price = float(t["lastPrice"])
            quote_volume = float(t["quoteVolume"])
            pct_change = float(t["priceChangePercent"])
        except (KeyError, ValueError, TypeError):
            continue
        if last_price <= 0 or quote_volume < min_quote_volume:
            continue
        candidates.append(
            {
                "symbol": symbol,
                "price_change_pct": pct_change,
                "quote_volume": quote_volume,
                "last_price": last_price,
            }
        )

    candidates.sort(key=lambda x: x["price_change_pct"], reverse=True)
    return candidates[:top_n]
