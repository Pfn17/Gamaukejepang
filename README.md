# Crypto Scalper — Binance TESTNET

Bot scalping (spot + futures) untuk **Binance Testnet only**, dengan strategi
confluence rule-based, risk management otomatis, dashboard real-time, notifikasi
Telegram, dan reasoning/journaling AI (Groq primer, Anthropic fallback).

## ⚠️ Baca dulu sebelum jalan

1. **Semua kredensial yang pernah kamu paste di chat sebelumnya harus dianggap
   bocor.** Revoke & generate ulang: GitHub PAT, Telegram bot token, Groq key,
   Anthropic key, dan Binance testnet key/secret. Jangan pernah paste key asli
   ke chat/dokumen manapun lagi.
2. **Target profit realistis.** $100 → Rp200.000/hari (~12-13%/hari, konsisten)
   itu bukan target scalping wajar — itu level yang biasanya hanya tercapai
   lewat leverage ekstrem + oversized position, yang sama saja dengan judi.
   Sistem ini **tidak** dirancang untuk memaksa angka itu. Risk per trade
   dibatasi (default 1% saldo/trade), jadi realistiknya walau winrate bagus,
   return harian yang sehat ada di kisaran jauh lebih kecil dari itu. Ubah
   `RISK_PER_TRADE_PCT` kalau paham risikonya, tapi jangan naikkan drastis
   hanya untuk mengejar target harian.
3. **Ini testnet.** Tidak ada uang asli yang berisiko selama kamu pakai
   `testnet.binance.vision` / `testnet.binancefuture.com`. Kalau nanti mau ke
   mainnet, itu keputusan terpisah dengan risiko sepenuhnya milik kamu — bot
   ini TIDAK divalidasi untuk itu tanpa testing panjang + backtest historis
   dulu.
4. **Soal VPN untuk bypass geo-block Binance:** itu berpotensi melanggar ToS
   Binance. Untuk testnet risikonya kecil, tapi tetap keputusanmu sendiri.
   Panduan di bawah tidak menyertakan VPN karena GitHub Codespaces biasanya
   sudah punya IP yang tidak kena geo-block versi HP kamu.

## Strategi (ringkas)

Long-only, multi-timeframe confluence:
`EMA9>EMA21>EMA50 (trend)` + `pullback ke EMA9/VWAP` + `RSI 45-68` +
`volume >1.3x rata-rata` → entry, dengan stop loss berbasis ATR/swing-low
(dipilih yang lebih ketat), dan take-profit dihitung dari `MIN_RISK_REWARD_RATIO`
(default 1.25). Kalau salah satu syarat gagal → tidak ada sinyal. Detail
lengkap ada di `src/strategy.py` — semua logikanya dikomentari baris per baris,
silakan diaudit.

**Catatan jujur:** ini strategi berbasis prinsip TA yang sudah mapan
(trend-following + pullback + volume confirmation), bukan alpha rahasia yang
terbukti profitable. Sebelum eksekusi sungguhan (bahkan di testnet dalam
jumlah besar), sebaiknya kamu backtest dulu pakai data historis untuk lihat
performanya sebelum percaya penuh.

## Struktur project

```
crypto-scalper/
  .env.example        <- copy ke .env, isi key ASLI kamu (yang sudah di-rotate)
  config.py            <- semua parameter dibaca dari .env
  src/
    binance_client.py  <- REST client testnet, signed requests
    market_scanner.py  <- scan top gainers, filter likuiditas & leveraged token
    indicators.py       <- EMA/RSI/ATR/VWAP dari raw kline
    strategy.py          <- logika sinyal
    risk_manager.py      <- position sizing, daily loss limit, trade caps
    executor.py           <- eksekusi order + bracket SL/TP
    ai_reasoner.py         <- Groq -> fallback Anthropic, untuk narasi & jurnal
    telegram_bot.py         <- notifikasi
    journal.py               <- log JSONL, dibaca dashboard
    dashboard.py              <- Flask real-time dashboard
    main.py                    <- orchestrator/loop utama
  templates/dashboard.html
  scripts/auto_push.sh          <- commit+push journal ke GitHub berkala
```

## Setup — GitHub Codespaces (direkomendasikan, jalan dari Chrome HP)

1. Buat repo baru **private** di GitHub (dari HP: buka github.com → New
   repository → private).
2. Upload semua file project ini ke repo itu (drag & drop lewat web UI GitHub,
   atau `git push` dari mana saja kamu punya akses).
3. Di halaman repo → tombol hijau **Code** → tab **Codespaces** → **Create
   codespace on main**. Ini buka VS Code di browser, jalan di server GitHub
   (bukan di HP kamu).
4. Di terminal Codespaces:
   ```bash
   cp .env.example .env
   nano .env   # isi semua key ASLI kamu yang sudah di-rotate
   pip install -r requirements.txt
   ```
5. Jalankan bot (proses 1):
   ```bash
   python -m src.main
   ```
6. Buka terminal kedua, jalankan dashboard (proses 2):
   ```bash
   python -m src.dashboard
   ```
   Codespaces akan munculkan notifikasi "port 5000 forwarded" — klik untuk
   buka dashboard di browser HP kamu.
7. Terminal ketiga, auto-push berkala ke GitHub (proses 3):
   ```bash
   set -a; source .env; set +a
   bash scripts/auto_push.sh loop 300
   ```
8. Tutup tab Chrome pun codespace tetap jalan di server (sampai idle timeout
   default GitHub, biasanya 30 menit tanpa aktivitas terminal — untuk 24/7
   sungguhan kamu perlu keep-alive terpisah atau upgrade plan Codespaces).

## Setup — Termux (Poco M4 Pro), untuk monitoring/notifikasi saja

Termux **tidak disarankan** menjalankan proses trading 24/7 (Android mematikan
background process, koneksi putus-nyambung). Pakai untuk cek status atau
jalankan dashboard lokal saat HP aktif:

```bash
pkg update && pkg upgrade
pkg install python git -y
git clone <url-repo-kamu>
cd crypto-scalper
pip install -r requirements.txt
cp .env.example .env
nano .env
python -m src.dashboard
```

Notifikasi trade tetap masuk ke Telegram kapan pun (dikirim dari bot yang
jalan di Codespaces), jadi kamu tidak perlu Termux menyala terus untuk tahu
statusnya.

## Setup — Pydroid3

Tidak disarankan untuk proses `main.py` (long-running background service) —
Pydroid3 didesain untuk eksekusi script interaktif/GUI, bukan service 24/7.
Kalau mau, bisa dipakai sekadar untuk baca-baca `journal/trades.jsonl` atau
eksplorasi kode.

## Precision check sebelum live-run

- Set `BINANCE_USE_FUTURES=true` dan/atau `BINANCE_USE_SPOT=true` sesuai
  kebutuhan (default: dua-duanya aktif, sesuai request kamu).
- `MIN_RISK_REWARD_RATIO=1.25` sudah sesuai target R:R kamu.
- Cek `MAX_TRADES_PER_DAY` (default 40) — ini yang mengontrol "puluhan trade
  sehari" tanpa jadi overtrading tak terbatas.
- Order size dibulatkan otomatis sesuai `LOT_SIZE`/`PRICE_FILTER` exchange
  (lihat `binance_client.py::round_qty/round_price`) — mencegah order reject
  karena presisi salah, kesalahan umum di bot-bot asal jadi.

## Yang belum dan sebaiknya kamu tambahkan sebelum mainnet

- Backtesting engine terhadap data historis (belum ada di sini — dashboard
  live baru mulai mengumpulkan data sejak kamu jalankan).
- Reconciliation PnL yang lebih presisi (fee trading, slippage funding rate
  futures) — perhitungan PnL saat ini murni `(exit-entry)*qty`, belum
  memotong fee.
- Circuit breaker kalau API Binance down/lag (saat ini loop akan retry di
  cycle berikutnya, tapi tidak ada alert khusus "API down > 5 menit").

Kalau kamu mau, saya bisa lanjutkan ke backtesting engine berikutnya supaya
kamu bisa uji strategi ini terhadap data historis sebelum percaya penuh sama
live signals-nya.
