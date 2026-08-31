#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
PAPER BOT v2.3 — Üçlü Zaman Dilimi Uyumu (1D+4H+1H) + SADECE LONG
12 Ağustos 2026 (v2.0) → 20-21 Ağustos 2026 (v2.1/v2.2 güncellemeleri)

v2.1: iki kademeli trend dönüş ajanı (çoğunluk/kısmi bozulma, farklı
teyit süreleri) - sonradan kullanıcı kararıyla TREND_TERS_TEYIT_SAYISI=50
ile pratikte devre dışı bırakıldı (Railway ortam değişkeniyle).
v2.2: İZLEME LİSTESİ AJANI eklendi - genel tarama (en hareketli 80 coin)
sessizce (büyük hareket olmadan) 1D+4H uyumuna erişen coinleri
kaçırabiliyordu (backtest: sinyallerin %38'i %3'ten az 24h hareketle
oluşmuştu). Bu ajan 2/3 uyumlu coinleri ayrı, sabit bir listede (max 10)
tutup her turda tam kontrol ediyor.
KULLANICI KARARI (21.08.2026): Sanal kasa $500'e, marjin $100'e çıkarıldı
(sıfırdan başlatıldı) - daha büyük ölçekte, daha net rakamlarla test.

⚠️ BU BOT GERÇEK EMİR AÇMAZ. Sadece canlı fiyatlarla simülasyon
yapar, sonuçları kaydeder.

GEREKÇE: Şimdiye kadar 6 farklı fikir gerçek Bitget verisiyle test
edildi (trend kovalama, swing dip/tepe, FVG, likidasyon süpürme
yaklaşımı, volatilite sıkışması+kırılım, 2li zaman dilimi uyumu).
İki bulgu tekrar tekrar doğrulandı:
  1) Üst zaman dilimi trend filtresi (4H+1H uyumu) tek başına en
     büyük iyileştirmeyi sağladı (+76.64$/811 işlem, %50.1 kazanma)
  2) SHORT taraf HER testte LONG'dan belirgin zayıf çıktı

Bu bot ikisini birleştirip BİR KAT DAHA İLERİ GÖTÜRÜYOR: filtreye
1D (günlük) trend de eklenerek ÜÇLÜ uyum isteniyor, ve SADECE LONG
alınıyor. Backtest (78 coin, ~15 gün, gerçek Bitget verisi):
  290 işlem, %58.6 kazanma, net +74.44$, ortalama işlem +0.257$
  (2li uyum LONG+SHORT: 811 işlem, %50.1 kazanma, net +76.64$,
  ortalama işlem +0.094$ — bu yeni yaklaşım İŞLEM BAŞINA 2.7 KAT
  daha karlı, çok daha az işlemle neredeyse aynı toplam kârı üretti)

MANTIK:
  1) 1D trend YUKARI olmalı (20 periyot MA)
  2) 4H trend YUKARI olmalı
  3) 1H trend YUKARI olmalı
  4) Üçü de uyumlu değilse sinyal YOK
  5) 15m'de swing dip + dönüş onayı (son 20 mumun dibi son 3 mumda
     yapıldı + şu anki mum yukarı kapandı) → LONG gir

TREND DÖNÜŞ AJANI: Pozisyon açıkken 1D+4H+1H uyumu periyodik olarak
(15dk'da bir) yeniden kontrol edilir. Üçünden biri bile artık
"yukselis" değilse VE bu 2 ardışık kontrolde (30dk) teyit edilirse,
SL beklenmeden pozisyon erken kapatılır - "trend_degisti" etiketiyle.

⚠️ DÜRÜSTLÜK NOTU: Bu strateji hiç canlı test edilmedi. Backtest
sonucu umut verici ama KANITLANMIŞ değil - önceki 5 fikrin de
mantıklı görünüp gerçek performansı değişken çıktığını gördük.
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
log = logging.getLogger("PAPER_BOT_V2")

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
BASLANGIC_BAKIYE_USDT = float(os.getenv("BASLANGIC_BAKIYE_USDT", "500.0"))
# KULLANICI KARARI (21.08.2026): $50'den $500'e çıkarıldı - sanal olduğu
# için risk yok, tam sıfırlama ile birlikte.
SANAL_MARJIN_USDT = float(os.getenv("SANAL_MARJIN_USDT", "100.0"))
# KULLANICI KARARI (21.08.2026): $5'ten $100'e çıkarıldı.
LEV = 10
NOTIONAL = SANAL_MARJIN_USDT * LEV
MAX_POS = int(os.getenv("MAX_POS", "3"))

LOOKBACK_15M = 20
MA_PERIYOT = 20
SL_BUFFER_PCT = 0.015
MIN_SL_PCT = 0.05
TARGET_MAX_LOSS_USDT = float(os.getenv("TARGET_MAX_LOSS_USDT", "0.90"))
MAX_SL_PCT_TAVAN = TARGET_MAX_LOSS_USDT / NOTIONAL
# KULLANICI KARARI (22.08.2026): live_bot_v2'deki "hızlı kâr al" güncellemesiyle
# tutarlı olsun diye buraya da uygulandı - 1.0R/0.5R'den 0.4R/0.15R'ye.
IZ_SURME_R_ORANI = float(os.getenv("IZ_SURME_R_ORANI", "0.4"))
IZ_SURME_GERI_COKME_ORANI = float(os.getenv("IZ_SURME_GERI_COKME_ORANI", "0.15"))
# KISMİ KÂR ALMA (22.08.2026 kararı, kullanıcı isteğiyle "sürekli kâr alsın"):
# backtest'te test edildi (503 işlem, %76.9 kazanma, net +58.24$ - mevcut tam
# iz sürmeden [%58.6 kazanma, +74.44$] biraz daha az toplam kâr ama çok daha
# sık/hızlı, "sürekli kazanıyorum" hissi veren bir profil). Pozisyonun
# KISMI_KAPAMA_ORANI kadarı KISMI_HEDEF_R'de HEMEN kapatılır, kalanı normal
# iz sürmeyle (IZ_SURME_R_ORANI/IZ_SURME_GERI_COKME_ORANI) devam eder.
KISMI_KAPAMA_ORANI = float(os.getenv("KISMI_KAPAMA_ORANI", "0.5"))
KISMI_HEDEF_R = float(os.getenv("KISMI_HEDEF_R", "0.5"))
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
FUNDING_PCT_8SAAT = 0.0001
COOLDOWN_SAAT = 1.0
MAX_HOLD_SAAT = 24
KONTROL_ARALIGI_SN = 60
ADAY_HAVUZU_BUYUKLUGU = 80

TREND_KONTROL_ARALIGI_SN = int(os.getenv("TREND_KONTROL_ARALIGI_SN", "900"))
TREND_TERS_TEYIT_SAYISI = int(os.getenv("TREND_TERS_TEYIT_SAYISI", "2"))
TREND_TERS_TEYIT_KISMI_SAYISI = int(os.getenv("TREND_TERS_TEYIT_KISMI_SAYISI", "4"))
# KULLANICI KARARI (14.08.2026): live_bot'taki (gerçek para) iki kademeli
# mantığın aynısı buraya da uygulandı - çoğunluk (2-3 zaman dilimi) bozulunca
# hızlı teyit, sadece biri bozulunca daha uzun/temkinli teyit.

# İZLEME LİSTESİ AJANI (20.08.2026 kararı): kullanıcının önerisi - genel
# tarama listesi (aday_havuzu, en hareketli 80 coin) sessizce (büyük fiyat
# hareketi olmadan) 1D+4H uyumuna erişen coinleri kaçırabilir, çünkü skor
# 24h fiyat değişimine dayalı. Backtest analizi: geçmiş sinyallerin %38'i
# sinyal anında %3'ten az 24h hareket göstermişti. Bu ajan, genel taramadan
# BAĞIMSIZ olarak 2/3 uyumlu (1D+4H var, 1H yok) coinleri ayrı, sabit bir
# listede (max İZLEME_LISTESI_BOYUTU) tutar; her turda bu liste TAM
# kontrol edilir (1H + swing dip dahil) - 1H de uyunca son bir doğrulamayla
# (ucyon_sinyal zaten kendi içinde tüm koşulları yeniden kontrol eder)
# işlem açılır.
IZLEME_LISTESI_BOYUTU = int(os.getenv("IZLEME_LISTESI_BOYUTU", "10"))
IZLEME_TARAMA_ARALIGI_SN = int(os.getenv("IZLEME_TARAMA_ARALIGI_SN", "900"))
IZLEME_MAX_YAS_SAAT = float(os.getenv("IZLEME_MAX_YAS_SAAT", "24"))
# bir coin listede bu kadar saatten fazla kalıp hâlâ 1H uyum sağlamadıysa
# ya da 1D/4H uyumunu kaybettiyse listeden düşürülür - bayat kayıt kalmasın

TRADE_STATE_PATH = os.getenv("TRADE_STATE_PATH", "/data/paperv2_state.json")
COOLDOWN_PATH = os.getenv("COOLDOWN_PATH", "/data/paperv2_cooldown.json")
TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "/data/paperv2_log.json")

trade_state = {}
state_lock = threading.Lock()
trade_log = []
log_lock = threading.Lock()
son_kapanis_zamani = {}
cooldown_lock = threading.Lock()

izleme_listesi = {}  # sym -> {"eklenme_zamani": ts}
izleme_lock = threading.Lock()
_son_izleme_taramasi = {"ts": 0}


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


def genis_evren_listesi():
    """KULLANICI KARARI (20.08.2026, izleme listesi ajanı): aday_havuzu()
    sadece 'en hareketli' ADAY_HAVUZU_BUYUKLUGU (80) coini döner - skoru
    24h fiyat değişimine dayalı. Ama bir coin BÜYÜK bir hareket yapmadan
    sessizce 1D+4H+1H uyumuna erişiyorsa, düşük skor alıp bu listeden
    dışarıda kalabilir. Backtest analizi: geçmiş sinyallerin %38'i sinyal
    anında %3'ten AZ 24h hareket göstermişti - yani gerçek ortamda önemli
    bir kısmı kaçırılma riski taşıyor. Bu fonksiyon, hacim filtresi DIŞINDA
    hiçbir skor/sıralama uygulamadan TÜM uygun coinleri döner - izleme
    listesi ajanı bunları tarayıp erken uyum yakalayabilsin diye."""
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"[TICKERS_GENIS] {e}")
        return []
    try:
        markets = exchange.load_markets()
    except Exception:
        markets = {}
    tumu = []
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
        tumu.append(sym)
    return tumu


# ════════════════════════════════════════════
# ÜÇLÜ ZAMAN DİLİMİ UYUM SİNYALİ (1D+4H+1H) + SADECE LONG
# ════════════════════════════════════════════
def trend_yonu(df, periyot=MA_PERIYOT):
    if df is None or len(df) < periyot + 1:
        return None
    ma = df["close"].rolling(periyot).mean().iloc[-1]
    fiyat = df["close"].iloc[-1]
    if pd.isna(ma):
        return None
    return "yukselis" if fiyat > ma else "dusus"


def iki_uzerinden_uc_kontrol(sym):
    """İZLEME LİSTESİ AJANI (20.08.2026 kararı): sadece 1D+4H kontrol eder
    (1H'ye BAKMAZ) - amaç, 'neredeyse hazır' (2/3 uyumlu) coinleri ucuz bir
    kontrolle tespit edip izleme listesine almak. 1H onayı ayrıca, tam
    sinyal fonksiyonunda (ucyon_sinyal) kontrol edilir."""
    df_1d = get_df(sym, "1d", MA_PERIYOT + 10)
    df_4h = get_df(sym, "4h", MA_PERIYOT + 5)
    yon_1d = trend_yonu(df_1d)
    yon_4h = trend_yonu(df_4h)
    return yon_1d == "yukselis" and yon_4h == "yukselis"


def ucyon_sinyal(sym):
    """1D, 4H, 1H üçü de yükselişte olmalı - biri bile değilse sinyal yok.
    Üçü de uyumluysa, 15m'de swing dip + dönüş onayı aranır (SADECE LONG,
    backtest'te SHORT tarafı defalarca zayıf çıktığı için)."""
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
# SANAL (PAPER) POZİSYON AÇMA/KAPATMA - GERÇEK EMİR YOK
# ════════════════════════════════════════════
def sanal_pozisyon_ac(sinyal):
    sym = sinyal["symbol"]
    with state_lock:
        if sym in trade_state or len(trade_state) >= MAX_POS:
            return
        entry = sinyal["entry"]
        swing_nokta = sinyal["swing_nokta"]

        sl = swing_nokta * (1 - SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT_TAVAN, (entry - sl) / entry))
        sl = entry * (1 - sl_mesafe)

        r_risk = abs(entry - sl)
        trade_state[sym] = {
            "entry": entry, "sl": sl, "yon": "long", "r_risk": r_risk,
            "acilis_zamani": time.time(), "en_iyi_kar": None, "iz_aktif": False,
            "1d": sinyal["1d"], "4h": sinyal["4h"], "1h": sinyal["1h"],
            "notional": NOTIONAL, "son_trend_kontrol": 0, "ters_trend_sayisi": 0,
            # KISMİ KÂR ALMA (22.08.2026 kararı, kullanıcı isteğiyle): backtest'te
            # test edildi (503 işlem, %76.9 kazanma, net +58.24$ - mevcut tam iz
            # sürmeden [%58.6 kazanma, +74.44$] biraz daha az toplam kâr ama çok
            # daha sık/hızlı kâr alma hissi). Pozisyonun yarısı 0.5R'de HEMEN
            # kapatılır, kalan yarısı normal iz sürme (0.4R/0.15R) ile devam eder.
            "kismi_alindi": False, "kismi_pnl_toplam": 0.0,
            "orijinal_notional": NOTIONAL, "kalan_notional": NOTIONAL,
        }
    durumu_diske_yaz()
    tg(f"📝 SANAL POZİSYON (paper v2): {sym} LONG\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (%{sl_mesafe*100:.1f})\n"
       f"1D:{sinyal['1d']} | 4H:{sinyal['4h']} | 1H:{sinyal['1h']} (üçlü uyumlu)\n"
       f"📊 Kısmi kâr alma AKTİF: %{KISMI_KAPAMA_ORANI*100:.0f} pozisyon {KISMI_HEDEF_R:.1f}R'de "
       f"hızlı kapanır, kalan iz sürmeyle devam eder\n"
       f"⚠️ Gerçek emir AÇILMADI - bu sadece simülasyon.")


def sanal_pozisyon_kismi_kapat(sym, cikis_fiyat):
    """KISMİ KÂR ALMA: pozisyonu TAMAMEN kapatmaz, sadece KISMI_KAPAMA_ORANI
    kadarını hemen kapatıp ayrı bir işlem olarak kaydeder. Kalan pozisyon
    (kalan_notional güncellenerek) normal iz sürme mantığıyla açık kalmaya
    devam eder."""
    with state_lock:
        durum = trade_state.get(sym)
        if not durum or durum.get("kismi_alindi"):
            return
        entry = durum["entry"]
        orijinal_notional = durum.get("orijinal_notional", NOTIONAL)
        kapanan_notional = orijinal_notional * KISMI_KAPAMA_ORANI

        pnl_pct = (cikis_fiyat - entry) / entry
        brut_pnl = pnl_pct * kapanan_notional
        komisyon_maliyeti = KOMISYON_PCT * kapanan_notional * 2
        net_pnl = brut_pnl - komisyon_maliyeti

        durum["kismi_alindi"] = True
        durum["kalan_notional"] = orijinal_notional * (1 - KISMI_KAPAMA_ORANI)
        durum["kismi_pnl_toplam"] = net_pnl
    durumu_diske_yaz()

    trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat,
                       "brut_pnl": brut_pnl, "komisyon": komisyon_maliyeti, "funding": 0.0,
                       "pnl": net_pnl, "yon": "long", "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                       "not": "kismi_kar_alma", "1d": durum.get("1d"), "4h": durum.get("4h"), "1h": durum.get("1h")})

    emoji = "🟢" if net_pnl >= 0 else "🔴"
    tg(f"{emoji} KISMİ KÂR ALINDI: {sym} — pozisyonun %{KISMI_KAPAMA_ORANI*100:.0f}'i kapatıldı\n"
       f"Giriş:{entry:.6f} → Şimdi:{cikis_fiyat:.6f} (%{pnl_pct*100:+.2f})\n"
       f"💰 Kısmi net PnL: {net_pnl:+.2f}$\n"
       f"🔒 Kalan %{(1-KISMI_KAPAMA_ORANI)*100:.0f} pozisyon iz sürmeyle devam ediyor.")


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
    poz_notional = durum.get("kalan_notional", durum.get("notional", NOTIONAL))
    pnl_pct = (cikis_fiyat - entry) / entry
    brut_pnl = pnl_pct * poz_notional
    komisyon_maliyeti = KOMISYON_PCT * poz_notional * 2
    sure_saat = (time.time() - durum["acilis_zamani"]) / 3600
    funding_periyot = int(sure_saat // 8)
    funding_maliyeti = FUNDING_PCT_8SAAT * poz_notional * funding_periyot
    net_pnl = brut_pnl - komisyon_maliyeti - funding_maliyeti

    iz_aktif = durum.get("iz_aktif", False)
    en_iyi_kar = durum.get("en_iyi_kar")

    trade_log_kaydet({"symbol": sym, "entry": entry, "exit": cikis_fiyat,
                       "brut_pnl": brut_pnl, "komisyon": komisyon_maliyeti, "funding": funding_maliyeti,
                       "pnl": net_pnl, "yon": "long", "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                       "not": sebep, "1d": durum.get("1d"), "4h": durum.get("4h"), "1h": durum.get("1h"),
                       "iz_surme_aktifti": iz_aktif, "en_iyi_kar": en_iyi_kar})

    emoji = "🟢" if net_pnl >= 0 else "🔴"
    sebep_etiket = {"sl": "SL vuruldu", "iz_suren_tp": "İz süren TP (geri çekilme)",
                     "max_hold_timeout": "Max süre doldu", "trend_degisti": "Üst trend çoğunlukla değişti",
                     "trend_kismi_degisti": "Üst trend kısmen değişti"}.get(sebep, sebep)

    if iz_aktif and en_iyi_kar is not None:
        iz_satiri = (f"\n🔒 İz sürme: AKTİFTİ | En iyi an: {en_iyi_kar:+.2f}$ | "
                      f"Kapanışta: {net_pnl:+.2f}$ (geri çekilme: {en_iyi_kar - net_pnl:.2f}$)")
    else:
        iz_satiri = "\n🔓 İz sürme: hiç aktifleşmedi"

    funding_satiri = f" | Funding: -{funding_maliyeti:.2f}$ ({funding_periyot}x)" if funding_periyot > 0 else ""
    tg(f"{emoji} SANAL kapandı: {sym} [{sebep_etiket}]\n"
       f"Giriş:{entry:.6f} → Çıkış:{cikis_fiyat:.6f} (%{pnl_pct*100:+.2f} hareket)\n"
       f"Brüt PnL: {brut_pnl:+.2f}$ | Komisyon: -{komisyon_maliyeti:.2f}${funding_satiri}\n"
       f"💰 Net PnL: {net_pnl:+.2f}$ (simülasyon, gerçek para değil)"
       f"{iz_satiri}")


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
        "🧪 PAPER BOT v2 — CANLI ÖZET",
        "(sanal kasa, 1D+4H+1H uyum + LONG-only)",
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
    if acik_detay:
        for sym, anlik in acik_detay:
            e = "🟢" if anlik >= 0 else "🔴"
            satirlar.append(f"  {e} {sym.split('/')[0]:<8} {anlik:+.2f}$")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    with izleme_lock:
        izleme_boyut = len(izleme_listesi)
        izleme_coinler = sorted(s.split("/")[0] for s in izleme_listesi.keys())
    izleme_satiri = f"  Şu an listede: {', '.join(izleme_coinler)}" if izleme_coinler else "  Şu an liste boş"
    return ("⚙️ PAPER BOT v2 AYARLARI\n\n"
            "Sürüm: v2.2 (üçlü uyum + iki kademeli trend ajanı + izleme listesi ajanı)\n\n"
            "🧪 Bu bot SANAL modda çalışır — hiçbir gerçek emir açılmaz.\n\n"
            "Strateji: Üçlü zaman dilimi trend uyumu\n"
            "  1) 1D trend YUKARI olmalı (20 periyot MA)\n"
            "  2) 4H trend YUKARI olmalı\n"
            "  3) 1H trend YUKARI olmalı\n"
            "  4) Üçü uyumlu değilse sinyal yok\n"
            "  5) 15m'de swing dip + dönüş onayı → LONG (SADECE LONG)\n\n"
            f"Backtest (78 coin/~15 gün): 290 işlem, %58.6 kazanma, net +74.44$\n"
            f"(2li uyum LONG+SHORT: 811 işlem, %50.1 kazanma, net +76.64$ — "
            f"bu yeni yaklaşım işlem başına 2.7 kat daha karlı)\n\n"
            f"Kaldıraç: {LEV}x (sanal) | Sanal marjin: ${SANAL_MARJIN_USDT:.2f}\n"
            f"MAX_POS: {MAX_POS}\n"
            f"SL: swing bazlı, taban %{MIN_SL_PCT*100:.0f}, hedef kayıp≈${TARGET_MAX_LOSS_USDT:.2f}\n"
            f"TP: İZ SÜREN — {IZ_SURME_R_ORANI:.2f}R aktifleşme, {IZ_SURME_GERI_COKME_ORANI:.2f}R geri çekilme\n\n"
            f"🔄 TREND DÖNÜŞ AJANI: {TREND_KONTROL_ARALIGI_SN//60}dk'da bir 1D+4H+1H "
            f"uyumu tekrar kontrol edilir. Biri bile artık yükselişte değilse VE bu "
            f"{TREND_TERS_TEYIT_SAYISI} ardışık kontrolde teyit edilirse, SL beklenmeden "
            f"pozisyon erken kapatılır.\n\n"
            f"👁️ İZLEME LİSTESİ AJANI (20.08.2026 kararı): genel tarama listesi "
            f"(en hareketli {ADAY_HAVUZU_BUYUKLUGU} coin) sessizce (büyük fiyat "
            f"hareketi olmadan) 1D+4H uyumuna erişen coinleri kaçırabilir - backtest "
            f"analizi geçmiş sinyallerin %38'inin sinyal anında %3'ten az 24h hareket "
            f"gösterdiğini buldu. Bu ajan 2/3 uyumlu coinleri ayrı, sabit bir listede "
            f"(max {IZLEME_LISTESI_BOYUTU}) tutup her turda TAM kontrol eder - 1H de "
            f"uyunca son doğrulamayla işlem açar.\n"
            f"{izleme_satiri} ({izleme_boyut}/{IZLEME_LISTESI_BOYUTU})\n\n"
            "⚠️ Bu strateji hiç canlı test edilmedi - istatistiksel doğrulama yok.")


def panel_gecmis_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "📜 Henüz kapanan sanal işlem yok."
    satirlar = ["📜 SON 15 SANAL İŞLEM\n"]
    for t in list(reversed(gecmis))[:15]:
        emoji = "🟢" if t["pnl"] >= 0 else "🔴"
        sebep = {"sl": "SL", "iz_suren_tp": "iz süren TP", "max_hold_timeout": "max süre",
                 "trend_degisti": "trend çoğunlukla değişti", "trend_kismi_degisti": "trend kısmen değişti",
                 "kismi_kar_alma": "kısmi kâr alma"}.get(t.get("not"), t.get("not", "?"))
        iz_bilgi = ""
        if t.get("iz_surme_aktifti"):
            en_iyi = t.get("en_iyi_kar")
            if en_iyi is not None:
                iz_bilgi = f" | en iyi:{en_iyi:+.2f}$"
        satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} LONG {t['pnl']:+.2f}$ "
                         f"[{sebep}]{iz_bilgi}\n   {t['zaman']} | 1D:{t.get('1d','?')}/4H:{t.get('4h','?')}/1H:{t.get('1h','?')}")
    return "\n".join(satirlar)


def panel_analiz_metni():
    with log_lock:
        gecmis = list(trade_log)
    if not gecmis:
        return "🔬 SANAL ANALİZ\n\nHenüz kapanan işlem yok."
    satirlar = ["🔬 SANAL ANALİZ\n"]

    satirlar.append("🚪 Kapanış sebebine göre:")
    for sebep in sorted(set(t.get("not", "?") for t in gecmis)):
        alt = [t for t in gecmis if t.get("not") == sebep]
        net = sum(t["pnl"] for t in alt)
        w = len([t for t in alt if t["pnl"] > 0])
        satirlar.append(f"  {sebep}: {len(alt)} işlem, %{w/len(alt)*100:.0f} kazanma, net {net:+.2f}$")

    iz_aktif_olanlar = [t for t in gecmis if t.get("iz_surme_aktifti")]
    if iz_aktif_olanlar:
        satirlar.append(f"\n🔒 İz sürme aktifleşen işlemler: {len(iz_aktif_olanlar)}/{len(gecmis)}")
        toplam_geri_cekilme = sum((t.get("en_iyi_kar", 0) or 0) - t["pnl"] for t in iz_aktif_olanlar)
        satirlar.append(f"  Toplam geri çekilen kâr: {toplam_geri_cekilme:.2f}$")

    trend_degisti_olanlar = [t for t in gecmis if t.get("not") == "trend_degisti"]
    if trend_degisti_olanlar:
        net_td = sum(t["pnl"] for t in trend_degisti_olanlar)
        satirlar.append(f"\n🔄 Trend dönüş ajanı ile kapananlar: {len(trend_degisti_olanlar)} işlem, net {net_td:+.2f}$")

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
            iz_durum = "🔒 aktif" if d.get("iz_aktif") else "🔓 pasif"
            en_iyi = d.get("en_iyi_kar")
            en_iyi_metin = f", en iyi: {en_iyi:+.2f}$" if en_iyi is not None else ""
            sure_dk = (time.time() - d["acilis_zamani"]) / 60
            ters_sayac = d.get("ters_trend_sayisi", 0)
            satirlar.append(f"{sym} LONG (1D:{d.get('1d')}/4H:{d.get('4h')}/1H:{d.get('1h')})\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f}\n"
                             f"  İz sürme: {iz_durum}{en_iyi_metin}\n"
                             f"  Trend ters teyit: {ters_sayac}/{TREND_TERS_TEYIT_SAYISI}\n"
                             f"  Açık süre: {sure_dk:.0f} dk")
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
        # KULLANICI KARARI (21.08.2026): "hepsini sıfırla" isteğiyle - artık
        # sadece işlem geçmişi değil, açık (sanal) pozisyonlar, cooldown'lar
        # ve izleme listesi de temizleniyor. Sanal bir bot olduğu için
        # gerçek borsada kapatılacak bir şey yok, sadece hafıza/disk
        # kayıtları sıfırlanıyor.
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

        with izleme_lock:
            izleme_listesi.clear()

        bot.send_message(msg.chat.id,
            f"🗑️ TAM SIFIRLAMA tamamlandı:\n"
            f"  • İşlem geçmişi temizlendi\n"
            f"  • {acik_sayisi} açık sanal pozisyon kapatıldı (kayıtsız)\n"
            f"  • Cooldown listesi temizlendi\n"
            f"  • İzleme listesi temizlendi\n\n"
            f"💼 Yeni başlangıç bakiyesi: ${BASLANGIC_BAKIYE_USDT:,.2f}\n"
            f"📊 Her işlem: ${SANAL_MARJIN_USDT:,.2f} marjin ({LEV}x = ${NOTIONAL:,.2f} notional)")

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
            dosya.name = f"paperv2_log_{time.strftime('%Y%m%d_%H%M%S')}.json"
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

                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    sanal_pozisyon_kapat(sym, guncel, "max_hold_timeout")
                    continue

                # TREND DÖNÜŞ AJANI: 1D+4H+1H uyumu periyodik olarak yeniden
                # kontrol edilir. v2.1 KULLANICI KARARI (14.08.2026): live_bot'ta
                # (gerçek para) tek kademeli mantığın çok temkinli/çok gevşek
                # olabildiği görüldü - artık İKİ KADEMELİ: ÇOĞUNLUK bozulmuşsa
                # (3 zaman diliminden 2'si veya 3'ü artık yükselişte değil) daha
                # HIZLI teyit (TREND_TERS_TEYIT_SAYISI), sadece BİRİ bozulmuşsa
                # (daha zayıf/gürültülü sinyal) daha UZUN teyit
                # (TREND_TERS_TEYIT_KISMI_SAYISI) isteniyor.
                son_kontrol = durum.get("son_trend_kontrol", 0)
                if time.time() - son_kontrol >= TREND_KONTROL_ARALIGI_SN:
                    try:
                        y1d = trend_yonu(get_df(sym, "1d", MA_PERIYOT + 10))
                        y4h = trend_yonu(get_df(sym, "4h", MA_PERIYOT + 5))
                        y1h = trend_yonu(get_df(sym, "1h", MA_PERIYOT + 5))
                        bozuk_sayisi = sum(1 for y in (y1d, y4h, y1h) if y != "yukselis")
                        tam_ters = bozuk_sayisi >= 2
                        kismi_ters = bozuk_sayisi == 1

                        with state_lock:
                            if sym not in trade_state:
                                continue
                            trade_state[sym]["son_trend_kontrol"] = time.time()
                            if tam_ters:
                                trade_state[sym]["ters_trend_sayisi"] = trade_state[sym].get("ters_trend_sayisi", 0) + 1
                                trade_state[sym]["kismi_ters_sayisi"] = 0
                                sayac_tam = trade_state[sym]["ters_trend_sayisi"]
                                sayac_kismi = 0
                            elif kismi_ters:
                                trade_state[sym]["kismi_ters_sayisi"] = trade_state[sym].get("kismi_ters_sayisi", 0) + 1
                                trade_state[sym]["ters_trend_sayisi"] = 0
                                sayac_kismi = trade_state[sym]["kismi_ters_sayisi"]
                                sayac_tam = 0
                            else:
                                trade_state[sym]["ters_trend_sayisi"] = 0
                                trade_state[sym]["kismi_ters_sayisi"] = 0
                                sayac_tam = 0
                                sayac_kismi = 0

                        log.info(f"[TREND_KONTROL] {sym} 1d={y1d} 4h={y4h} 1h={y1h} bozuk={bozuk_sayisi}/3 "
                                 f"tam_ters={tam_ters} sayac_tam={sayac_tam}/{TREND_TERS_TEYIT_SAYISI} "
                                 f"kismi_ters={kismi_ters} sayac_kismi={sayac_kismi}/{TREND_TERS_TEYIT_KISMI_SAYISI}")

                        if tam_ters and sayac_tam >= TREND_TERS_TEYIT_SAYISI:
                            tg(f"⚠️ {sym} — üst trend uyumu ÇOĞUNLUKLA ({bozuk_sayisi}/3) {sayac_tam} kontrol "
                               f"boyunca ardışık bozuldu, sanal pozisyon SL beklenmeden kapatılıyor.")
                            sanal_pozisyon_kapat(sym, guncel, "trend_degisti")
                            continue
                        elif kismi_ters and sayac_kismi >= TREND_TERS_TEYIT_KISMI_SAYISI:
                            tg(f"⚠️ {sym} — üst trend KISMEN (1/3) {sayac_kismi} kontrol boyunca ardışık "
                               f"bozuldu, sanal pozisyon SL beklenmeden kapatılıyor.")
                            sanal_pozisyon_kapat(sym, guncel, "trend_kismi_degisti")
                            continue
                        elif tam_ters:
                            tg(f"👀 {sym} — üst trend ÇOĞUNLUKLA bozulmuş görünüyor ({bozuk_sayisi}/3), "
                               f"{sayac_tam}/{TREND_TERS_TEYIT_SAYISI} teyit - henüz kapatılmadı, izleniyor.")
                        elif kismi_ters:
                            tg(f"👀 {sym} — üst trend KISMEN bozulmuş görünüyor (1/3), "
                               f"{sayac_kismi}/{TREND_TERS_TEYIT_KISMI_SAYISI} teyit - henüz kapatılmadı, izleniyor.")
                    except Exception as e:
                        log.warning(f"[TREND_KONTROL_HATA] {sym}: {e}")

                if guncel <= durum["sl"]:
                    sanal_pozisyon_kapat(sym, durum["sl"], "sl")
                    continue

                entry = durum["entry"]
                r_risk = durum["r_risk"]

                # KISMİ KÂR ALMA: henüz alınmadıysa ve 0.5R hedefine
                # ulaşıldıysa, pozisyonun yarısını HEMEN kapat (bkz.
                # sanal_pozisyon_kismi_kapat). Kalan yarı aşağıdaki normal
                # iz sürme mantığıyla devam eder.
                if not durum.get("kismi_alindi", False):
                    kismi_hedef_fiyat = entry + r_risk * KISMI_HEDEF_R
                    if guncel >= kismi_hedef_fiyat:
                        sanal_pozisyon_kismi_kapat(sym, guncel)
                        with state_lock:
                            durum = trade_state.get(sym)
                        if not durum:
                            continue

                poz_notional = durum.get("kalan_notional", durum.get("notional", NOTIONAL))
                anlik_kar = (guncel - entry) / entry * poz_notional
                risk_usdt = (r_risk / entry) * poz_notional
                iz_esik = risk_usdt * IZ_SURME_R_ORANI
                gc_esik = risk_usdt * IZ_SURME_GERI_COKME_ORANI

                en_iyi = None
                if anlik_kar >= iz_esik or durum["iz_aktif"]:
                    with state_lock:
                        if sym in trade_state:
                            trade_state[sym]["iz_aktif"] = True
                            en_iyi = trade_state[sym]["en_iyi_kar"]
                            if en_iyi is None or anlik_kar > en_iyi:
                                trade_state[sym]["en_iyi_kar"] = anlik_kar
                                en_iyi = anlik_kar
                    if en_iyi is not None and anlik_kar <= en_iyi - gc_esik:
                        sanal_pozisyon_kapat(sym, guncel, "iz_suren_tp")
            time.sleep(5)
        except Exception as e:
            log.error(f"[MANAGE] {e}")
            time.sleep(5)


def izleme_listesi_guncelle():
    """İZLEME LİSTESİ AJANI: geniş evreni (tüm uygun coinler, hacim skoru
    olmadan) tarar, sadece 1D+4H uyumlu (2/3) olanları listeye ekler.
    Zaten pozisyonu açık ya da cooldown'da olan coinler atlanır. Liste
    dolu değilse yeni adaylar eklenir, doluysa en eskisi çıkarılır."""
    if time.time() - _son_izleme_taramasi["ts"] < IZLEME_TARAMA_ARALIGI_SN:
        return
    _son_izleme_taramasi["ts"] = time.time()

    try:
        genis_liste = genis_evren_listesi()
    except Exception as e:
        log.warning(f"[IZLEME_TARAMA] {e}")
        return

    with izleme_lock:
        mevcut = set(izleme_listesi.keys())
    with state_lock:
        acik = set(trade_state.keys())

    adaylar = [s for s in genis_liste if s not in mevcut and s not in acik and not cooldown_da_mi(s)]
    if not adaylar:
        return

    eklenen = 0
    with ThreadPoolExecutor(max_workers=6) as havuz:
        gelecekler = {havuz.submit(iki_uzerinden_uc_kontrol, sym): sym for sym in adaylar}
        for gelecek in as_completed(gelecekler):
            sym = gelecekler[gelecek]
            try:
                uyumlu = gelecek.result()
            except Exception as e:
                log.warning(f"[IZLEME_KONTROL] {sym}: {e}")
                continue
            if not uyumlu:
                continue
            with izleme_lock:
                if sym in izleme_listesi:
                    continue
                if len(izleme_listesi) >= IZLEME_LISTESI_BOYUTU:
                    en_eski = min(izleme_listesi.items(), key=lambda kv: kv[1]["eklenme_zamani"])
                    izleme_listesi.pop(en_eski[0], None)
                izleme_listesi[sym] = {"eklenme_zamani": time.time()}
                eklenen += 1
    if eklenen:
        log.info(f"[IZLEME_LISTESI] {eklenen} yeni coin eklendi, liste boyutu={len(izleme_listesi)}")


def izleme_listesi_kontrol():
    """İzleme listesindeki her coin için TAM sinyal kontrolü (1D+4H+1H+15m)
    yapılır - bu, kullanıcının istediği 'son kontrolü yaparak işleme gir'
    adımı: ucyon_sinyal() zaten üç zaman dilimini de sıfırdan yeniden
    doğruluyor, hiçbir varsayım/eski veri kullanılmıyor. Ayrıca 1D veya 4H
    uyumunu kaybetmiş ya da çok bayatlamış (IZLEME_MAX_YAS_SAAT) kayıtlar
    listeden temizlenir."""
    with izleme_lock:
        izlenenler = dict(izleme_listesi)
    if not izlenenler:
        return 0

    acilanlar = 0
    for sym, kayit in izlenenler.items():
        with state_lock:
            if sym in trade_state or len(trade_state) >= MAX_POS:
                continue
        if cooldown_da_mi(sym):
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            continue

        yas_saat = (time.time() - kayit["eklenme_zamani"]) / 3600
        if yas_saat > IZLEME_MAX_YAS_SAAT:
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            log.info(f"[IZLEME_LISTESI] {sym} bayatladı ({yas_saat:.1f}sa), listeden çıkarıldı")
            continue

        try:
            sinyal = ucyon_sinyal(sym)
        except Exception as e:
            log.warning(f"[IZLEME_SINYAL] {sym}: {e}")
            continue

        if sinyal:
            with izleme_lock:
                izleme_listesi.pop(sym, None)
            with state_lock:
                if sym in trade_state or len(trade_state) >= MAX_POS:
                    continue
            log.info(f"[IZLEME_LISTESI] {sym} tam uyuma ulaştı (1D+4H+1H+15m), pozisyon açılıyor")
            sanal_pozisyon_ac(sinyal)
            acilanlar += 1
        else:
            # hâlâ 1D+4H uyumlu mu diye kontrol et - değilse listeden düş
            try:
                if not iki_uzerinden_uc_kontrol(sym):
                    with izleme_lock:
                        izleme_listesi.pop(sym, None)
            except Exception:
                pass
    return acilanlar


def tarama_loop():
    tg(f"🚀 PAPER BOT v2.3 başladı - 1D+4H+1H UYUM + SADECE LONG\n"
       f"⚠️ SANAL - hiçbir gerçek emir açılmıyor, sadece simülasyon.\n"
       f"Kural: 1D+4H+1H üçü de yükselişte olmalı, sadece o zaman 15m sinyaline bakılır.\n"
       f"MAX_POS={MAX_POS} | Sanal marjin: ${SANAL_MARJIN_USDT:.2f} | {LEV}x\n"
       f"TP: iz süren, {IZ_SURME_R_ORANI}R aktifleşme, {IZ_SURME_GERI_COKME_ORANI}R geri çekilme\n"
       f"🔄 Trend dönüş ajanı: {TREND_KONTROL_ARALIGI_SN//60}dk'da bir kontrol, "
       f"{TREND_TERS_TEYIT_SAYISI} ardışık teyitte erken kapanır\n"
       f"👁️ İzleme listesi ajanı: max {IZLEME_LISTESI_BOYUTU} coin, {IZLEME_TARAMA_ARALIGI_SN//60}dk'da "
       f"bir genişletiliyor - 2/3 uyumlu (sessizce/hareket olmadan) coinleri "
       f"genel taramanın kaçırabileceği durumlar için ayrıca izler\n\n"
       f"Backtest: 290 işlem, %58.6 kazanma, net +74.44$ (78 coin/~15 gün)\n\n"
       f"📱 /panel yaz — tam menüyü görürsün.")

    while True:
        try:
            with state_lock:
                bos_slot = MAX_POS - len(trade_state)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            # İZLEME LİSTESİ AJANI: önce listeyi genişlet (periyodik, ucuz
            # 1D+4H kontrolü), sonra listedeki her coini TAM kontrol et.
            try:
                izleme_listesi_guncelle()
                izleme_acilan = izleme_listesi_kontrol()
            except Exception as e:
                log.warning(f"[IZLEME_GENEL] {e}")
                izleme_acilan = 0

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

            with izleme_lock:
                izleme_boyut = len(izleme_listesi)
            log.info(f"[NABIZ] tur tamam | havuz={len(adaylar)} | bulunan={bulunan} | "
                     f"izleme_acilan={izleme_acilan} | izleme_liste={izleme_boyut}/{IZLEME_LISTESI_BOYUTU} | "
                     f"acik={MAX_POS-bos_slot}/{MAX_POS}")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("PAPER BOT v2.3 (1D+4H+1H UYUM, izleme listesi ajanı) BAŞLIYOR...")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
