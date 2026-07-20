"""
Append-only JSONL trade journal. Simple on purpose — this is the single
source of truth the dashboard reads from, so it needs to survive crashes
(each line is a complete, independently-parseable record).
"""
import json
import os
import datetime

JOURNAL_PATH = os.path.join(os.path.dirname(__file__), "..", "journal", "trades.jsonl")


def _now():
    return datetime.datetime.utcnow().isoformat() + "Z"


def log_event(event_type: str, data: dict):
    os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
    record = {"ts": _now(), "type": event_type, **data}
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record


def read_all():
    if not os.path.exists(JOURNAL_PATH):
        return []
    records = []
    with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def summary_stats():
    records = read_all()
    closed = [r for r in records if r.get("type") == "trade_closed"]
    wins = [r for r in closed if r.get("pnl", 0) > 0]
    losses = [r for r in closed if r.get("pnl", 0) <= 0]
    total_pnl = sum(r.get("pnl", 0) for r in closed)
    winrate = (len(wins) / len(closed) * 100) if closed else 0.0
    return {
        "total_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "winrate_pct": round(winrate, 1),
        "total_pnl": round(total_pnl, 2),
    }
