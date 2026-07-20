import unittest

from src.quant_model import MarketContext, QuantSignal, quantify_market


class QuantModelTestCase(unittest.TestCase):
    def test_bullish_context_returns_positive_score(self):
        candles = []
        for i in range(80):
            price = 100 + i * 0.2
            candles.append({
                "open": price,
                "high": price + 0.5,
                "low": price - 0.5,
                "close": price + 0.1,
                "volume": 1200 + i,
            })
        ctx = MarketContext(
            symbol="BTCUSDT",
            price=100 + 79 * 0.2 + 0.1,
            change_24h=2.8,
            volume_ratio=1.7,
            funding_rate=0.0004,
            open_interest_ratio=1.35,
            momentum=0.8,
            volatility=0.02,
        )
        signal = quantify_market("BTCUSDT", candles, ctx)
        self.assertIsInstance(signal, QuantSignal)
        self.assertGreater(signal.score, 0.0)
        self.assertIn(signal.label, {"bullish", "neutral", "bearish"})

    def test_neutral_context_is_capped(self):
        candles = []
        for i in range(80):
            price = 100.0
            candles.append({
                "open": price,
                "high": price + 0.1,
                "low": price - 0.1,
                "close": price,
                "volume": 1000,
            })
        ctx = MarketContext(symbol="ETHUSDT", price=100.0, change_24h=0.0, volume_ratio=1.0, funding_rate=0.0, open_interest_ratio=1.0, momentum=0.0, volatility=0.01)
        signal = quantify_market("ETHUSDT", candles, ctx)
        self.assertLessEqual(abs(signal.score), 1.0)


if __name__ == "__main__":
    unittest.main()
