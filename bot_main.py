#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
PAPER BOT FIRSATÇI v1.0 — Sabit Hızlı Kâr Hedefi (SANAL)
01 Eylül 2026

⚠️ BU BOT GERÇEK EMİR AÇMAZ. Sadece canlı fiyatlarla simülasyon
yapar, sonuçları kaydeder.

GEREKÇE: Kullanıcı isteği - "dalgalanmadan kazanmak, yükselirken gir,
küçük ama garanti kâr olunca hemen çık, sürekli/sık kazanç ile kasa
büyüsün." Bu, mevcut paper_bot_v2'nin (iz süren TP + kısmi kâr alma)
YERİNE değil, ONA EK bir deney - aynı kanıtlanmış giriş filtresini
kullanıyor ama çıkışı tamamen farklı: SABİT, HIZLI bir hedef.

BACKTEST SONUCU (78 coin, ~14 gün, $1 marjin/$10 notional ölçeğinde,
komisyon dahil NET rakamlar):
  %5 sabit hedef: 573 işlem, %64.4 kazanma, net +$58.10 (ort +$0.10/işlem)
  Brüt $64.97 idi, komisyon $6.88 (%10.6) yedi, net $58.10 kaldı.
  (Kıyaslama: mevcut iz süren+kısmi kâr alma botu aynı ölçekte ~+$5.82
  veriyordu - ama bu iki strateji birbirinin YERİNE değil, farklı
  senaryolar. Gerçek performans garantisi YOK, bu ilk canlı/paper testi.)

MANTIK (giriş - paper_bot_v2 ile AYNI, kanıtlanmış filtre):
  1) 1D trend YUKARI olmalı (20 periyot MA)
  2) 4H trend YUKARI olmalı
  3) 1H trend YUKARI olmalı
  4) 15m'de swing dip + dönüş onayı → LONG (SADECE LONG)

ÇIKIŞ (BURASI FARKLI - paper_bot_v2'nin iz sürmesi YERİNE):
  - SL: swing bazlı, geniş (%5 taban) - aynı güvenlik mantığı
  - TP: SABİT %5 hedef - fiyat oraya değer değmez HEMEN kapan, bekleme yok
  - Max tutma: 4 SAAT (24 değil) - "hızlı gir çık" isteğine uygun, kararsız
    pozisyonlar uzun süre beklemeden kapanır

⚠️ DÜRÜSTLÜK NOTU: Bu strateji SADECE backtest edildi, hiç canlı/paper
test edilmedi. Backtest'teki %5 hedefin gerçek piyasada aynı sıklıkla
tutturulacağının garantisi yok - kayan (slippage), ani ters dönüşler,
ya da MAX_POS sınırının backtest'ten farklı sonuç vermesi mümkün.
════════════════════════════════════════════════════════
"""

import os
import time
import json
import logging
import threading
import ccxt
import telebot
import pandas as pd
import numpy as np
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                     stream=sys.stdout, force=True)
log = logging.getLogger("PAPER_FIRSATCI")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0"))
API_KEY = os.getenv("BITGET_API", "")
API_SEC = os.getenv("BITGET_SEC", "")
PASSPHRASE = os.getenv("BITGET_PASS", "")

if not PASSPHRASE:
    raise RuntimeError("BITGET_PASS ortam değişkeni eksik.")
if not CHAT_ID:
    raise RuntimeError("MY_CHAT_ID ortam değişkeni eksik.")

exchange = ccxt.bitget({
    "apiKey": API_KEY, "secret": API_SEC, "password": PASSPHRASE,
    "options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 30000,
})

bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None


def tg(msg):
    if not bot or not CHAT_ID:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


def yetkili_mi(msg_or_call):
    try:
        chat_id = msg_or_call.message.chat.id if hasattr(msg_or_call, "message") else msg_or_call.chat.id
    except Exception:
        return False
    return chat_id == CHAT_ID


SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}

# ── SANAL (paper) işlem parametreleri ──
BASLANGIC_BAKIYE_USDT = float(os.getenv("BASLANGIC_BAKIYE_USDT", "50.0"))
SANAL_MARJIN_USDT = float(os.getenv("SANAL_MARJIN_USDT", "1.0"))
LEV = 10
NOTIONAL = SANAL_MARJIN_USDT * LEV
MAX_POS = int(os.getenv("MAX_POS", "4"))

LOOKBACK_15M = 20
MA_PERIYOT = 20
SL_BUFFER_PCT = 0.015
MIN_SL_PCT = 0.05
# FIRSATÇI ÇIKIŞ: sabit hedef, iz sürme YOK
HIZLI_HEDEF_PCT = float(os.getenv("HIZLI_HEDEF_PCT", "0.05"))
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
FUNDING_PCT_8SAAT = 0.0001
COOLDOWN_SAAT = 1.0
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "4"))
KONTROL_ARALIGI_SN = 60
ADAY_HAVUZU_BUYUKLUGU = 80

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/firsatci_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/firsatci_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/firsatci_log.json")

trade_state = {}
state_lock = threading.Lock()
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()


def atomik_yaz(path, veri):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(veri, f)
        os.replace(tmp, path)
    except Exception as e:
        log.warning(f"[ATOMIK_YAZ] {path}: {e}")


def guvenli_oku(path, varsayilan):
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception as e:
        log.warning(f"[OKU] {path}: {e}")
    return varsayilan


def durumu_diske_yaz():
    with state_lock:
        veri = dict(trade_state)
    atomik_yaz(TRADE_STATE_PATH, veri)


def durumu_diskten_yukle():
    global trade_state
    trade_state = guvenli_oku(TRADE_STATE_PATH, {})


def cooldown_diske_yaz():
    with cooldown_lock:
        veri = dict(son_kapanis_zamani)
    atomik_yaz(COOLDOWN_PATH, veri)


def cooldown_diskten_yukle():
    global son_kapanis_zamani
    son_kapanis_zamani = guvenli_oku(COOLDOWN_PATH, {})


def trade_log_kaydet(kayit):
    with log_lock:
        trade_log.append(kayit)
        veri = list(trade_log)
    atomik_yaz(TRADE_LOG_PATH, veri)


def trade_log_yukle():
    global trade_log
    trade_log = guvenli_oku(TRADE_LOG_PATH, [])


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def get_df(sym, tf, limit=60):
    for deneme in range(3):
        try:
            candles = exchange.fetch_ohlcv(sym, tf, limit=limit + 1)
            if not candles or len(candles) < 2:
                return None
            candles = candles[:-1]
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
            time.sleep(0.08)
            return df
        except Exception as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                time.sleep(1.5 * (deneme + 1))
                continue
            log.warning(f"[VERI] {sym} {tf}: {e}")
            return None
    return None


def cooldown_da_mi(sym):
    with cooldown_lock:
        son = son_kapanis_zamani.get(sym)
    if son is None:
        return False
    return (time.time() - son) < COOLDOWN_SAAT * 3600


def aday_havuzu():
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
        return []
    try:
        markets = exchange.load_markets()
    except Exception:
        markets = {}
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE:
            continue
        m = markets.get(sym)
        if m and m.get("info", {}).get("isRwa") == "YES":
            continue
        vol = t.get("quoteVolume") or 0
        if vol < 300000:
            continue
        chg = t.get("percentage")
        if chg is None:
            continue
        skor = abs(chg) * np.log10(max(vol, 10))
        adaylar.append((sym, skor))
    adaylar.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in adaylar[:ADAY_HAVUZU_BUYUKLUGU]]


# ════════════════════════════════════════════
# ÜÇLÜ ZAMAN DİLİMİ UYUM SİNYALİ (paper_bot_v2 ile AYNI giriş)
# ════════════════════════════════════════════
def trend_yonu(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma):
        return None
    return "yukselis" if fiyat > ma else "dusus"


def ucyon_sinyal(sym):
    df_1d = get_df(sym, "1d", MA_PERIYOT + 10)
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    df_1h = get_df(sym, "1h", MA_PERIYOT + 5)
    df_15m = get_df(sym, "15m", LOOKBACK_15M + 5)

    yon_1d = trend_yonu(df_1d)
    yon_4h = trend_yonu(df_4h)
    yon_1h = trend_yonu(df_1h)
    if yon_1d != "yukselis" or yon_4h != "yukselis" or yon_1h != "yukselis":
        return None
    if df_15m is None or len(df_15m) < LOOKBACK_15M + 2:
        return None

    pencere = df_15m.iloc[-(LOOKBACK_15M + 1):-1]
    son_mum = df_15m.iloc[-1]
    son_3_idx = pencere.index[-3:]

    swing_low = pencere["low"].min()
    dip_idx = pencere["low"].idxmin()
    dip_yakin = dip_idx in son_3_idx
    yukari_kapandi = son_mum["close"] > son_mum["open"]

    if dip_yakin and yukari_kapandi and son_mum["close"] > swing_low:
        return {"symbol": sym, "entry": float(son_mum["close"]), "swing_nokta": float(swing_low),
                "1d": yon_1d, "4h": yon_4h, "1h": yon_1h}
    return None


# ════════════════════════════════════════════
# SANAL POZİSYON AÇMA/KAPATMA - GERÇEK EMİR YOK
# ════════════════════════════════════════════
def sanal_pozisyon_ac(sinyal):
    sym = sinyal["symbol"]
    with state_lock:
        if sym in trade_state or len(trade_state) >= MAX_POS:
            return
        entry = sinyal["entry"]
        swing_nokta = sinyal["swing_nokta"]

        sl = swing_nokta * (1 - SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, (entry - sl) / entry)
        sl = entry * (1 - sl_mesafe)
        tp = entry * (1 + HIZLI_HEDEF_PCT)

        trade_state[sym] = {
            "entry": entry, "sl": sl, "tp": tp, "yon": "long",
            "acilis_zamani": time.time(),
            "1d": sinyal["1d"], "4h": sinyal["4h"], "1h": sinyal["1h"],
            "notional": NOTIONAL,
        }
    durumu_diske_yaz()
    tg(f"📝 SANAL POZİSYON (fırsatçı): {sym} LONG\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (%{sl_mesafe*100:.1f}) | TP:{tp:.6f} (%{HIZLI_HEDEF_PCT*100:.1f} sabit)\n"
       f"1D:{sinyal['1d']} | 4H:{sinyal['4h']} | 1H:{sinyal['1h']} (üçlü uyumlu)\n"
       f"⚡ FIRSATÇI ÇIKIŞ: hedefe değer değmez HEMEN kapanır, bekleme yok\n"
       f"⚠️ Gerçek emir AÇILMADI - bu sadece simülasyon.")


def sanal_pozisyon_kapat(sym, cikis_fiyat, sebep):
    with state_lock:
        durum = trade_state.pop(sym, None)
    if not durum:
        return
    durumu_diske_yaz()
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()

    entry = durum["entry"]
    poz_notional = durum.get("notional", NOTIONAL)
    pnl_pct = (cikis_fiyat - entry) / entry
    brut_pnl = pnl_pct * poz_notional
    komisyon_maliyeti = KOMISYON_PCT * poz_notional * 2
    sure_saat = (time.time() - durum["acilis_zamani"]) / 3600
    funding_periyot = int(sure_saat // 8)
    funding_maliyeti = FUNDING_PCT_8SAAT * poz_notional * funding_periyot
    net_pnl = brut_pnl - komisyon_maliyeti - funding_maliyeti

    trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat,
                       "brut_pnl": brut_pnl, "komisyon": komisyon_maliyeti, "funding": funding_maliyeti,
                       "pnl": net_pnl, "yon": "long", "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                       "not": sebep, "1d": durum.get("1d"), "4h": durum.get("4h"), "1h": durum.get("1h")})

    emoji = "🟢" if net_pnl >= 0 else "🔴"
    sebep_etiket = {"sl": "SL vuruldu", "hizli_tp": "Hızlı hedef (sabit TP)",
                     "max_hold_timeout": "Max süre doldu (4sa)"}.get(sebep, sebep)
    funding_satiri = f" | Funding: -{funding_maliyeti:.2f}$ ({funding_periyot}x)" if funding_periyot > 0 else ""
    tg(f"{emoji} SANAL kapandı (fırsatçı): {sym} [{sebep_etiket}]\n"
       f"Giriş:{entry:.6f} → Çıkış:{cikis_fiyat:.6f} (%{pnl_pct*100:+.2f} hareket)\n"
       f"Brüt PnL: {brut_pnl:+.2f}$ | Komisyon: -{komisyon_maliyeti:.2f}${funding_satiri}\n"
       f"💰 Net PnL: {net_pnl:+.2f}$ (simülasyon, gerçek para değil)")


# ════════════════════════════════════════════
# PANEL
# ════════════════════════════════════════════
def acik_pozisyonlar_gercek_pnl():
    with state_lock:
        durumlar = dict(trade_state)
    toplam = 0.0
    detaylar = []
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            poz_notional = d.get("notional", NOTIONAL)
            pnl_pct = (guncel - entry) / entry
            anlik = pnl_pct * poz_notional
            toplam += anlik
            detaylar.append((sym, anlik))
        except Exception:
            continue
    return toplam, detaylar


def panel_ozet_metni():
    with log_lock:
        gecmis = list(trade_log)
    gerceklesen_net = sum(t["pnl"] for t in gecmis)
    gerceklesmeyen_net, acik_detay = acik_pozisyonlar_gercek_pnl()
    with state_lock:
        acik_sayi = len(trade_state)

    guncel_bakiye = BASLANGIC_BAKIYE_USDT + gerceklesen_net
    canli_toplam_deger = guncel_bakiye + gerceklesmeyen_net
    toplam_getiri_pct = (canli_toplam_deger - BASLANGIC_BAKIYE_USDT) / BASLANGIC_BAKIYE_USDT * 100

    kasa_emoji = "📈" if canli_toplam_deger >= BASLANGIC_BAKIYE_USDT else "📉"
    satirlar = [
        "⚡ PAPER BOT FIRSATÇI — CANLI ÖZET",
        "(sanal kasa, sabit %5 hızlı hedef, bekleme yok)",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{kasa_emoji} Toplam Değer:  {canli_toplam_deger:,.2f}$   ({toplam_getiri_pct:+.1f}%)",
        f"💼 Kasa (gerçekleşen): {guncel_bakiye:,.2f}$  (başlangıç: {BASLANGIC_BAKIYE_USDT:,.2f}$)",
    ]
    if acik_sayi > 0:
        gc_emoji = "🟢" if gerceklesmeyen_net >= 0 else "🔴"
        satirlar.append(f"{gc_emoji} Açık pozisyonlarda (gerçekleşmemiş): {gerceklesmeyen_net:+.2f}$")
    satirlar.append("━━━━━━━━━━━━━━━━━━━━\n")

    if gecmis:
        toplam = len(gecmis)
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        brut_toplam = sum(t.get("brut_pnl", t["pnl"]) for t in gecmis)
        toplam_komisyon = sum(t.get("komisyon", 0) for t in gecmis)
        toplam_funding = sum(t.get("funding", 0) for t in gecmis)
        wr = len(kazanan) / toplam * 100
        satirlar.append("📊 İstatistik")
        satirlar.append(f"  Toplam işlem: {toplam}  |  Kazanma: %{wr:.1f}")
        satirlar.append(f"  Brüt PnL: {brut_toplam:+.2f}$  |  Maliyet: -{toplam_komisyon+toplam_funding:.2f}$")
        satirlar.append(f"  Ortalama işlem: {gerceklesen_net/toplam:+.3f}$\n")
        satirlar.append("📋 Son 5 işlem:")
        for t in list(reversed(gecmis))[:5]:
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            sebep = t.get("not", "")
            satirlar.append(f"  {emoji} {t['symbol'].split('/')[0]:<8} {t['pnl']:+.2f}$  ({sebep})")
    else:
        satirlar.append("Henüz kapanan sanal işlem yok.")

    satirlar.append(f"\n📈 Açık pozisyon: {acik_sayi}/{MAX_POS}")
    for sym, anlik in acik_detay:
        e = "🟢" if anlik >= 0 else "🔴"
        satirlar.append(f"  {e} {sym.split('/')[0]:<8} {anlik:+.2f}$")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    return ("⚙️ PAPER BOT FIRSATÇI AYARLARI\n\n"
            "Sürüm: v1.0 (deneysel - sabit hızlı hedef stratejisi)\n\n"
            "🧪 Bu bot SANAL modda çalışır — hiçbir gerçek emir açılmaz.\n\n"
            "Giriş (paper_bot_v2 ile AYNI, kanıtlanmış filtre):\n"
            "  1) 1D trend YUKARI olmalı\n"
            "  2) 4H trend YUKARI olmalı\n"
            "  3) 1H trend YUKARI olmalı\n"
            "  4) 15m'de swing dip + dönüş onayı → LONG (SADECE LONG)\n\n"
            "⚡ ÇIKIŞ (BURASI FARKLI - iz sürme YOK):\n"
            f"  TP: SABİT %{HIZLI_HEDEF_PCT*100:.1f} hedef - değer değmez HEMEN kapanır\n"
            f"  SL: swing bazlı, taban %{MIN_SL_PCT*100:.0f}\n"
            f"  Max tutma: {MAX_HOLD_SAAT:.0f} SAAT (bekleme yok, hızlı karar)\n\n"
            f"Kaldıraç: {LEV}x (sanal) | Sanal marjin: ${SANAL_MARJIN_USDT:.2f}\n"
            f"MAX_POS: {MAX_POS}\n\n"
            "📊 BACKTEST (78 coin/~14 gün, $1 marjin ölçeğinde, komisyon dahil):\n"
            "  573 işlem, %64.4 kazanma, net +$58.10 (ort +$0.10/işlem)\n"
            "  Brüt $64.97 idi, komisyon $6.88 (%10.6) yedi.\n\n"
            "⚠️ DÜRÜSTLÜK NOTU: Bu strateji SADECE backtest edildi, hiç "
            "canlı/paper test edilmedi. Bu botun amacı tam da bunu görmek - "
            "gerçek piyasada backtest'teki gibi çalışıyor mu, yoksa MAX_POS "
            "sınırı/kayma/ani dönüşler farklı sonuç mu veriyor?")


def panel_gecmis_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "📜 Henüz kapanan sanal işlem yok."
    satirlar = ["📜 SON 15 SANAL İŞLEM\n"]
    for t in list(reversed(gecmis))[:15]:
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        sebep = {"sl": "SL", "hizli_tp": "hızlı hedef", "max_hold_timeout": "max süre"}.get(t.get("not"), t.get("not", "?"))
        satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} LONG {t['pnl']:+.2f}$ "
                         f"[{sebep}]\n   {t['zaman']} | 1D:{t.get('1d','?')}/4H:{t.get('4h','?')}/1H:{t.get('1h','?')}")
    return "\n".join(satirlar)


def panel_analiz_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "🔬 SANAL ANALİZ\n\nHenüz kapanan işlem yok."
    satirlar = ["🔬 SANAL ANALİZ\n", "🚪 Kapanış sebebine göre:"]
    for sebep in sorted(set(t.get("not", "?") for t in gecmis)):
        alt = [t for t in gecmis if t.get("not") == sebep]
        net = sum(t["pnl"] for t in alt)
        w = len([t for t in alt if t["pnl"] > 0])
        satirlar.append(f"  {sebep}: {len(alt)} işlem, %{w/len(alt)*100:.0f} kazanma, net {net:+.2f}$")

    coin_pnl = {}
    for t in gecmis:
        sym = t["symbol"].split("/")[0]
        coin_pnl[sym] = coin_pnl.get(sym, 0) + t["pnl"]
    siralanmis = sorted(coin_pnl.items(), key=lambda x: x[1], reverse=True)
    kazandiranlar = [x for x in siralanmis if x[1] > 0][:3]
    kaybettirenler = [x for x in siralanmis if x[1] < 0][-3:][::-1]
    if kazandiranlar:
        satirlar.append("\n🏆 En kazandıran coinler:")
        for sym, pnl in kazandiranlar:
            satirlar.append(f"  {sym}: {pnl:+.2f}$")
    if kaybettirenler:
        satirlar.append("💀 En kaybettiren coinler:")
        for sym, pnl in kaybettirenler:
            satirlar.append(f"  {sym}: {pnl:+.2f}$")
    return "\n".join(satirlar)


def panel_risk_metni():
    with state_lock:
        durumlar = dict(trade_state)
    satirlar = ["📉 AÇIK SANAL POZİSYON DETAYI\n"]
    if not durumlar:
        satirlar.append("Açık sanal pozisyon yok.")
        return "\n".join(satirlar)
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            pnl_pct = (guncel - entry) / entry * 100
            anlik_kar = pnl_pct / 100 * d.get("notional", NOTIONAL)
            sure_dk = (time.time() - d["acilis_zamani"]) / 60
            kalan_dk = MAX_HOLD_SAAT * 60 - sure_dk
            satirlar.append(f"{sym} LONG (1D:{d.get('1d')}/4H:{d.get('4h')}/1H:{d.get('1h')})\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f} | TP:{d['tp']:.6f}\n"
                             f"  Açık süre: {sure_dk:.0f} dk | Max tutmaya kalan: {max(0,kalan_dk):.0f} dk")
        except Exception:
            satirlar.append(f"{sym} (fiyat alınamadı)")
    return "\n".join(satirlar)


def ana_menu_klavye():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("📊 Özet", callback_data="panel_ozet"),
        telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="panel_ayarlar"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📜 Geçmiş", callback_data="panel_gecmis"),
        telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="panel_analiz"),
    )
    markup.row(telebot.types.InlineKeyboardButton("📉 Açık Pozisyon Detayı", callback_data="panel_risk"))
    markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="panel_ana"))
    return markup


def geri_butonu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="panel_ana"))
    return markup


if bot:
    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "panel_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye())
            elif veri == "panel_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "panel_risk":
                bot.edit_message_text(panel_risk_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            bot.answer_callback_query(call.id)
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"[PANEL_BUTON] {e}")
            try: bot.answer_callback_query(call.id, "Tamam")
            except Exception: pass

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_risk_metni())

    @bot.message_handler(commands=["ozet"])
    def ozet_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni())

    @bot.message_handler(commands=["sifirlagecmis"])
    def sifirlagecmis_komutu(msg):
        if not yetkili_mi(msg):
            return
        global trade_log, son_kapanis_zamani
        with log_lock:
            trade_log = []
        atomik_yaz(TRADE_LOG_PATH, [])
        with state_lock:
            acik_sayisi = len(trade_state)
            trade_state.clear()
        durumu_diske_yaz()
        with cooldown_lock:
            son_kapanis_zamani = {}
        cooldown_diske_yaz()
        bot.send_message(msg.chat.id,
            f"🗑️ TAM SIFIRLAMA tamamlandı:\n"
            f"  • İşlem geçmişi temizlendi\n"
            f"  • {acik_sayisi} açık sanal pozisyon kapatıldı (kayıtsız)\n"
            f"  • Cooldown listesi temizlendi\n\n"
            f"💼 Yeni başlangıç bakiyesi: ${BASLANGIC_BAKIYE_USDT:.2f}")

    @bot.message_handler(commands=["veri"])
    def veri_komutu(msg):
        if not yetkili_mi(msg):
            return
        with log_lock:
            veri = list(trade_log)
        if not veri:
            bot.send_message(msg.chat.id, "Henüz kapanan sanal işlem yok.")
            return
        try:
            import io
            icerik = json.dumps(veri, ensure_ascii=False, indent=2)
            dosya = io.BytesIO(icerik.encode("utf-8"))
            dosya.name = f"firsatci_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
            bot.send_document(msg.chat.id, dosya, caption=f"📦 {len(veri)} sanal işlem")
        except Exception as e:
            bot.send_message(msg.chat.id, f"⚠️ Hata: {e}")


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)


def manage_loop():
    while True:
        try:
            with state_lock:
                semboller = list(trade_state.keys())
            for sym in semboller:
                with state_lock:
                    durum = trade_state.get(sym)
                if not durum:
                    continue
                try:
                    t = exchange.fetch_ticker(sym)
                    guncel = safe(t["last"])
                except Exception:
                    continue
                if guncel <= 0:
                    continue

                if guncel <= durum["sl"]:
                    sanal_pozisyon_kapat(sym, durum["sl"], "sl")
                    continue

                if guncel >= durum["tp"]:
                    sanal_pozisyon_kapat(sym, durum["tp"], "hizli_tp")
                    continue

                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    sanal_pozisyon_kapat(sym, guncel, "max_hold_timeout")
                    continue
            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


def tarama_loop():
    tg(f"⚡ PAPER BOT FIRSATÇI v1.0 başladı - SABİT HIZLI HEDEF\n"
       f"⚠️ SANAL - hiçbir gerçek emir açılmıyor, sadece simülasyon.\n"
       f"Kural: 1D+4H+1H üçü de yükselişte olmalı, 15m swing dip + dönüş onayı.\n"
       f"MAX_POS={MAX_POS} | Sanal marjin: ${SANAL_MARJIN_USDT:.2f} | {LEV}x\n"
       f"⚡ ÇIKIŞ: SABİT %{HIZLI_HEDEF_PCT*100:.1f} hedefte HEMEN kapan (iz sürme YOK, bekleme YOK)\n"
       f"Max tutma: {MAX_HOLD_SAAT:.0f} saat (hızlı karar, uzun bekleme yok)\n\n"
       f"Backtest: 573 işlem, %64.4 kazanma, net +$58.10 ($1 marjin ölçeğinde, "
       f"78 coin/~14 gün, komisyon dahil)\n"
       f"⚠️ Bu strateji hiç canlı test edilmedi - ilk kez burada deneniyor.\n\n"
       f"📱 /panel yaz — tam menüyü görürsün.")

    while True:
        try:
            with state_lock:
                bos_slot = MAX_POS - len(trade_state)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            adaylar = aday_havuzu()
            taranacaklar = []
            for sym in adaylar:
                with state_lock:
                    if sym in trade_state:
                        continue
                if cooldown_da_mi(sym):
                    continue
                taranacaklar.append(sym)

            bulunan = 0
            if taranacaklar:
                with ThreadPoolExecutor(max_workers=4) as havuz:
                    gelecekler = {havuz.submit(ucyon_sinyal, sym): sym for sym in taranacaklar}
                    for gelecek in as_completed(gelecekler):
                        sym = gelecekler[gelecek]
                        try:
                            sinyal = gelecek.result()
                        except Exception as e:
                            log.warning(f"[TARAMA] {sym}: {e}")
                            continue
                        if sinyal:
                            with state_lock:
                                if sym in trade_state or len(trade_state) >= MAX_POS:
                                    continue
                            sanal_pozisyon_ac(sinyal)
                            bulunan += 1

            log.info(f"[NABIZ] tur tamam | havuz={len(adaylar)} | bulunan={bulunan} | acik={MAX_POS-bos_slot}/{MAX_POS}")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("PAPER BOT FIRSATÇI v1.0 (SABİT HIZLI HEDEF) BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
