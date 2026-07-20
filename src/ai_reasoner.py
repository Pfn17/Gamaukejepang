"""
AI reasoning/journaling layer. IMPORTANT scope: this is used to EXPLAIN and
JOURNAL trades in human-readable language (for your Telegram alerts + dashboard
notes) — it is NOT used to generate entry/exit signals. All trading decisions
come from strategy.py (deterministic, rule-based). This keeps the bot's core
logic auditable and reproducible; the AI layer is a narration/summary layer
on top of it, with Groq and Anthropic as fallbacks for each other so a rate
limit on one doesn't stop journaling.
"""
import time
import requests

from config import cfg

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def _call_groq(prompt: str, max_tokens=300, timeout=15) -> str:
    if not cfg.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    resp = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {cfg.GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": cfg.GROQ_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    if resp.status_code == 429:
        raise RateLimitError("groq rate limited")
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _call_anthropic(prompt: str, max_tokens=300, timeout=20) -> str:
    if not cfg.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": cfg.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": cfg.ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    if resp.status_code == 429:
        raise RateLimitError("anthropic rate limited")
    resp.raise_for_status()
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


class RateLimitError(Exception):
    pass


def ask(prompt: str, max_tokens=300) -> str:
    """
    Tries Groq first (fast + cheap), falls back to Anthropic on any error
    (rate limit, timeout, network issue, missing key). If both fail, returns
    a plain-text fallback string instead of raising — narration failing should
    NEVER block or crash the trading loop.
    """
    for attempt_fn, name in ((_call_groq, "groq"), (_call_anthropic, "anthropic")):
        try:
            return attempt_fn(prompt, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001 - deliberately broad, this path must never crash the bot
            last_err = f"{name} failed: {e}"
            time.sleep(0.5)
            continue
    return f"[AI reasoning unavailable — {last_err}]"


def explain_signal(signal) -> str:
    prompt = (
        "Ringkas alasan setup trading scalping berikut dalam 2-3 kalimat bahasa Indonesia "
        "santai tapi presisi, untuk notifikasi Telegram. Jangan menambah klaim yang tidak "
        f"ada di data.\n\nSymbol: {signal.symbol}\nEntry: {signal.entry}\n"
        f"Stop Loss: {signal.stop_loss}\nTake Profit: {signal.take_profit}\n"
        f"Risk:Reward: {signal.risk_reward:.2f}\nAlasan teknikal: {', '.join(signal.reasons)}"
    )
    return ask(prompt, max_tokens=200)


def journal_trade(trade_record: dict) -> str:
    prompt = (
        "Tulis catatan jurnal trading singkat (3-4 kalimat, bahasa Indonesia) untuk trade "
        "yang sudah closed berikut. Fokus pada fakta angka, bukan opini berlebihan.\n\n"
        f"{trade_record}"
    )
    return ask(prompt, max_tokens=250)
