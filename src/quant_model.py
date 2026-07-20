from dataclasses import dataclass
from typing import Optional

from src import indicators as ind


@dataclass
class MarketContext:
    symbol: str
    price: float
    change_24h: float
    volume_ratio: float
    funding_rate: float
    open_interest_ratio: float
    momentum: float
    volatility: float


@dataclass
class QuantSignal:
    symbol: str
    label: str
    score: float
    confidence: float
    reasons: list
    sentiment_score: float = 0.0
    fundamental_score: float = 0.0


def _safe_score(value: float, positive: bool = True) -> float:
    if value is None:
        return 0.0
    value = max(-1.0, min(1.0, value))
    return value if positive else -value


def quantify_market(symbol: str, candles: list, context: Optional[MarketContext] = None) -> QuantSignal:
    if not candles:
        return QuantSignal(symbol=symbol, label="neutral", score=0.0, confidence=0.0, reasons=["no candle data"])

    closes = ind.closes(candles)
    ema9 = ind.ema(closes, 9)
    ema21 = ind.ema(closes, 21)
    rsi14 = ind.rsi(closes, 14)
    vwap = ind.vwap_session(candles)
    vol_sma = ind.volume_sma(candles, 20)
    last_idx = len(candles) - 1

    if context is None:
        context = MarketContext(
            symbol=symbol,
            price=float(closes[-1]),
            change_24h=0.0,
            volume_ratio=1.0,
            funding_rate=0.0,
            open_interest_ratio=1.0,
            momentum=0.0,
            volatility=0.01,
        )

    score = 0.0
    sentiment_score = 0.0
    fundamental_score = 0.0
    reasons = []

    if not (ema9[last_idx] != ema9[last_idx] or ema21[last_idx] != ema21[last_idx]):
        if ema9[last_idx] > ema21[last_idx]:
            score += 0.25
            sentiment_score += 0.25
            reasons.append("EMA9>EMA21")
        elif ema9[last_idx] < ema21[last_idx]:
            score -= 0.25
            sentiment_score -= 0.25
            reasons.append("EMA9<EMA21")

    if not (rsi14[last_idx] != rsi14[last_idx]):
        if 50 <= rsi14[last_idx] <= 70:
            score += 0.15
            sentiment_score += 0.15
            reasons.append("RSI in healthy bullish zone")
        elif rsi14[last_idx] > 70:
            score -= 0.1
            sentiment_score -= 0.1
            reasons.append("RSI overbought")
        elif rsi14[last_idx] < 30:
            score -= 0.1
            sentiment_score -= 0.1
            reasons.append("RSI oversold")

    if context.change_24h > 0.5:
        score += 0.2
        sentiment_score += 0.2
        reasons.append("positive 24h move")
    elif context.change_24h < -0.5:
        score -= 0.2
        sentiment_score -= 0.2
        reasons.append("negative 24h move")

    if context.volume_ratio > 1.2:
        score += 0.15
        sentiment_score += 0.15
        reasons.append("volume expansion")
    elif context.volume_ratio < 0.8:
        score -= 0.15
        sentiment_score -= 0.15
        reasons.append("volume contraction")

    if context.funding_rate > 0.0001:
        score += 0.05
        fundamental_score += 0.05
        reasons.append("positive funding")
    elif context.funding_rate < -0.0001:
        score -= 0.05
        fundamental_score -= 0.05
        reasons.append("negative funding")

    if context.open_interest_ratio > 1.1:
        score += 0.05
        fundamental_score += 0.05
        reasons.append("OI rising")
    elif context.open_interest_ratio < 0.9:
        score -= 0.05
        fundamental_score -= 0.05
        reasons.append("OI falling")

    if context.momentum > 0.3:
        score += 0.1
        sentiment_score += 0.1
        reasons.append("momentum positive")
    elif context.momentum < -0.3:
        score -= 0.1
        sentiment_score -= 0.1
        reasons.append("momentum negative")

    if context.volatility > 0.02:
        score += 0.05
        sentiment_score += 0.05
        reasons.append("volatility supports breakout")

    if abs(score) > 0.5:
        label = "bullish" if score > 0 else "bearish"
    else:
        label = "neutral"

    confidence = min(0.99, 0.55 + min(0.35, abs(score) / 2.0))
    return QuantSignal(symbol=symbol, label=label, score=max(-1.0, min(1.0, score)), confidence=confidence, reasons=reasons, sentiment_score=max(-1.0, min(1.0, sentiment_score)), fundamental_score=max(-1.0, min(1.0, fundamental_score)))
