"""
Main loop. This is the only place that ties strategy + risk + execution
together. Sequence every cycle:

  1. Scan top gainers (spot and/or futures per config)
  2. For each candidate: pull closed klines, run strategy.evaluate()
  3. If signal found AND risk_manager allows a new trade:
       - size position
       - execute bracket order (entry + SL + TP)
       - log to journal, notify Telegram, ask AI for a short explanation
  4. Check all currently-open positions against SL/TP fill status and
     MAX_HOLD_MINUTES (time-based exit — core to scalping: don't let a
     trade linger past its intended horizon)
  5. Write status.json for the dashboard
  6. Sleep SCAN_INTERVAL_SECONDS, repeat

Run: python -m src.main   (from project root)
"""
import sys
import os
import time
import json
import datetime
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import cfg
from src.binance_client import BinanceClient, BinanceAPIError
from src import market_scanner, strategy, risk_manager as rm_module
from src.quant_model import MarketContext
from src import executor, journal, telegram_bot, ai_reasoner

STATUS_PATH = os.path.join(os.path.dirname(__file__), "..", "journal", "status.json")

risk_manager = rm_module.RiskManager()

# open_trades: symbol -> trade record dict (in-memory; also mirrored to journal)
open_trades = {}


def write_status(state, candidates=None):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    status = {
        "state": state,
        "last_scan": datetime.datetime.utcnow().isoformat() + "Z",
        "open_positions": [
            {
                "symbol": sym,
                "entry": t["entry"],
                "stop_loss": t["stop_loss"],
                "take_profit": t["take_profit"],
                "qty": t["qty"],
                "market": t["market"],
            }
            for sym, t in open_trades.items()
        ],
        "candidates": candidates or [],
    }
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f)


def get_closed_klines(client, symbol, interval, limit=100):
    """Fetch klines and drop the last (still-forming) candle to avoid lookahead bias."""
    candles = client.klines(symbol, interval, limit=limit)
    if len(candles) < 2:
        return []
    return candles[:-1]


def scan_market(client, market_type):
    candidates = market_scanner.get_top_gainers(client)
    signals = []
    for c in candidates:
        symbol = c["symbol"]
        if symbol in open_trades:
            continue
        try:
            candles = get_closed_klines(client, symbol, cfg.KLINE_INTERVAL, limit=100)
            if not candles:
                continue
            ticker = client.ticker_24hr()
            ticker_map = {item["symbol"]: item for item in ticker if isinstance(item, dict) and "symbol" in item}
            t = ticker_map.get(symbol, {})
            funding_payload = client.funding_rate(symbol) if market_type == "futures" else {"lastFundingRate": "0"}
            oi_payload = client.open_interest(symbol) if market_type == "futures" else {"openInterest": 0.0}
            funding_rate = float(funding_payload.get("lastFundingRate", funding_payload.get("fundingRate", 0.0)) or 0.0)
            open_interest = float(oi_payload.get("openInterest", 0.0) or 0.0)
            context = MarketContext(
                symbol=symbol,
                price=float(t.get("lastPrice", 0.0) or 0.0),
                change_24h=float(t.get("priceChangePercent", 0.0) or 0.0) / 100.0,
                volume_ratio=float(t.get("quoteVolume", 0.0) or 0.0) / max(1.0, float(t.get("volume", 0.0) or 0.0)),
                funding_rate=funding_rate,
                open_interest_ratio=max(1e-6, open_interest / max(1.0, open_interest)),
                momentum=float(t.get("priceChangePercent", 0.0) or 0.0) / 100.0,
                volatility=max(0.0001, float(t.get("priceChangePercent", 0.0) or 0.0) / 1000.0),
            )
            sig = strategy.evaluate(symbol, candles, market_context=context)
            if sig:
                signals.append((market_type, sig))
        except BinanceAPIError as e:
            print(f"[scan] {symbol} ({market_type}) API error: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"[scan] {symbol} ({market_type}) unexpected error: {e}")
    return candidates, signals


def try_execute_signal(client, market_type, signal):
    balance = client.available_balance_usdt()
    can_trade, reason = risk_manager.can_open_new_trade(balance)
    if not can_trade:
        print(f"[risk] skip {signal.symbol}: {reason}")
        return

    qty = risk_manager.position_size(balance, signal.entry, signal.stop_loss)
    if qty <= 0:
        print(f"[risk] skip {signal.symbol}: computed qty <= 0")
        return

    try:
        if market_type == "futures":
            result = executor.execute_futures_long(client, signal.symbol, qty, signal)
        else:
            result = executor.execute_spot_long(client, signal.symbol, qty, signal)
    except (BinanceAPIError, executor.ExecutionError) as e:
        print(f"[exec] FAILED {signal.symbol}: {e}")
        journal.log_event("execution_failed", {"symbol": signal.symbol, "error": str(e)})
        return

    trade_record = {
        "symbol": signal.symbol,
        "market": market_type,
        "entry": signal.entry,
        "stop_loss": result["stop_price"],
        "take_profit": result["tp_price"],
        "qty": result["qty"],
        "risk_reward": signal.risk_reward,
        "opened_at": time.time(),
        "sl_order_id": result.get("sl_order", {}).get("orderId"),
        "tp_order_id": result.get("tp_order", {}).get("orderId"),
        "oco_order_id": result.get("oco_order", {}).get("orderListId") if market_type == "spot" else None,
    }
    open_trades[signal.symbol] = trade_record
    risk_manager.register_trade_opened()
    journal.log_event("trade_opened", {k: v for k, v in trade_record.items() if k != "opened_at"})

    explanation = ai_reasoner.explain_signal(signal)
    telegram_bot.send_message(
        f"🟢 OPEN {signal.symbol} ({market_type})\n"
        f"Entry: {signal.entry:.6f} | SL: {result['stop_price']:.6f} | TP: {result['tp_price']:.6f}\n"
        f"R:R {signal.risk_reward:.2f} | Qty {result['qty']}\n\n{explanation}"
    )
    print(f"[exec] opened {signal.symbol} qty={qty}")


def monitor_open_trades(clients_by_market):
    """
    Checks time-based exit (MAX_HOLD_MINUTES). SL/TP fills are handled by the
    exchange itself (bracket orders already placed); we detect a close by
    checking whether the position/order has actually closed on the exchange,
    which for futures means checking open_positions(), and for spot means
    checking whether the OCO order is still open. This function focuses on
    the scalping-specific time exit which the exchange can't enforce itself.
    """
    now = time.time()
    to_remove = []
    for symbol, trade in list(open_trades.items()):
        age_minutes = (now - trade["opened_at"]) / 60
        client = clients_by_market[trade["market"]]

        still_open = True
        exit_price = None
        won = None

        if trade["market"] == "futures":
            positions = client.open_positions()
            still_open = any(p["symbol"] == symbol for p in positions)
            if not still_open:
                # Determine which bracket order actually filled to get real exit price.
                try:
                    tp_status = client.get_order(symbol, trade["tp_order_id"]) if trade.get("tp_order_id") else None
                    sl_status = client.get_order(symbol, trade["sl_order_id"]) if trade.get("sl_order_id") else None
                    if tp_status and tp_status.get("status") == "FILLED":
                        exit_price = float(tp_status.get("avgPrice") or trade["take_profit"])
                        won = True
                    elif sl_status and sl_status.get("status") == "FILLED":
                        exit_price = float(sl_status.get("avgPrice") or trade["stop_loss"])
                        won = False
                except BinanceAPIError as e:
                    print(f"[monitor] could not fetch fill status for {symbol}: {e}")
        else:
            # Spot: check OCO leg order status.
            if trade.get("oco_order_id"):
                try:
                    tp_status = client.get_order(symbol, trade["tp_order_id"]) if trade.get("tp_order_id") else None
                    if tp_status and tp_status.get("status") == "FILLED":
                        exit_price = float(tp_status.get("price") or trade["take_profit"])
                        won = True
                        still_open = False
                except BinanceAPIError:
                    pass
            else:
                still_open = False  # no OCO id recorded, can't track further — assume closed to avoid a stuck entry

        if not still_open:
            pnl = None
            if exit_price is not None:
                pnl = round((exit_price - trade["entry"]) * trade["qty"], 4)
            journal.log_event(
                "trade_closed",
                {"symbol": symbol, "reason": "sl_or_tp_hit", "pnl": pnl, "won": won, "exit_price": exit_price},
            )
            telegram_bot.send_message(
                f"{'✅' if won else '❌' if won is False else 'ℹ️'} CLOSED {symbol} — "
                f"{'TP' if won else 'SL' if won is False else 'unknown'} hit. PnL: {pnl if pnl is not None else 'n/a'}"
            )
            risk_manager.register_trade_closed(realized_pnl=pnl or 0.0)
            to_remove.append(symbol)
            continue

        if age_minutes >= cfg.MAX_HOLD_MINUTES:
            try:
                if trade["market"] == "futures":
                    client.place_market_order(symbol, side="SELL", quantity=trade["qty"], reduce_only=True)
                else:
                    client.place_market_order(symbol, side="SELL", quantity=trade["qty"])
                journal.log_event("trade_closed", {"symbol": symbol, "reason": "max_hold_time", "pnl": None})
                telegram_bot.send_message(f"⏱ CLOSED {symbol} — max hold time ({cfg.MAX_HOLD_MINUTES}m) reached.")
                risk_manager.register_trade_closed(realized_pnl=0.0)
                to_remove.append(symbol)
            except BinanceAPIError as e:
                print(f"[monitor] failed to time-exit {symbol}: {e}")

    for s in to_remove:
        open_trades.pop(s, None)


def main_loop():
    clients_by_market = {}
    if cfg.USE_SPOT:
        clients_by_market["spot"] = BinanceClient("spot")
    if cfg.USE_FUTURES:
        clients_by_market["futures"] = BinanceClient("futures")

    if not clients_by_market:
        raise RuntimeError("Both BINANCE_USE_SPOT and BINANCE_USE_FUTURES are false — nothing to trade.")

    telegram_bot.send_message("🚀 Scalper bot started (TESTNET). Markets: " + ", ".join(clients_by_market) + "\n\nDashboard access: http://localhost:5000")
    print("Bot started. Markets:", list(clients_by_market))

    while True:
        try:
            all_candidates = []
            for market_type, client in clients_by_market.items():
                candidates, signals = scan_market(client, market_type)
                all_candidates.extend([{**c, "market": market_type} for c in candidates])
                for m_type, sig in signals:
                    try_execute_signal(client, m_type, sig)

            monitor_open_trades(clients_by_market)
            write_status("running", candidates=all_candidates)

        except Exception as e:  # noqa: BLE001 - loop must survive unexpected errors
            print("[main] loop error:", e)
            traceback.print_exc()
            journal.log_event("loop_error", {"error": str(e)})
            write_status("error")

        time.sleep(cfg.SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()
