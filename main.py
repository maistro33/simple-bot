#!/usr/bin/env python3
"""
SADIK SIMPLE BOT v2 — Basit Trend + Momentum
Paper Trading — AI karşılaştırma için
"""

import os, time, threading
import ccxt
import pandas as pd
import requests as req
import telebot
from supabase import create_client

# ─── CONFIG ───
TELE_TOKEN = os.getenv("TELE_TOKEN","")
CHAT_ID    = int(os.getenv("MY_CHAT_ID","0"))
BITGET_API = os.getenv("BITGET_API","")
BITGET_SEC = os.getenv("BITGET_SEC","")
BITGET_PASS= os.getenv("BITGET_PASS","")
SUPA_URL   = os.getenv("SUPABASE_URL","")
SUPA_KEY   = os.getenv("SUPABASE_KEY","")

# ─── RİSK ───
LEVERAGE      = 5
MARGIN        = 10.0
TP_PCT        = 0.015   # %1.5
SL_PCT        = 0.010   # %1.0
MAX_OPEN      = 5
MAX_OPEN_NEUTRAL = 5    # BTC NEUTRAL'da max 2 pozisyon
SCAN_INTERVAL = 30
MIN_QUOTE_VOL = 2_000_000  # 3M'den 2M'ye düşürüldü
MAX_PRICE     = 30

BLACKLIST = {
    "BANANAS31","BSB","JCT","MEGA","ALLO","FTM","MU","NVDA","TSLA",
    "TURBO","MOODENG","SUNDOG","NEIRO","HMSTR","CATI","DOGS","MYRO",
    "BOME","SLERF","PNUT","ACT","GOAT","RGTI","SATL","WET","POET",
    "QCOM","AAPL","AMZN","GOOGL","META","MSFT","COIN","UBER","ARQQ",
}

# ─── TELEGRAM ───
bot = telebot.TeleBot(TELE_TOKEN)
def tg(msg):
    try: bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e: print(f"[TG] {e}")

# ─── SUPABASE ───
supa = None
if SUPA_URL and SUPA_KEY:
    try:
        supa = create_client(SUPA_URL, SUPA_KEY)
        print("[SUPA] OK")
    except Exception as e: print(f"[SUPA] {e}")

def save_trade(data):
    if not supa: return
    try: supa.table("simple_trades").insert(data).execute()
    except Exception as e: print(f"[SAVE] {e}")

# ─── EXCHANGE ───
exchange = ccxt.bitget({
    "apiKey": BITGET_API, "secret": BITGET_SEC,
    "password": BITGET_PASS, "enableRateLimit": True,
    "options": {"defaultType": "swap"},
})
LAST_API = 0

def safe_api(func, *args, **kwargs):
    global LAST_API
    for i in range(4):
        try:
            w = 0.8 - (time.time() - LAST_API)
            if w > 0: time.sleep(w)
            LAST_API = time.time()
            return func(*args, **kwargs)
        except ccxt.RateLimitExceeded:
            time.sleep(10)
        except Exception as e:
            print(f"[API {i}] {e}")
            time.sleep(3)
    return None

# ─── STATE ───
positions = {}
pos_lock  = threading.Lock()

# ─── BTC TREND ───
def get_btc_trend():
    try:
        raw = safe_api(exchange.fetch_ohlcv, "BTC/USDT:USDT", "1h", limit=50)
        if not raw: return "NEUTRAL"
        df = pd.DataFrame(raw, columns=["t","o","h","l","c","v"])
        c  = df["c"]
        e20 = float(c.ewm(span=20).mean().iloc[-1])
        e50 = float(c.ewm(span=50).mean().iloc[-1])
        p   = float(c.iloc[-1])
        if p > e20 and e20 > e50: return "UP"
        if p < e20 and e20 < e50: return "DOWN"
        return "NEUTRAL"
    except: return "NEUTRAL"

# ─── RSI ───
def calc_rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return float((100 - 100/(1+g/l.replace(0,0.001))).iloc[-1])

# ─── GÖSTERGELER ───
def calc_indicators(symbol):
    try:
        raw1 = safe_api(exchange.fetch_ohlcv, symbol, "1m", limit=50)
        if not raw1 or len(raw1) < 20: return None
        df = pd.DataFrame(raw1, columns=["t","o","h","l","c","v"])
        c = df["c"]; v = df["v"]

        price  = float(c.iloc[-1])
        if price <= 0: return None

        ema9   = float(c.ewm(span=9).mean().iloc[-1])
        ema20  = float(c.ewm(span=20).mean().iloc[-1])
        rsi    = calc_rsi(c)

        # Son 3 bar aynı yönde mi?
        last3  = [float(c.iloc[-i]) > float(c.iloc[-i-1]) for i in range(1,4)]
        bars_up   = all(last3)
        bars_down = not any(last3)

        # Hacim
        vol_avg   = float(v.rolling(10).mean().iloc[-1])
        vol_ratio = float(v.iloc[-1]) / max(vol_avg, 0.001)

        # Momentum
        prev3  = float(c.iloc[-4])
        if prev3 <= 0: return None
        move_3 = (price - prev3) / prev3 * 100

        return {
            "symbol": symbol, "price": price,
            "ema9": ema9, "ema20": ema20,
            "rsi": rsi, "bars_up": bars_up,
            "bars_down": bars_down,
            "vol_ratio": vol_ratio,
            "move_3": move_3,
        }
    except: return None

# ─── SİNYAL ───
def get_signal(ind, btc_trend):
    rsi = ind["rsi"]

    if rsi < 45 or rsi > 70: return None
    if ind["vol_ratio"] < 0.8: return None  # 1.0'dan 0.8'e düşürüldü

    # LONG
    if (btc_trend in ["UP", "NEUTRAL"]
            and ind["ema9"] > ind["ema20"]
            and ind["bars_up"]
            and ind["move_3"] > 0.1):  # 0.2'den 0.1'e düşürüldü
        # NEUTRAL'da sadece güçlü sinyaller
        if btc_trend == "NEUTRAL" and ind["move_3"] < 0.3:
            return None
        return "LONG"

    # SHORT
    if (btc_trend in ["DOWN", "NEUTRAL"]
            and ind["ema9"] < ind["ema20"]
            and ind["bars_down"]
            and ind["move_3"] < -0.1):  # -0.2'den -0.1'e düşürüldü
        # NEUTRAL'da sadece güçlü sinyaller
        if btc_trend == "NEUTRAL" and ind["move_3"] > -0.3:
            return None
        return "SHORT"

    return None

# ─── PAPER AÇ ───
def open_paper(symbol, signal, ind, btc_trend):
    with pos_lock:
        if symbol in positions: return
        # NEUTRAL'da max 2 pozisyon
        if btc_trend == "NEUTRAL" and len(positions) >= MAX_OPEN_NEUTRAL: return
        if len(positions) >= MAX_OPEN: return

    price = ind["price"]
    if signal == "LONG":
        tp = price*(1+TP_PCT); sl = price*(1-SL_PCT)
    else:
        tp = price*(1-TP_PCT); sl = price*(1+SL_PCT)

    with pos_lock:
        positions[symbol] = {
            "signal": signal, "entry": price,
            "tp": tp, "sl": sl,
            "btc_trend": btc_trend, "ind": ind,
            "open_time": time.time(),
        }

    sym = symbol.split("/")[0]
    tg(
        f"📋 [SIMPLE] {sym} {signal}\n"
        f"Giriş: {price:.6f}\n"
        f"TP: {tp:.6f} (+%{TP_PCT*100:.1f})\n"
        f"SL: {sl:.6f} (-%{SL_PCT*100:.1f})\n"
        f"RSI:{ind['rsi']:.0f} Hacim:{ind['vol_ratio']:.1f}x BTC:{btc_trend}"
    )

# ─── PAPER KAPAT ───
def close_paper(symbol, reason, exit_price=None):
    with pos_lock:
        pos = positions.pop(symbol, None)
    if not pos: return

    if exit_price is None:
        t = safe_api(exchange.fetch_ticker, symbol)
        exit_price = t["last"] if t else pos["entry"]

    sig   = pos["signal"]; entry = pos["entry"]
    pnl   = (exit_price-entry)/entry*MARGIN*LEVERAGE if sig=="LONG" else (entry-exit_price)/entry*MARGIN*LEVERAGE
    sure  = int((time.time() - pos["open_time"]) / 60)
    ind   = pos.get("ind", {})

    save_trade({
        "symbol":      symbol,
        "signal":      sig,
        "pnl":         round(pnl, 4),
        "rsi":         ind.get("rsi", 0),
        "vol_ratio":   ind.get("vol_ratio", 0),
        "move_3":      ind.get("move_3", 0),
        "btc_trend":   pos.get("btc_trend", "NEUTRAL"),
        "sure_dk":     sure,
        "cikis":       reason,
    })

    sym  = symbol.split("/")[0]
    icon = "🟢" if pnl >= 0 else "🔴"
    tg(f"{icon} [SIMPLE] {sym} KAPANDI\n{reason}\nPnL: {pnl:+.2f} USDT | {sure}dk")

# ─── YÖNETİCİ ───
def manage_loop():
    while True:
        time.sleep(5)
        try:
            with pos_lock: syms = list(positions.keys())
            for symbol in syms:
                with pos_lock:
                    pos = positions.get(symbol)
                if not pos: continue

                t = safe_api(exchange.fetch_ticker, symbol)
                if not t: continue
                price  = t["last"]
                sig    = pos["signal"]
                pnl_pct = (price-pos["entry"])/pos["entry"]*100 if sig=="LONG" else (pos["entry"]-price)/pos["entry"]*100

                if pnl_pct >= TP_PCT*100:
                    close_paper(symbol, f"TP +%{TP_PCT*100:.1f} 🎯", price)
                elif pnl_pct <= -SL_PCT*100:
                    close_paper(symbol, f"SL -%{SL_PCT*100:.1f}", price)
                elif time.time() - pos["open_time"] > 60*60:
                    close_paper(symbol, "ZAMAN AŞIMI 60dk", price)
        except Exception as e:
            print(f"[MANAGE] {e}")

# ─── TARAYICI ───
def scanner_loop():
    while True:
        try:
            with pos_lock:
                open_count = len(positions)
                if open_count >= MAX_OPEN:
                    time.sleep(10); continue

            btc_trend = get_btc_trend()

            tickers = safe_api(exchange.fetch_tickers)
            if not tickers:
                time.sleep(SCAN_INTERVAL); continue

            active = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith("/USDT:USDT"): continue
                sym = symbol.split("/")[0]
                if sym in BLACKLIST: continue
                if ticker.get("quoteVolume", 0) < MIN_QUOTE_VOL: continue
                price = ticker.get("last", 0) or 0
                if price > MAX_PRICE: continue
                pct = abs(ticker.get("percentage", 0) or 0)
                if pct < 0.2: continue  # 0.3'ten 0.2'ye düşürüldü
                active.append(symbol)

            print(f"[SIMPLE SCAN] {len(active)} coin | BTC:{btc_trend}")

            for symbol in active[:60]:
                with pos_lock:
                    if symbol in positions: continue
                    if btc_trend == "NEUTRAL" and len(positions) >= MAX_OPEN_NEUTRAL: break
                    if len(positions) >= MAX_OPEN: break

                ind = calc_indicators(symbol)
                if not ind: continue

                signal = get_signal(ind, btc_trend)
                if not signal: continue

                sym = symbol.split("/")[0]
                print(f"[SIMPLE SİNYAL] {sym} {signal} RSI={ind['rsi']:.0f} BTC={btc_trend}")
                open_paper(symbol, signal, ind, btc_trend)
                time.sleep(1)

            time.sleep(SCAN_INTERVAL)

        except Exception as e:
            print(f"[SCANNER] {e}")
            time.sleep(10)

# ─── HEALTH ───
def health_server():
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
        def log_message(self, *a): pass
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()

# ─── KOMUTLAR ───
@bot.message_handler(commands=["simple","simplestats"])
def cmd_stats(msg):
    if not supa:
        bot.send_message(msg.chat.id, "Supabase yok."); return
    try:
        r = supa.table("simple_trades").select("pnl,btc_trend").execute()
        data = r.data or []
        if not data:
            bot.send_message(msg.chat.id, "Henüz kayıt yok."); return
        toplam = len(data)
        kazan  = sum(1 for d in data if float(d.get("pnl") or 0) > 0)
        net    = sum(float(d.get("pnl") or 0) for d in data)
        bot.send_message(msg.chat.id,
            f"📊 SIMPLE BOT\n\n"
            f"Toplam: {toplam} işlem\n"
            f"Kazanan: {kazan} (%{kazan/toplam*100:.0f})\n"
            f"Net: {net:+.2f} USDT"
        )
    except Exception as e:
        bot.send_message(msg.chat.id, f"Hata: {e}")

# ─── MAIN ───
if __name__ == "__main__":
    print("🟢 SADIK SIMPLE BOT v2 BAŞLIYOR...")
    threading.Thread(target=health_server, daemon=True).start()
    threading.Thread(target=manage_loop,   daemon=True).start()
    threading.Thread(target=scanner_loop,  daemon=True).start()
    tg(
        "🟢 SADIK SIMPLE BOT v2\n\n"
        "Strateji: Trend + Momentum + RSI\n\n"
        f"TP: %{TP_PCT*100:.1f} | SL: %{SL_PCT*100:.1f}\n"
        "BTC UP → LONG\n"
        "BTC DOWN → SHORT\n"
        "BTC NEUTRAL → max 2 pozisyon\n"
        "Hacim filtresi: 2M (3M'den düşürüldü)\n"
        "Momentum: 0.1 (0.2'den düşürüldü)\n\n"
        "/simple → istatistik"
    )
    while True:
        try: bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"[POLLING] {e}"); time.sleep(5)
