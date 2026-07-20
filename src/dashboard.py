"""
Lightweight real-time dashboard. Runs as its own Flask process so a
dashboard bug can never crash the trading loop, and vice versa. The two
processes talk through the journal file + a small status.json file that
main.py writes to every scan cycle.

Run: python -m src.dashboard   (from project root, with .env loaded)
In Codespaces: forward DASHBOARD_PORT, open in browser.
"""
import json
import os
from flask import Flask, render_template, jsonify

from src.quant_model import MarketContext, quantify_market

from config import cfg
from src import journal
from src.binance_client import BinanceClient

STATUS_PATH = os.path.join(os.path.dirname(__file__), "..", "journal", "status.json")

app = Flask(__name__, template_folder="../templates")


def read_status():
    if not os.path.exists(STATUS_PATH):
        return {"state": "starting", "last_scan": None, "open_positions": [], "candidates": []}
    with open(STATUS_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"state": "unknown"}


@app.route("/")
def index():
    return render_template("dashboard.html", refresh_seconds=5)


@app.route("/api/status")
def api_status():
    status = read_status()
    stats = journal.summary_stats()
    recent = journal.read_all()[-30:][::-1]
    return jsonify({"status": status, "stats": stats, "recent_events": recent})


@app.route("/api/market")
def api_market():
    try:
        spot_client = BinanceClient("spot")
        futures_client = BinanceClient("futures")
        spot_ticker = spot_client.ticker_24hr()[:8]
        futures_ticker = futures_client.ticker_24hr()[:8]
        quant_items = []
        for client, label in ((spot_client, "spot"), (futures_client, "futures")):
            for item in client.ticker_24hr()[:8]:
                if not isinstance(item, dict):
                    continue
                symbol = item.get("symbol")
                if not symbol:
                    continue
                candles = client.klines(symbol, "5m", limit=80)[:-1]
                if len(candles) < 60:
                    continue
                funding_payload = client.funding_rate(symbol) if label == "futures" else {"lastFundingRate": "0"}
                oi_payload = client.open_interest(symbol) if label == "futures" else {"openInterest": 0.0}
                funding_rate = float(funding_payload.get("lastFundingRate", funding_payload.get("fundingRate", 0.0)) or 0.0)
                open_interest = float(oi_payload.get("openInterest", 0.0) or 0.0)
                context = MarketContext(
                    symbol=symbol,
                    price=float(item.get("lastPrice", 0.0) or 0.0),
                    change_24h=float(item.get("priceChangePercent", 0.0) or 0.0) / 100.0,
                    volume_ratio=float(item.get("quoteVolume", 0.0) or 0.0) / max(1.0, float(item.get("volume", 0.0) or 0.0)),
                    funding_rate=funding_rate,
                    open_interest_ratio=max(1e-6, open_interest / max(1.0, open_interest)),
                    momentum=float(item.get("priceChangePercent", 0.0) or 0.0) / 100.0,
                    volatility=max(0.0001, float(item.get("priceChangePercent", 0.0) or 0.0) / 1000.0),
                )
                quant = quantify_market(symbol, candles, context)
                quant_items.append({"symbol": symbol, "market": label, "quant": {"label": quant.label, "score": round(quant.score, 3), "confidence": round(quant.confidence, 3), "sentiment": round(quant.sentiment_score, 3), "fundamental": round(quant.fundamental_score, 3), "reasons": quant.reasons}})
        return jsonify({
            "spot": spot_ticker,
            "futures": futures_ticker,
            "quant": quant_items,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def run():
    app.run(host="0.0.0.0", port=cfg.DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    run()
