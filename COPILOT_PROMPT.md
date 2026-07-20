# Prompt untuk GitHub Copilot Chat (di Codespaces)

Paste blok ini ke Copilot Chat setelah project sudah ada di repo dan
Codespace sudah terbuka. Sudah ditulis presisi supaya Copilot tidak
mengarang ulang arsitektur, hanya membantu deployment + hardening.

---

```
Saya punya project Python di repo ini bernama "crypto-scalper" — bot trading
scalping untuk Binance TESTNET (spot + USDT-M futures), sudah punya:
- config.py (loader .env, fail loudly kalau env wajib kosong)
- src/binance_client.py (REST client signed request, testnet only)
- src/market_scanner.py (scan top gainer, filter leveraged token & likuiditas)
- src/indicators.py (EMA/RSI/ATR/VWAP dari raw kline, no external TA lib)
- src/strategy.py (signal rule-based: trend filter + pullback + RSI + volume + R:R)
- src/risk_manager.py (fixed fractional position sizing, daily loss limit, trade caps)
- src/executor.py (eksekusi order + bracket SL/TP, rounding sesuai LOT_SIZE/PRICE_FILTER)
- src/ai_reasoner.py (Groq primary, Anthropic fallback, HANYA untuk narasi/jurnal — BUKAN sumber sinyal)
- src/telegram_bot.py, src/journal.py, src/dashboard.py (Flask), src/main.py (loop utama)
- scripts/auto_push.sh (commit+push journal berkala pakai GITHUB_TOKEN dari env)

Tolong bantu saya dengan langkah berikut, JANGAN mengubah logika strategi
atau risk management yang sudah ada tanpa saya minta eksplisit:

1. Jalankan `pip install -r requirements.txt` dan perbaiki kalau ada
   dependency yang gagal install di environment Codespaces ini.
2. Cek `.env` saya (sudah saya isi dari `.env.example`) — validasi semua
   variable required terbaca dengan benar oleh config.py, tanpa
   menampilkan isi key asli di chat/log manapun.
3. Jalankan `python -m src.main` di satu terminal dan `python -m src.dashboard`
   di terminal lain. Kalau ada error saat startup, diagnosis dari traceback
   dan perbaiki BUG-nya (bukan mengganti logika strategi), lalu jelaskan
   akar masalahnya ke saya dalam Bahasa Indonesia singkat.
4. Setup port forwarding untuk DASHBOARD_PORT (default 5000) supaya bisa
   saya buka dari browser HP.
5. Tambahkan file `.github/workflows/keepalive.yml` sederhana (jika
   relevan) HANYA jika saya minta — jangan buat otomatis kalau saya tidak
   minta, karena bisa mempengaruhi biaya/limit Codespaces saya.
6. SEBELUM menyarankan perubahan apapun ke src/strategy.py atau
   src/risk_manager.py, tanya saya dulu — dua file itu adalah inti risk
   control, jangan diubah diam-diam meskipun terlihat "lebih optimal".
7. Kalau kamu menemukan bug nyata (bukan gaya penulisan) di file manapun,
   tunjukkan diff-nya dan jelaskan root cause-nya sebelum saya approve,
   jangan langsung auto-apply perubahan besar.
8. Terakhir, bantu saya jalankan `bash scripts/auto_push.sh` sekali secara
   manual dulu (bukan mode loop) supaya saya bisa cek commit-nya di GitHub
   sebelum saya nyalakan mode loop otomatis.

Semua ini untuk Binance TESTNET saja — jangan sarankan konfigurasi apapun
yang mengarah ke mainnet/API key production.
```
