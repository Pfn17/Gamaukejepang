"""
Turns a validated Signal + position size into real (testnet) orders.
Handles quantity/price rounding to exchange filters — a very common
source of "silent" order rejections if skipped.
"""
import time
from src.binance_client import BinanceAPIError


class ExecutionError(Exception):
    pass


def execute_futures_long(client, symbol, qty, entry_signal, leverage=3):
    """
    Opens a market long, then places STOP_MARKET (SL) and TAKE_PROFIT_MARKET
    (TP) as separate reduce-only orders (Binance USDT-M futures has no native
    OCO, so both are placed and whichever fills first, the other is cancelled
    by the position-monitor loop in main.py).
    """
    filters = client.get_symbol_filters(symbol)
    qty = client.round_qty(symbol, qty)
    if qty < float(filters["min_qty"]):
        raise ExecutionError(f"{symbol}: sized qty {qty} below exchange min_qty {filters['min_qty']}")

    notional = qty * entry_signal.entry
    if notional < float(filters["min_notional"]):
        raise ExecutionError(
            f"{symbol}: notional {notional:.2f} below exchange min_notional {filters['min_notional']}"
        )

    try:
        client.set_leverage(symbol, leverage)
    except BinanceAPIError:
        pass  # leverage already set or symbol doesn't support change right now — not fatal

    entry_order = client.place_market_order(symbol, side="BUY", quantity=qty)
    time.sleep(0.5)  # let the fill register before placing exits

    stop_price = client.round_price(symbol, entry_signal.stop_loss)
    tp_price = client.round_price(symbol, entry_signal.take_profit)

    sl_order = client.place_stop_market(symbol, side="SELL", quantity=qty, stop_price=stop_price)
    tp_order = client.place_take_profit_market(symbol, side="SELL", quantity=qty, stop_price=tp_price)

    return {
        "entry_order": entry_order,
        "sl_order": sl_order,
        "tp_order": tp_order,
        "qty": qty,
        "stop_price": stop_price,
        "tp_price": tp_price,
    }


def execute_spot_long(client, symbol, qty, entry_signal):
    """
    Buys spot, then places an OCO sell order bracketing TP/SL in one shot
    (spot testnet supports native OCO, unlike futures).
    """
    filters = client.get_symbol_filters(symbol)
    qty = client.round_qty(symbol, qty)
    if qty < float(filters["min_qty"]):
        raise ExecutionError(f"{symbol}: sized qty {qty} below exchange min_qty {filters['min_qty']}")

    notional = qty * entry_signal.entry
    if notional < float(filters["min_notional"]):
        raise ExecutionError(
            f"{symbol}: notional {notional:.2f} below exchange min_notional {filters['min_notional']}"
        )

    entry_order = client.place_market_order(symbol, side="BUY", quantity=qty)
    time.sleep(0.5)

    tp_price = client.round_price(symbol, entry_signal.take_profit)
    stop_price = client.round_price(symbol, entry_signal.stop_loss)
    # stop-limit trigger slightly below stop_price so the limit order actually fills in a fast drop
    stop_limit_price = client.round_price(symbol, entry_signal.stop_loss * 0.997)

    oco_order = client.place_oco_spot(
        symbol,
        side="SELL",
        quantity=qty,
        take_profit_price=tp_price,
        stop_price=stop_price,
        stop_limit_price=stop_limit_price,
    )

    return {
        "entry_order": entry_order,
        "oco_order": oco_order,
        "qty": qty,
        "stop_price": stop_price,
        "tp_price": tp_price,
    }
