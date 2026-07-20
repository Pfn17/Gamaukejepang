"""
Raw Binance TESTNET REST client — spot + USDT-M futures.
Deliberately built on plain requests + HMAC signing instead of a wrapper
library, so every request/response is inspectable and there is no hidden
behavior. This talks ONLY to testnet hosts.
"""
import time
import hmac
import hashlib
import requests
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

from config import cfg


class BinanceAPIError(Exception):
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Binance API error [{status_code}]: {payload}")


class BinanceClient:
    """
    market: "spot" or "futures"
    """

    def __init__(self, market="spot"):
        assert market in ("spot", "futures")
        self.market = market
        self.base_url = cfg.SPOT_BASE_URL if market == "spot" else cfg.FUTURES_BASE_URL
        self.api_key = cfg.BINANCE_API_KEY
        self.api_secret = cfg.BINANCE_API_SECRET
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})
        self._symbol_filters_cache = {}

    # ---------- low level ----------

    def _sign(self, params: dict) -> str:
        query = urlencode(params, doseq=True)
        signature = hmac.new(
            self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return query + f"&signature={signature}"

    def _request(self, method, path, params=None, signed=False, timeout=10):
        params = dict(params or {})
        url = self.base_url + path
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params.setdefault("recvWindow", 5000)
            query = self._sign(params)
            full_url = f"{url}?{query}"
            resp = self.session.request(method, full_url, timeout=timeout)
        else:
            resp = self.session.request(method, url, params=params, timeout=timeout)

        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except ValueError:
                payload = resp.text
            raise BinanceAPIError(resp.status_code, payload)
        return resp.json()

    # ---------- public market data ----------

    def ticker_24hr(self):
        """All symbols, 24h stats. Public endpoint, no signing needed."""
        path = "/api/v3/ticker/24hr" if self.market == "spot" else "/fapi/v1/ticker/24hr"
        return self._request("GET", path)

    def klines(self, symbol, interval, limit=100):
        path = "/api/v3/klines" if self.market == "spot" else "/fapi/v1/klines"
        raw = self._request(
            "GET", path, params={"symbol": symbol, "interval": interval, "limit": limit}
        )
        # Each row: [open_time, open, high, low, close, volume, close_time, quote_vol, trades, ...]
        candles = []
        for row in raw:
            candles.append(
                {
                    "open_time": row[0],
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "close_time": row[6],
                }
            )
        return candles

    def exchange_info(self, symbol=None):
        path = "/api/v3/exchangeInfo" if self.market == "spot" else "/fapi/v1/exchangeInfo"
        params = {"symbol": symbol} if symbol else {}
        return self._request("GET", path, params=params)

    def funding_rate(self, symbol):
        if self.market != "futures":
            return {"lastFundingRate": "0", "fundingRate": "0"}
        payload = self._request("GET", "/fapi/v1/premiumIndex", params={"symbol": symbol})
        return payload

    def open_interest(self, symbol):
        if self.market != "futures":
            return {"openInterest": 0.0}
        return self._request("GET", "/fapi/v1/openInterest", params={"symbol": symbol})

    def get_symbol_filters(self, symbol):
        """Cached LOT_SIZE / PRICE_FILTER / MIN_NOTIONAL for correct order rounding."""
        if symbol in self._symbol_filters_cache:
            return self._symbol_filters_cache[symbol]
        info = self.exchange_info(symbol=symbol)
        sym_info = info["symbols"][0]
        filters = {f["filterType"]: f for f in sym_info["filters"]}
        result = {
            "step_size": Decimal(filters.get("LOT_SIZE", filters.get("MARKET_LOT_SIZE"))["stepSize"]),
            "tick_size": Decimal(filters["PRICE_FILTER"]["tickSize"]),
            "min_qty": Decimal(filters.get("LOT_SIZE", filters.get("MARKET_LOT_SIZE"))["minQty"]),
            "min_notional": Decimal(
                filters.get("MIN_NOTIONAL", {}).get("notional")
                or filters.get("NOTIONAL", {}).get("minNotional", "0")
            ),
            "quote_precision": sym_info.get("quoteAssetPrecision", 8),
        }
        self._symbol_filters_cache[symbol] = result
        return result

    def round_qty(self, symbol, qty: float) -> float:
        f = self.get_symbol_filters(symbol)
        step = f["step_size"]
        q = Decimal(str(qty)).quantize(step, rounding=ROUND_DOWN)
        # snap to step
        q = (q // step) * step if step > 0 else q
        return float(q)

    def round_price(self, symbol, price: float) -> float:
        f = self.get_symbol_filters(symbol)
        tick = f["tick_size"]
        p = Decimal(str(price)).quantize(tick, rounding=ROUND_DOWN)
        p = (p // tick) * tick if tick > 0 else p
        return float(p)

    # ---------- account (signed) ----------

    def account(self):
        path = "/api/v3/account" if self.market == "spot" else "/fapi/v2/account"
        return self._request("GET", path, signed=True)

    def available_balance_usdt(self):
        acc = self.account()
        if self.market == "spot":
            for bal in acc["balances"]:
                if bal["asset"] == "USDT":
                    return float(bal["free"])
            return 0.0
        else:
            return float(acc.get("availableBalance", 0.0))

    def open_positions(self):
        """Futures only — returns non-zero positions."""
        assert self.market == "futures"
        acc = self.account()
        positions = []
        for p in acc.get("positions", []):
            amt = float(p["positionAmt"])
            if abs(amt) > 0:
                positions.append(p)
        return positions

    # ---------- orders (signed) ----------

    def place_market_order(self, symbol, side, quantity, reduce_only=False):
        path = "/api/v3/order" if self.market == "spot" else "/fapi/v1/order"
        params = {"symbol": symbol, "side": side, "type": "MARKET", "quantity": quantity}
        if self.market == "futures" and reduce_only:
            params["reduceOnly"] = "true"
        return self._request("POST", path, params=params, signed=True)

    def place_stop_market(self, symbol, side, quantity, stop_price, reduce_only=True):
        """Futures STOP_MARKET (used as stop-loss exit)."""
        assert self.market == "futures"
        path = "/fapi/v1/order"
        params = {
            "symbol": symbol,
            "side": side,
            "type": "STOP_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true" if reduce_only else "false",
            "workingType": "MARK_PRICE",
        }
        return self._request("POST", path, params=params, signed=True)

    def place_take_profit_market(self, symbol, side, quantity, stop_price, reduce_only=True):
        """Futures TAKE_PROFIT_MARKET (used as take-profit exit)."""
        assert self.market == "futures"
        path = "/fapi/v1/order"
        params = {
            "symbol": symbol,
            "side": side,
            "type": "TAKE_PROFIT_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true" if reduce_only else "false",
            "workingType": "MARK_PRICE",
        }
        return self._request("POST", path, params=params, signed=True)

    def place_oco_spot(self, symbol, side, quantity, take_profit_price, stop_price, stop_limit_price):
        """Spot OCO (One-Cancels-Other) used to bracket a spot long with TP + SL at once."""
        assert self.market == "spot"
        path = "/api/v3/order/oco"
        params = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": take_profit_price,
            "stopPrice": stop_price,
            "stopLimitPrice": stop_limit_price,
            "stopLimitTimeInForce": "GTC",
        }
        return self._request("POST", path, params=params, signed=True)

    def cancel_order(self, symbol, order_id):
        path = "/api/v3/order" if self.market == "spot" else "/fapi/v1/order"
        return self._request(
            "DELETE", path, params={"symbol": symbol, "orderId": order_id}, signed=True
        )

    def get_order(self, symbol, order_id):
        path = "/api/v3/order" if self.market == "spot" else "/fapi/v1/order"
        return self._request(
            "GET", path, params={"symbol": symbol, "orderId": order_id}, signed=True
        )

    def set_leverage(self, symbol, leverage):
        assert self.market == "futures"
        return self._request(
            "POST", "/fapi/v1/leverage", params={"symbol": symbol, "leverage": leverage}, signed=True
        )
