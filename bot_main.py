#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
PAPER BOT — ÇOKLU ZAMAN DİLİMİ TREND UYUMU (SANAL PARA)
16 Eylül 2026 (v1.0)

⚠️ BU BOT SADECE SANAL (PAPER) İŞLEM YAPAR. GERÇEK EMİR AÇMAZ,
GERÇEK PARA KULLANMAZ.

KÖKEN VE DERİN ARAŞTIRMA SÜRECİ (16.09.2026):
Bu stratejiye ulaşmadan önce, gerçek Bitget verisiyle (136 coin, ~51
gün, 15 dakikalık mumlar - Bitget'in mum API'sinin sayfalama hatası
düzeltildikten sonra elde edilen DOĞRU veri) şu fikirler büyük ölçekte
test edildi ve HEPSİ NET ZARARLI çıktı:
  1) Likidite avı sonrası tersine dönüş (fitil kırılımı + geri dönüş +
     hacim teyidi): 2623 işlem, net -6323$
  2) Fonlama oranı bazlı kalabalığa karşı pozisyon: 2294 işlem, net -6507$
  3) Kırılım YÖNÜNDE devam (tersinin tersi): 3439 işlem, net -9800$
  4) Yukarıdaki stratejilerin çok sayıda TP/SL/eşik kombinasyonu
     (30+ farklı parametre seti denendi) - hiçbiri net pozitif çıkmadı.
  5) Sabit R:R denemeleri (SL'i TP'den küçük tutmak dahil, 2:1 lehte
     oran bile) - kazanma oranı (%32) o kadar düşük çıktı ki lehte R:R
     bile yetersiz kaldı.
Bu testler şunu KANITLADI: sorun "hangi yöne bahis oynadığımız" ya da
"SL/TP oranı" değildi - kullanılan GİRİŞ SİNYALLERİNİN (fiyat fitili,
fonlama oranı) kendisi piyasa yönünü rastgeleden daha iyi tahmin
etmiyordu.

SONRA DENENEN VE BAŞARILI ÇIKAN YAKLAŞIM:
Canlı botun (live_bot v3.9) zaten gerçek parada kısmi başarı gösteren
kendi mantığı - 1D+4H+1H üçlü zaman dilimi trend UYUMU + hacim teyidi +
15m swing dip/tepe girişi - aynı büyük veri setinde (ekstra API çağrısı
gerekmeden, 15m veriden resample edilerek) test edildi:
  - TP=SL=%5, trend gücü eşiği %2: 704 işlem, net +1211$, %51.7 kazanma
  - TP=%6/SL=%5, trend gücü eşiği %1: 937 işlem, net +1706$, %48.9 kazanma
KARARLILIK KONTROLÜ: TP/SL %4'ten %8'e kadar, trend gücü eşiği %0.5'ten
%4'e kadar denendi - SONUÇ HER KOMBİNASYONDA POZİTİF kaldı (net +442$
ile +1706$ arası), kazanma oranı hep %48-52 bandında istikrarlı kaldı.
Bu istikrar (komşu parametrelerde ani sıçrama olmaması), önceki
başarısız stratejilerin gösterdiği kırılganlıktan (parametre değişince
kâr/zarar tamamen tersine dönmesi) BELİRGİN ŞEKİLDE FARKLI - gerçek bir
sinyal olma ihtimalini güçlendiren bir işaret.

⚠️ DÜRÜSTLÜK NOTU: "İstikrarlı ve büyük örneklemde pozitif" demek
"garanti kazandırır" demek DEĞİLDİR. Bu hâlâ tek bir 51 günlük geçmiş
dönem - farklı piyasa rejimlerinde (örn. uzun süreli düşüş piyasası)
nasıl davranacağı bilinmiyor. Bu yüzden GERÇEK PARA DEĞİL, yine SANAL
para ile canlı ortamda test ediliyor - amaç, backtest'teki istikrarın
gerçek zamanlı, henüz görülmemiş veride de sürüp sürmediğini ölçmek.

STRATEJİ MANTIĞI:
  1) 1D trend YUKARI (ya da SHORT için AŞAĞI) - 20 periyot MA bazlı
  2) 4H trend AYNI yönde
  3) 1H trend AYNI yönde
  4) 4H trend gücü (MA'dan uzaklık) en az %1 (backtest'te en iyi denge)
  5) 15m'de swing dip/tepe + dönüş onayı (canlı botla birebir aynı)
  6) Hacim teyidi: son mum hacmi, ortalamanın en az 1.3 katı

ÇIKIŞ MANTIĞI (backtest'te en iyi/en kararlı sonucu veren):
  TP: sabit %6 (SIRALI - iz sürme yok, hedefe ulaşınca kapanır)
  SL: sabit %5 (canlı botun swing-bazlı SL'inden FARKLI - burada
      basit sabit yüzde, backtest'te bu şekilde test edildi)
  Max tutma: 8 saat (canlı botla tutarlı)

SANAL PARAMETRELER: 500 USDT bakiye, işlem başına sabit 100 USDT
marjin, 10x kaldıraç (kullanıcı talimatıyla, önceki paper bot ile
tutarlı).
════════════════════════════════════════════════════════
"""

import os
import time
import json
import logging
import threading
import sys
import ccxt
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                     stream=sys.stdout, force=True)
log = logging.getLogger("PAPER_TREND_UYUM")

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0") or "0")

try:
    import telebot
    bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None
except ImportError:
    telebot = None
    bot = None


def tg(msg):
    if not bot or not CHAT_ID:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


exchange = ccxt.bitget({
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
    "timeout": 30000,
})

SANAL_BASLANGIC_BAKIYE = float(os.getenv("SANAL_BASLANGIC_BAKIYE", "500"))
SANAL_ISLEM_BUYUKLUGU_USDT = float(os.getenv("SANAL_ISLEM_BUYUKLUGU_USDT", "100"))
LEV = int(os.getenv("LEV", "10"))
MAX_POS = int(os.getenv("MAX_POS", "3"))

SLUGGISH_BASE = {"BTC", "ETH", "XRP", "ADA", "DOGE", "BNB", "TRX", "LINK", "LTC", "BCH"}
ADAY_HAVUZU_BUYUKLUGU = 80
KONTROL_ARALIGI_SN = 60

# ── GİRİŞ PARAMETRELERİ (backtest'te en kararlı/en iyi sonucu veren) ──
MA_PERIYOT = int(os.getenv("MA_PERIYOT", "20"))
MIN_4H_TREND_GUCU_PCT = float(os.getenv("MIN_4H_TREND_GUCU_PCT", "1.0"))
LOOKBACK_15M = int(os.getenv("LOOKBACK_15M", "20"))
GIRIS_MAX_MESAFE_PCT = float(os.getenv("GIRIS_MAX_MESAFE_PCT", "0.02"))
HACIM_TEYIT_KATSAYI = float(os.getenv("HACIM_TEYIT_KATSAYI", "1.3"))
HACIM_TEYIT_PERIYOT = int(os.getenv("HACIM_TEYIT_PERIYOT", "20"))
SHORT_AKTIF = os.getenv("SHORT_AKTIF", "true").lower() == "true"

# ── ÇIKIŞ PARAMETRELERİ (backtest'te en iyi/en kararlı: TP%6, SL%5) ──
HEDEF_PCT = float(os.getenv("HEDEF_PCT", "0.06"))
SL_PCT = float(os.getenv("SL_PCT", "0.05"))
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "8"))
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
COOLDOWN_SAAT = 1.0

STATE_PATH = os.getenv("PAPER_STATE_PATH", "/data/paper_trend_state.json")
LOG_PATH = os.getenv("PAPER_LOG_PATH", "/data/paper_trend_log.json")
BAKIYE_PATH = os.getenv("PAPER_BAKIYE_PATH", "/data/paper_trend_bakiye.json")
COOLDOWN_PATH = os.getenv("PAPER_COOLDOWN_PATH", "/data/paper_trend_cooldown.json")

trade_state = {}
state_lock = threading.Lock()
acilis_rezervasyonlari = {}
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()
sanal_bakiye = {"deger": SANAL_BASLANGIC_BAKIYE}
bakiye_lock = threading.Lock()


# ════════════════════════════════════════════
# DİSK OKUMA/YAZMA
# ════════════════════════════════════════════
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
    atomik_yaz(STATE_PATH, veri)


def durumu_diskten_yukle():
    global trade_state
    trade_state = guvenli_oku(STATE_PATH, {})


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
    atomik_yaz(LOG_PATH, veri)


def trade_log_yukle():
    global trade_log
    trade_log = guvenli_oku(LOG_PATH, [])


def bakiye_diske_yaz():
    with bakiye_lock:
        veri = {"bakiye": sanal_bakiye["deger"]}
    atomik_yaz(BAKIYE_PATH, veri)


def bakiye_diskten_yukle():
    veri = guvenli_oku(BAKIYE_PATH, {"bakiye": SANAL_BASLANGIC_BAKIYE})
    with bakiye_lock:
        sanal_bakiye["deger"] = veri.get("bakiye", SANAL_BASLANGIC_BAKIYE)


def bakiye_guncelle(delta):
    with bakiye_lock:
        sanal_bakiye["deger"] += delta
        yeni = sanal_bakiye["deger"]
    bakiye_diske_yaz()
    return yeni


def cooldown_da_mi(sym):
    with cooldown_lock:
        son = son_kapanis_zamani.get(sym)
    if son is None:
        return False
    return (time.time() - son) < COOLDOWN_SAAT * 3600


def cooldown_uygula(sym):
    with cooldown_lock:
        son_kapanis_zamani[sym] = time.time()
    cooldown_diske_yaz()


def safe(x):
    try:
        return float(x)
    except Exception:
        return 0.0


# ════════════════════════════════════════════
# VERİ ÇEKME
# ════════════════════════════════════════════
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


_ticker_cache = {"veri": {}, "ts": 0}
TICKER_CACHE_SN = 30


def guncel_tickerlari_al():
    if time.time() - _ticker_cache["ts"] < TICKER_CACHE_SN and _ticker_cache["veri"]:
        return _ticker_cache["veri"]
    try:
        _ticker_cache["veri"] = exchange.fetch_tickers()
        _ticker_cache["ts"] = time.time()
    except Exception as e:
        log.warning(f"[TICKERS] {e}")
    return _ticker_cache["veri"]


def aday_havuzu():
    tickers = guncel_tickerlari_al()
    if not tickers:
        return []
    adaylar = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT:USDT"):
            continue
        base = sym.split("/")[0]
        if base in SLUGGISH_BASE:
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
# ÇOKLU ZAMAN DİLİMİ TREND UYUM SİNYALİ
# (canlı bot v3.9 ile birebir aynı mantık, backtest'te doğrulanmış
# TP/SL/eşik değerleriyle)
# ════════════════════════════════════════════
def trend_yonu(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma):
        return None
    return "yukselis" if fiyat > ma else "dusus"


def trend_gucu_pct(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma) or ma == 0:
        return None
    return (fiyat - ma) / ma * 100


def ucyon_sinyal(sym):
    df_1d = get_df(sym, "1d", MA_PERIYOT + 10)
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    df_1h = get_df(sym, "1h", MA_PERIYOT + 5)

    yon_1d = trend_yonu(df_1d)
    yon_4h = trend_yonu(df_4h)
    yon_1h = trend_yonu(df_1h)
    guc_4h = trend_gucu_pct(df_4h)

    if guc_4h is None:
        return None

    long_uyumlu = (yon_1d == "yukselis" and yon_4h == "yukselis" and yon_1h == "yukselis"
                   and guc_4h >= MIN_4H_TREND_GUCU_PCT)
    short_uyumlu = (SHORT_AKTIF and yon_1d == "dusus" and yon_4h == "dusus" and yon_1h == "dusus"
                    and guc_4h <= -MIN_4H_TREND_GUCU_PCT)

    if not long_uyumlu and not short_uyumlu:
        return None

    df_15m = get_df(sym, "15m", max(LOOKBACK_15M, HACIM_TEYIT_PERIYOT) + 5)
    if df_15m is None or len(df_15m) < LOOKBACK_15M + 2:
        return None

    pencere = df_15m.iloc[-(LOOKBACK_15M + 1):-1]
    son_mum = df_15m.iloc[-1]

    ort_hacim = df_15m["volume"].iloc[-(HACIM_TEYIT_PERIYOT + 1):-1].mean()
    if pd.isna(ort_hacim) or ort_hacim <= 0 or son_mum["volume"] < ort_hacim * HACIM_TEYIT_KATSAYI:
        return None

    if long_uyumlu:
        swing_nokta = pencere["low"].min()
        kapanis_uygun = son_mum["close"] > son_mum["open"]
        gecerli = kapanis_uygun and son_mum["close"] > swing_nokta
        if gecerli:
            mesafe = (son_mum["close"] - swing_nokta) / swing_nokta
            if mesafe <= GIRIS_MAX_MESAFE_PCT:
                return {"symbol": sym, "yon": "long", "entry": float(son_mum["close"]),
                        "swing_nokta": float(swing_nokta), "1d": yon_1d, "4h": yon_4h, "1h": yon_1h,
                        "guc_4h": round(guc_4h, 2)}

    if short_uyumlu:
        swing_nokta = pencere["high"].max()
        kapanis_uygun = son_mum["close"] < son_mum["open"]
        gecerli = kapanis_uygun and son_mum["close"] < swing_nokta
        if gecerli:
            mesafe = (swing_nokta - son_mum["close"]) / swing_nokta
            if mesafe <= GIRIS_MAX_MESAFE_PCT:
                return {"symbol": sym, "yon": "short", "entry": float(son_mum["close"]),
                        "swing_nokta": float(swing_nokta), "1d": yon_1d, "4h": yon_4h, "1h": yon_1h,
                        "guc_4h": round(guc_4h, 2)}

    return None


# ════════════════════════════════════════════
# SANAL POZİSYON AÇMA/KAPATMA
# ════════════════════════════════════════════
def sanal_pozisyon_ac(sinyal):
    sym = sinyal["symbol"]
    with state_lock:
        if sym in trade_state or sym in acilis_rezervasyonlari:
            return
        if len(trade_state) + len(acilis_rezervasyonlari) >= MAX_POS:
            return
        acilis_rezervasyonlari[sym] = True

    try:
        _sanal_pozisyon_ac_ic(sym, sinyal)
    finally:
        with state_lock:
            acilis_rezervasyonlari.pop(sym, None)


def _sanal_pozisyon_ac_ic(sym, sinyal):
    if cooldown_da_mi(sym):
        return

    yon = sinyal["yon"]
    long_mu = (yon == "long")
    entry = sinyal["entry"]

    # BACKTEST'TE DOĞRULANMIŞ: sabit yüzde SL/TP (canlı botun swing bazlı
    # SL'inden farklı - burada basit, simetriğe yakın oran kullanılıyor,
    # çünkü büyük ölçekli test bunun daha istikrarlı sonuç verdiğini gösterdi)
    sl = entry * (1 - SL_PCT) if long_mu else entry * (1 + SL_PCT)
    tp = entry * (1 + HEDEF_PCT) if long_mu else entry * (1 - HEDEF_PCT)
    notional = SANAL_ISLEM_BUYUKLUGU_USDT * LEV
    qty = notional / entry

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl": sl, "tp": tp, "yon": yon, "qty": qty,
            "notional": notional, "acilis_zamani": time.time(),
            "1d": sinyal["1d"], "4h": sinyal["4h"], "1h": sinyal["1h"], "guc_4h": sinyal["guc_4h"],
        }
    durumu_diske_yaz()

    yon_emoji = "🟢 LONG" if long_mu else "🔴 SHORT"
    tg(f"🎯 [PAPER-TREND] SİNYAL: {sym} {yon_emoji}\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (%{SL_PCT*100:.0f}) | TP:{tp:.6f} (%{HEDEF_PCT*100:.0f})\n"
       f"1D:{sinyal['1d']} 4H:{sinyal['4h']} 1H:{sinyal['1h']} | 4H güç: %{sinyal['guc_4h']:.1f}\n"
       f"Sanal işlem büyüklüğü: ${SANAL_ISLEM_BUYUKLUGU_USDT:.0f} ({LEV}x) — GERÇEK PARA DEĞİL")


def sanal_pozisyon_kapat(sym, sebep):
    with state_lock:
        durum = trade_state.get(sym)
    if not durum:
        return

    long_mu = durum.get("yon", "long") == "long"
    entry = durum["entry"]

    try:
        t = exchange.fetch_ticker(sym)
        guncel = safe(t["last"])
    except Exception as e:
        log.warning(f"[FIYAT_ALINAMADI] {sym}: {e}")
        return

    qty = durum["qty"]
    brut_pnl = (guncel - entry) * qty if long_mu else (entry - guncel) * qty
    komisyon = (entry + guncel) * qty * KOMISYON_PCT
    net_pnl = brut_pnl - komisyon

    trade_log_kaydet({
        "symbol": sym, "entry": entry, "exit": guncel, "pnl": net_pnl,
        "yon": durum.get("yon", "long"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "not": sebep, "1d": durum.get("1d"), "4h": durum.get("4h"), "1h": durum.get("1h"),
        "guc_4h": durum.get("guc_4h"),
    })
    yeni_bakiye = bakiye_guncelle(net_pnl)

    with state_lock:
        trade_state.pop(sym, None)
    durumu_diske_yaz()
    if sebep == "sl":
        cooldown_uygula(sym)
    tg(f"{'🟢' if net_pnl>=0 else '🔴'} [PAPER-TREND] {sym} kapandı [{sebep}] PnL≈{net_pnl:+.2f}$ (sanal)\n"
       f"Sanal bakiye: {yeni_bakiye:.2f}$")


# ════════════════════════════════════════════
# YÖNETİM DÖNGÜSÜ
# ════════════════════════════════════════════
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

                long_mu = durum.get("yon", "long") == "long"

                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    sanal_pozisyon_kapat(sym, "max_hold_timeout")
                    continue

                sl_tetiklendi = (guncel <= durum["sl"]) if long_mu else (guncel >= durum["sl"])
                if sl_tetiklendi:
                    sanal_pozisyon_kapat(sym, "sl")
                    continue

                tp_tetiklendi = (guncel >= durum["tp"]) if long_mu else (guncel <= durum["tp"])
                if tp_tetiklendi:
                    sanal_pozisyon_kapat(sym, "hedef")
                    continue
            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


def ozet_yaz():
    with log_lock:
        gecmis = list(trade_log)
    with bakiye_lock:
        bakiye = sanal_bakiye["deger"]
    with state_lock:
        durumlar = dict(trade_state)
    acik_sayi = len(durumlar)

    gerceklesmeyen_net = 0.0
    acik_detay = []
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            notional = d.get("notional", 0)
            long_mu = d.get("yon", "long") == "long"
            anlik = (guncel - entry) / entry * notional if long_mu else (entry - guncel) / entry * notional
            gerceklesmeyen_net += anlik
            acik_detay.append((sym, anlik))
        except Exception:
            continue

    satirlar = [
        "📈 PAPER TREND-UYUM BOTU — SANAL ÖZET",
        "(GERÇEK PARA DEĞİL - simülasyon, 1D+4H+1H trend uyumu)",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💼 Sanal bakiye: {bakiye:.2f}$ (başlangıç: {SANAL_BASLANGIC_BAKIYE:.0f}$)",
    ]
    if acik_sayi > 0:
        gc_emoji = "🟢" if gerceklesmeyen_net >= 0 else "🔴"
        satirlar.append(f"{gc_emoji} Açık pozisyonlarda (gerçekleşmemiş): {gerceklesmeyen_net:+.2f}$")
    satirlar.append("━━━━━━━━━━━━━━━━━━━━\n")

    if gecmis:
        toplam = len(gecmis)
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        net = sum(t["pnl"] for t in gecmis)
        wr = len(kazanan) / toplam * 100
        satirlar.append("📊 İstatistik")
        satirlar.append(f"  Toplam işlem: {toplam}  |  Kazanma: %{wr:.1f}")
        satirlar.append(f"  Net PnL: {net:+.2f}$  |  Ortalama: {net/toplam:+.3f}$\n")
        satirlar.append("📋 Son 5 işlem:")
        for t in list(reversed(gecmis))[:5]:
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            sebep = t.get("not", "")
            satirlar.append(f"  {emoji} {t['symbol'].split('/')[0]:<8} {t['pnl']:+.2f}$  ({sebep})")
    else:
        satirlar.append("Henüz kapanan işlem yok.")

    satirlar.append(f"\n📈 Açık pozisyon: {acik_sayi}/{MAX_POS}")
    for sym, anlik in acik_detay:
        e = "🟢" if anlik >= 0 else "🔴"
        satirlar.append(f"  {e} {sym.split('/')[0]:<8} {anlik:+.2f}$")
    return "\n".join(satirlar)


def panel_ozet_metni():
    return ozet_yaz()


def panel_gecmis_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "📜 Henüz kapanan işlem yok."
    satirlar = ["📜 SON 15 İŞLEM (SANAL)\n"]
    for t in list(reversed(gecmis))[:15]:
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        yon_etiket = "LONG" if t.get("yon", "long") == "long" else "SHORT"
        satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} {yon_etiket} {t['pnl']:+.2f}$ "
                         f"[{t.get('not','?')}]\n   {t['zaman']} | 1D:{t.get('1d','?')}/4H:{t.get('4h','?')}/1H:{t.get('1h','?')} "
                         f"| güç:%{t.get('guc_4h','?')}")
    return "\n".join(satirlar)


def panel_analiz_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "🔬 ANALİZ (SANAL)\n\nHenüz kapanan işlem yok."
    satirlar = ["🔬 ANALİZ (SANAL)\n", "🚪 Kapanış sebebine göre:"]
    for sebep in sorted(set(t.get("not", "?") for t in gecmis)):
        alt = [t for t in gecmis if t.get("not") == sebep]
        net = sum(t["pnl"] for t in alt)
        w = len([t for t in alt if t["pnl"] > 0])
        satirlar.append(f"  {sebep}: {len(alt)} işlem, %{w/len(alt)*100:.0f} kazanma, net {net:+.2f}$")

    long_islem = [t for t in gecmis if t.get("yon") == "long"]
    short_islem = [t for t in gecmis if t.get("yon") == "short"]
    if long_islem:
        satirlar.append(f"\n🟢 LONG: {len(long_islem)} işlem, net {sum(t['pnl'] for t in long_islem):+.2f}$")
    if short_islem:
        satirlar.append(f"🔴 SHORT: {len(short_islem)} işlem, net {sum(t['pnl'] for t in short_islem):+.2f}$")

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
        satirlar.append("Açık pozisyon yok.")
        return "\n".join(satirlar)
    for sym, d in durumlar.items():
        try:
            t = exchange.fetch_ticker(sym)
            guncel = safe(t["last"])
            entry = d["entry"]
            long_mu = d.get("yon", "long") == "long"
            yon_etiket = "LONG" if long_mu else "SHORT"
            pnl_pct = (guncel - entry) / entry * 100 if long_mu else (entry - guncel) / entry * 100
            anlik_kar = pnl_pct / 100 * d.get("notional", 0)
            sure_dk = (time.time() - d["acilis_zamani"]) / 60
            kalan_dk = MAX_HOLD_SAAT * 60 - sure_dk
            satirlar.append(f"{sym} {yon_etiket} (1D:{d.get('1d')}/4H:{d.get('4h')}/1H:{d.get('1h')}, güç:%{d.get('guc_4h','?')})\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f} | TP:{d.get('tp',0):.6f}\n"
                             f"  Açık süre: {sure_dk:.0f} dk | Max tutmaya kalan: {max(0,kalan_dk):.0f} dk")
        except Exception:
            satirlar.append(f"{sym} (fiyat alınamadı)")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    with bakiye_lock:
        bakiye = sanal_bakiye["deger"]
    return ("⚙️ PAPER TREND-UYUM BOTU AYARLARI (SANAL PARA)\n\n"
            "⚠️ Bu bot GERÇEK PARA KULLANMAZ - tüm işlemler sanaldır.\n\n"
            f"Sanal bakiye: {bakiye:.2f}$ (başlangıç: {SANAL_BASLANGIC_BAKIYE:.0f}$)\n"
            f"İşlem büyüklüğü: sabit ${SANAL_ISLEM_BUYUKLUGU_USDT:.0f}, {LEV}x kaldıraç\n"
            f"MAX_POS: {MAX_POS}\n\n"
            "Strateji: Çoklu zaman dilimi trend uyumu (1D+4H+1H)\n"
            f"  1) 1D, 4H, 1H üçü de AYNI yönde olmalı ({'LONG+SHORT' if SHORT_AKTIF else 'LONG-only'})\n"
            f"  2) 4H trend gücü en az %{MIN_4H_TREND_GUCU_PCT:.1f} olmalı\n"
            f"  3) 15m'de swing dip/tepe + dönüş onayı, en fazla %{GIRIS_MAX_MESAFE_PCT*100:.0f} uzaklık\n"
            f"  4) Hacim, {HACIM_TEYIT_PERIYOT} mum ortalamasının en az {HACIM_TEYIT_KATSAYI}x'i olmalı\n\n"
            "Çıkış (backtest'te en kararlı sonucu veren sabit oranlar):\n"
            f"  TP: sabit %{HEDEF_PCT*100:.0f}\n"
            f"  SL: sabit %{SL_PCT*100:.0f}\n"
            f"  Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
            "📊 BU STRATEJİNİN GEÇMİŞİ: 136 coin, ~51 günlük gerçek Bitget "
            "verisinde büyük ölçekli backtest edildi (~940 işlem), net "
            "+1706$ (sabit $100/işlem, 10x kaldıraç varsayımıyla). Komşu "
            "parametrelerde (TP/SL %4-8, güç eşiği %0.5-4) istikrarlı "
            "şekilde pozitif kaldı - bu, önceden denenen (likidite avı, "
            "fonlama oranı) stratejilerin gösterdiği kırılganlıktan farklı.\n\n"
            "⚠️ Bu geçmiş performans gelecekteki sonuçları garanti etmez - "
            "tek bir 51 günlük dönem test edildi. Bu yüzden gerçek para "
            "değil, sanal ortamda canlı test ediliyor.")


def ana_menu_klavye():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("📊 Özet", callback_data="pt_ozet"),
        telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="pt_ayarlar"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📜 Geçmiş", callback_data="pt_gecmis"),
        telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="pt_analiz"),
    )
    markup.row(telebot.types.InlineKeyboardButton("📉 Açık Pozisyon Detayı", callback_data="pt_risk"))
    markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="pt_ana"))
    return markup


def geri_butonu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="pt_ana"))
    return markup


def yetkili_mi(msg_or_call):
    if not CHAT_ID:
        return True
    try:
        chat_id = msg_or_call.message.chat.id if hasattr(msg_or_call, "message") else msg_or_call.chat.id
    except Exception:
        return False
    return chat_id == CHAT_ID


if bot:
    @bot.message_handler(commands=["panel"])
    def panel_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni(), reply_markup=ana_menu_klavye())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("pt_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "pt_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye())
            elif veri == "pt_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "pt_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "pt_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "pt_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "pt_risk":
                bot.edit_message_text(panel_risk_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            bot.answer_callback_query(call.id)
        except Exception as e:
            if "message is not modified" not in str(e):
                log.warning(f"[PANEL_BUTON] {e}")
            try: bot.answer_callback_query(call.id, "Tamam")
            except Exception: pass

    @bot.message_handler(commands=["ozet"])
    def ozet_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_ozet_metni())

    @bot.message_handler(commands=["durum"])
    def durum_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_risk_metni())

    @bot.message_handler(commands=["gecmis"])
    def gecmis_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_gecmis_metni())

    @bot.message_handler(commands=["analiz"])
    def analiz_komutu(msg):
        if not yetkili_mi(msg):
            return
        bot.send_message(msg.chat.id, panel_analiz_metni())

    @bot.message_handler(commands=["sifirlagecmis"])
    def sifirlagecmis_komutu(msg):
        if not yetkili_mi(msg):
            return
        global trade_log
        with log_lock:
            trade_log = []
        atomik_yaz(LOG_PATH, [])
        bot.send_message(msg.chat.id, "🗑️ Sanal işlem geçmişi sıfırlandı.")


def telebot_polling_baslat():
    if not bot:
        return
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30)
        except Exception as e:
            log.error(f"[TELEBOT_POLL] {e}")
            time.sleep(5)


def tarama_loop():
    tg(f"📈 PAPER TREND-UYUM BOTU v1.0 başladı — SANAL PARA (gerçek işlem AÇILMAZ)\n"
       f"Sanal bakiye: {SANAL_BASLANGIC_BAKIYE:.0f}$ | İşlem büyüklüğü: sabit {SANAL_ISLEM_BUYUKLUGU_USDT:.0f}$ ({LEV}x)\n"
       f"MAX_POS={MAX_POS}\n\n"
       f"Strateji: 1D+4H+1H trend uyumu + hacim teyidi + swing dip/tepe girişi\n"
       f"  Trend gücü eşiği: %{MIN_4H_TREND_GUCU_PCT:.1f}\n"
       f"  Sabit TP: %{HEDEF_PCT*100:.0f} | Sabit SL: %{SL_PCT*100:.0f}\n"
       f"  Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
       f"📊 Bu strateji, 136 coin/~51 gün gerçek veride büyük ölçekli "
       f"backtest edildi (~940 işlem, net +1706$) - önceki denenen "
       f"stratejilerden (likidite avı, fonlama oranı - ikisi de net "
       f"zararlıydı) farklı olarak, komşu parametrelerde İSTİKRARLI "
       f"pozitif sonuç verdi. Yine de gerçek para değil, sanal ortamda "
       f"canlı test ediliyor - geçmiş performans garanti değildir.\n\n"
       f"📱 /panel yaz — tam menüyü görürsün.")

    while True:
        try:
            with state_lock:
                bos_slot = MAX_POS - len(trade_state) - len(acilis_rezervasyonlari)
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
                                if sym in trade_state or len(trade_state) + len(acilis_rezervasyonlari) >= MAX_POS:
                                    continue
                            sanal_pozisyon_ac(sinyal)
                            bulunan += 1

            log.info(f"[NABIZ] tur tamam | havuz={len(adaylar)} | bulunan={bulunan} | "
                     f"acik={MAX_POS-bos_slot}/{MAX_POS}")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("PAPER TREND-UYUM BOTU v1.0 BAŞLIYOR... (SANAL PARA, GERÇEK İŞLEM YOK)")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    bakiye_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
