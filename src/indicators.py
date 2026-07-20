"""
Indicators computed directly from raw kline arrays. No TA-Lib dependency
(avoids install headaches on Termux/Codespaces), and every formula here is
the textbook definition so there is nothing hidden or approximated.

All functions take a list of candle dicts (as returned by BinanceClient.klines)
ordered oldest -> newest, and return a list aligned to the same length
(with None for indices where the indicator isn't yet defined).
"""
import numpy as np


def closes(candles):
    return np.array([c["close"] for c in candles], dtype=float)


def highs(candles):
    return np.array([c["high"] for c in candles], dtype=float)


def lows(candles):
    return np.array([c["low"] for c in candles], dtype=float)


def volumes(candles):
    return np.array([c["volume"] for c in candles], dtype=float)


def ema(values, period):
    """Standard exponential moving average. Returns np.array, NaN before warm-up."""
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if len(values) < period:
        return out
    alpha = 2 / (period + 1)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = values[i] * alpha + out[i - 1] * (1 - alpha)
    return out


def rsi(values, period=14):
    """Wilder's RSI."""
    values = np.asarray(values, dtype=float)
    out = np.full_like(values, np.nan)
    if len(values) < period + 1:
        return out
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    out[period] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

    for i in range(period + 1, len(values)):
        gain = gains[i - 1]
        loss = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = np.inf if avg_loss == 0 else avg_gain / avg_loss
        out[i] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + rs))
    return out


def atr(candles, period=14):
    """Average True Range (Wilder smoothing) — used for stop-loss distance."""
    h = highs(candles)
    l = lows(candles)
    c = closes(candles)
    n = len(candles)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    tr = np.zeros(n)
    tr[0] = h[0] - l[0]
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    out[period] = tr[1 : period + 1].mean()
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def vwap_session(candles):
    """
    Rolling VWAP over the candle window provided (not anchored to exchange
    midnight — since we pull a fixed window of recent candles, this is a
    rolling VWAP, which is what matters for intraday scalping mean-reversion).
    """
    c = closes(candles)
    v = volumes(candles)
    typical = (highs(candles) + lows(candles) + c) / 3
    cum_pv = np.cumsum(typical * v)
    cum_v = np.cumsum(v)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(cum_v > 0, cum_pv / cum_v, np.nan)
    return out


def volume_sma(candles, period=20):
    v = volumes(candles)
    out = np.full(len(v), np.nan)
    if len(v) < period:
        return out
    for i in range(period - 1, len(v)):
        out[i] = v[i - period + 1 : i + 1].mean()
    return out
