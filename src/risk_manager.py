"""
Risk manager. This module is the one allowed to say "no" to a trade
regardless of how good the signal looks. Nothing bypasses it.

Rules enforced:
- Position size = fixed fractional risk (RISK_PER_TRADE_PCT of current
  balance) divided by the per-unit stop distance. This means every trade
  risks the SAME % of account, regardless of how volatile the symbol is.
- Daily loss limit: once realized PnL for the day drops below
  -DAILY_LOSS_LIMIT_PCT of the day's starting balance, trading halts until
  the next UTC day.
- Max concurrent open trades and max trades per day, to keep this from
  turning into overtrading (which is how "high frequency" ideas usually
  blow up an account).
"""
import datetime
from dataclasses import dataclass, field
from config import cfg


@dataclass
class RiskState:
    day: str = field(default_factory=lambda: datetime.datetime.utcnow().strftime("%Y-%m-%d"))
    starting_balance: float = 0.0
    realized_pnl_today: float = 0.0
    trades_today: int = 0
    open_trades: int = 0

    def maybe_roll_day(self, current_balance: float):
        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
        if today != self.day:
            self.day = today
            self.starting_balance = current_balance
            self.realized_pnl_today = 0.0
            self.trades_today = 0


class RiskManager:
    def __init__(self):
        self.state = RiskState()

    def _daily_loss_hit(self) -> bool:
        if self.state.starting_balance <= 0:
            return False
        limit = -abs(cfg.DAILY_LOSS_LIMIT_PCT) / 100 * self.state.starting_balance
        return self.state.realized_pnl_today <= limit

    def can_open_new_trade(self, current_balance: float) -> tuple[bool, str]:
        self.state.maybe_roll_day(current_balance)
        if self.state.starting_balance == 0.0:
            self.state.starting_balance = current_balance

        if self._daily_loss_hit():
            return False, "daily loss limit reached — trading halted until next UTC day"
        if self.state.trades_today >= cfg.MAX_TRADES_PER_DAY:
            return False, f"max trades/day ({cfg.MAX_TRADES_PER_DAY}) reached"
        if self.state.open_trades >= cfg.MAX_CONCURRENT_TRADES:
            return False, f"max concurrent trades ({cfg.MAX_CONCURRENT_TRADES}) reached"
        if current_balance <= 0:
            return False, "zero/negative available balance"
        return True, "ok"

    def position_size(self, balance: float, entry: float, stop_loss: float) -> float:
        """Returns quantity (in base asset units) sized to risk exactly
        RISK_PER_TRADE_PCT of balance if stop_loss is hit."""
        risk_amount = balance * (cfg.RISK_PER_TRADE_PCT / 100)
        per_unit_risk = abs(entry - stop_loss)
        if per_unit_risk <= 0:
            return 0.0
        qty = risk_amount / per_unit_risk
        return max(qty, 0.0)

    def register_trade_opened(self):
        self.state.trades_today += 1
        self.state.open_trades += 1

    def register_trade_closed(self, realized_pnl: float):
        self.state.realized_pnl_today += realized_pnl
        self.state.open_trades = max(0, self.state.open_trades - 1)
