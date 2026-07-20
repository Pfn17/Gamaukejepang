import os
import json
from src import journal
from config import cfg


STATUS_PATH = os.path.join(os.path.dirname(__file__), "..", "journal", "status.json")


def _read_status() -> dict:
    if not os.path.exists(STATUS_PATH):
        return {"state": "starting", "open_positions": [], "last_scan": None}
    with open(STATUS_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"state": "unknown", "open_positions": [], "last_scan": None}


def build_help() -> str:
    return (
        "🤖 Telegram commands:\n"
        "/status - lihat status bot saat ini\n"
        "/positions - lihat posisi terbuka\n"
        "/stats - lihat ringkasan pnl/winrate\n"
        "/logs - lihat 10 event terakhir\n"
        "/help - tampilkan bantuan ini"
    )


def build_status_message() -> str:
    status = _read_status()
    stats = journal.summary_stats()
    open_positions = status.get("open_positions", [])
    lines = [
        "📊 Bot Status",
        f"State: {status.get('state', 'unknown')}",
        f"Last scan: {status.get('last_scan', 'n/a')}",
        f"Open positions: {len(open_positions)}",
        f"Total trades: {stats['total_trades']}",
        f"Winrate: {stats['winrate_pct']}%",
        f"PnL: {stats['total_pnl']} USDT",
    ]
    if open_positions:
        lines.append("\nOpen positions:")
        for pos in open_positions:
            lines.append(
                f"- {pos['symbol']} | entry {pos['entry']:.4f} | SL {pos['stop_loss']:.4f} | TP {pos['take_profit']:.4f} | qty {pos['qty']}"
            )
    else:
        lines.append("\nNo open positions")
    return "\n".join(lines)


def build_stats_message() -> str:
    stats = journal.summary_stats()
    return (
        "📈 Performance Summary\n"
        f"Trades: {stats['total_trades']}\n"
        f"Wins: {stats['wins']}\n"
        f"Losses: {stats['losses']}\n"
        f"Winrate: {stats['winrate_pct']}%\n"
        f"Total PnL: {stats['total_pnl']} USDT"
    )


def build_logs_message(limit: int = 10) -> str:
    records = journal.read_all()[-limit:][::-1]
    if not records:
        return "📝 No journal events yet"
    lines = ["📝 Recent events:"]
    for rec in records:
        lines.append(f"- {rec.get('ts', 'n/a')} | {rec.get('type', 'event')} | {rec.get('symbol', '')} {rec.get('reason', '')} {rec.get('pnl', '')}".strip())
    return "\n".join(lines)


def handle_command(command: str) -> str:
    cmd = (command or "").strip().lower()
    if cmd in {"/help", "help"}:
        return build_help()
    if cmd in {"/status", "status"}:
        return build_status_message()
    if cmd in {"/positions", "positions"}:
        status = _read_status()
        positions = status.get("open_positions", [])
        if not positions:
            return "📍 No open positions"
        lines = ["📍 Open positions:"]
        for pos in positions:
            lines.append(f"- {pos['symbol']} | {pos['market']} | entry {pos['entry']:.4f} | SL {pos['stop_loss']:.4f} | TP {pos['take_profit']:.4f}")
        return "\n".join(lines)
    if cmd in {"/stats", "stats"}:
        return build_stats_message()
    if cmd in {"/logs", "logs"}:
        return build_logs_message()
    return build_help()
