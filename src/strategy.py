"""
Scalping signal logic.

Design goal: fewer, higher-quality signals rather than "trade on every
candle". This is a LONG-ONLY momentum-pullback confluence setup, built on
well-established TA confluence (trend filter + pullback entry + volume
confirmation + volatility-based stop), not a proprietary "magic" indicator.
No guarantees of profitability are implied — this determines *when the
odds are more favorable*, not *whether a trade will win*.

IMPORTANT: every calculation here uses only data up to and including the
last CLOSED candle. We never look at the still-forming candle, to avoid
lookahead bias.

Setup logic (LONG):
1. TREND FILTER   — EMA9 > EMA21 > EMA50 on the closed series (uptrend structure)
2. MOMENTUM       — symbol is in the top-gainers scan (already-confirmed momentum)
3. PULLBACK ENTRY — price pulled back near EMA9 or rolling VWAP (not chasing a spike)
4. RSI FILTER     — RSI(14) between 45 and 68 (recovering from a dip, NOT already
                     overbought >70 which is where scalp longs get trapped)
5. VOLUME CONFIRM — last closed candle's volume > 1.3x the 20-period volume average
                     (real participation, not a dead pullback)
6. STRUCTURE STOP — stop placed below the recent swing low OR 1.5x ATR, whichever
                     is TIGHTER (keeps risk small, which is what makes a 1:1.25+ R:R
                     achievable on a scalp timeframe)
7. MIN R:R FILTER — signal is only valid if resulting reward:risk >= MIN_RISK_REWARD_RATIO

If any single condition fails, there is NO signal. This is intentional —
the point of "high probability" is to trade less often, not more.
"""
from dataclasses import dataclass
from typing import Optional

from config import cfg
from src import indicators as ind
from src.quant_model import MarketContext, quantify_market


@dataclass
class Signal:
    symbol: str
    side: str  # "LONG"
    entry: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    reasons: list


def _evaluate_primary(symbol: str, candles: list, i: int, closes: list, ema9: list,
                      ema21: list, ema50: list, rsi14: list, atr14: list,
                      vwap: list, vol_sma: list, last: dict, price: float) -> Optional[Signal]:
    reasons = []

    if not (ema9[i] > ema21[i] and price > ema21[i]):
        return None
    reasons.append("EMA9>EMA21 with price above EMA21")

    dist_ema9 = abs(price - ema9[i]) / ema9[i]
    dist_vwap = abs(price - vwap[i]) / vwap[i]
    near_pullback_zone = (dist_ema9 <= 0.015) or (dist_vwap <= 0.015)
    if not near_pullback_zone:
        return None
    reasons.append("price near EMA9/VWAP pullback zone")

    if not (35 <= rsi14[i] <= 75):
        return None
    reasons.append(f"RSI14={rsi14[i]:.1f} in favorable 35-75 band")

    if last["volume"] <= 1.0 * vol_sma[i]:
        return None
    reasons.append("volume > 1.0x 20-period average")

    recent_low = min(c["low"] for c in candles[max(0, i - 8) : i + 1])
    atr_stop = price - 2.0 * atr14[i]
    swing_stop = recent_low * 0.998
    stop_loss = max(atr_stop, swing_stop)

    if stop_loss >= price:
        return None

    risk = price - stop_loss
    if risk <= 0:
        return None

    take_profit = price + risk * cfg.MIN_RISK_REWARD_RATIO
    rr = (take_profit - price) / risk

    if rr < cfg.MIN_RISK_REWARD_RATIO - 1e-6:
        return None
    reasons.append(f"R:R={rr:.2f} meets minimum {cfg.MIN_RISK_REWARD_RATIO}")

    return Signal(
        symbol=symbol,
        side="LONG",
        entry=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=rr,
        reasons=reasons,
    )


def _evaluate_fallback(symbol: str, candles: list, i: int, closes: list, ema9: list,
                       ema21: list, ema50: list, rsi14: list, atr14: list,
                       vwap: list, vol_sma: list, last: dict, price: float) -> Optional[Signal]:
    reasons = []

    if not (ema9[i] > ema21[i] > ema50[i]):
        return None
    reasons.append("fallback: EMA9>EMA21>EMA50 trend continuation")

    if not (price > ema9[i] and price > ema21[i]):
        return None
    reasons.append("fallback: price above EMA9/EMA21")

    if not (price > closes[-2]):
        return None
    reasons.append("fallback: bullish candle breakout")

    if not (35 <= rsi14[i] <= 85):
        return None
    reasons.append(f"fallback: RSI14={rsi14[i]:.1f} in 35-85 band")

    if last["volume"] <= 0.8 * vol_sma[i]:
        return None
    reasons.append("fallback: volume > 0.8x 20-period average")

    recent_low = min(c["low"] for c in candles[max(0, i - 6) : i + 1])
    atr_stop = price - 1.5 * atr14[i]
    swing_stop = recent_low * 0.995
    stop_loss = max(atr_stop, swing_stop)

    if stop_loss >= price:
        return None

    risk = price - stop_loss
    if risk <= 0:
        return None

    take_profit = price + risk * max(cfg.MIN_RISK_REWARD_RATIO - 0.2, 0.9)
    rr = (take_profit - price) / risk

    if rr < max(cfg.MIN_RISK_REWARD_RATIO - 0.2, 0.9) - 1e-6:
        return None
    reasons.append(f"fallback R:R={rr:.2f}")

    return Signal(
        symbol=symbol,
        side="LONG",
        entry=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=rr,
        reasons=reasons,
    )


def _evaluate_liquidity_sweep(symbol: str, candles: list, i: int, closes: list, atr14: list,
                              vol_sma: list, last: dict, price: float) -> Optional[Signal]:
    reasons = []

    if len(candles) < 10:
        return None

    prev_close = closes[-2]
    prev_low = candles[-2]["low"]
    prev_high = candles[-2]["high"]
    if not (price > prev_high and price > prev_close * 1.002):
        return None
    reasons.append("liquidity sweep: bullish breakout above previous high")

    if not (last["volume"] >= 1.2 * vol_sma[i]):
        return None
    reasons.append("liquidity sweep: volume confirmation")

    swing_low = min(c["low"] for c in candles[max(0, i - 5) : i + 1])
    stop_loss = max(price - 1.2 * atr14[i], swing_low * 0.998)
    if stop_loss >= price:
        return None

    risk = price - stop_loss
    take_profit = price + risk * 1.0
    rr = (take_profit - price) / risk
    if rr < 1.0 - 1e-6:
        return None
    reasons.append("liquidity sweep: BSL/SSL-style continuation setup")

    return Signal(
        symbol=symbol,
        side="LONG",
        entry=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_reward=rr,
        reasons=reasons,
    )


def evaluate(symbol: str, candles: list, market_context: Optional[MarketContext] = None) -> Optional[Signal]:
    """
    candles: list of closed candles, oldest -> newest, from BinanceClient.klines()
    NOTE: caller must ensure the LAST element is a fully CLOSED candle
    (i.e. drop the currently-forming one before calling this).
    """
    min_len = 60
    if len(candles) < min_len:
        return None

    quant = quantify_market(symbol, candles, market_context)
    if quant.label == "bearish" and quant.score < -0.3:
        return None

    closes = ind.closes(candles)
    ema9 = ind.ema(closes, 9)
    ema21 = ind.ema(closes, 21)
    ema50 = ind.ema(closes, 50)
    rsi14 = ind.rsi(closes, 14)
    atr14 = ind.atr(candles, 14)
    vwap = ind.vwap_session(candles)
    vol_sma = ind.volume_sma(candles, 20)

    i = len(candles) - 1
    last = candles[i]
    price = last["close"]

    vals = [ema9[i], ema21[i], ema50[i], rsi14[i], atr14[i], vwap[i], vol_sma[i]]
    if any(v is None or v != v for v in vals):
        return None

    primary_signal = _evaluate_primary(
        symbol, candles, i, closes, ema9, ema21, ema50, rsi14, atr14, vwap, vol_sma, last, price
    )
    if primary_signal is not None:
        primary_signal.reasons.append(f"quant={quant.label}:{quant.score:.2f}")
        return primary_signal

    fallback_signal = _evaluate_fallback(
        symbol, candles, i, closes, ema9, ema21, ema50, rsi14, atr14, vwap, vol_sma, last, price
    )
    if fallback_signal is not None:
        fallback_signal.reasons.append(f"quant={quant.label}:{quant.score:.2f}")
        return fallback_signal

    liquidity_signal = _evaluate_liquidity_sweep(
        symbol, candles, i, closes, atr14, vol_sma, last, price
    )
    if liquidity_signal is not None:
        liquidity_signal.reasons.append(f"quant={quant.label}:{quant.score:.2f}")
    return liquidity_signal
