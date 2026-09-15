#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
PAPER BOT — LİKİDİTE AVI SONRASI TERSİNE DÖNÜŞ (SANAL PARA)
14 Eylül 2026 (v1.0)

⚠️ BU BOT SADECE SANAL (PAPER) İŞLEM YAPAR. GERÇEK EMİR AÇMAZ,
GERÇEK PARA KULLANMAZ. Sadece halka açık piyasa verisini (OHLCV,
ticker) okuyup stratejiyi simüle eder, sonuçları diske kaydeder.

KULLANICI KARARI (14.09.2026): "Büyük oyuncular küçük traderların
stop-loss'larını tetikleyip (likidite avı) sonra gerçek yönde
pozisyon açıyor, bu haksız" gözlemi üzerine tartışıldı. Yasa dışı
karşı-manipülasyon (spoofing, sahte emir vb.) AÇIKÇA REDDEDİLDİ —
bunun yerine yasal, gözlemsel bir strateji seçildi: "avlanmanın"
kendisini bir SİNYAL olarak kullanmak.

MANTIK — LİKİDİTE AVI SONRASI TERSİNE DÖNÜŞ:
  1) Fiyat, yakın geçmişteki bir swing dip/tepe noktasını ANİ bir
     fitille kırar (stop-loss'ların toplandığı bölge tetiklenir).
     Bu anda genelde hacim anormal yüksektir (ani, yoğun satış/alım).
  2) Fiyat AYNI MUMDA ya da hemen ardından geri döner ve kırdığı
     seviyenin İÇİNE girer (kapanış, kırılan seviyenin daha "güvenli"
     tarafında). Bu, kırılımın gerçek bir trend değil, sadece stop
     avı olduğunun işaretidir (bu paternin literatürdeki adı:
     "liquidity sweep" / "stop hunt reversal" / "false breakout").
  3) Biz bu geri dönüşün YÖNÜNDE pozisyon açarız — yani avı yapanın
     değil, avın bittiği andaki gerçek hareketin tarafında oluruz.

ÖNEMLİ DÜRÜSTLÜK NOTU: Bu bir "büyük oyuncuları yenme" garantisi
DEĞİLDİR. Her ani fitil bilinçli bir "av" olmayabilir - bazen sadece
piyasa gürültüsüdür. Bu strateji henüz hiç test edilmedi (backtest
dahil) - amacı, gerçek para riske atmadan bu fikrin gerçekten işe
yarayıp yaramadığını ölçmek.

SANAL PARAMETRELER (kullanıcı isteğiyle):
  BAKIYE: 500 USDT (sanal, sabit başlangıç)
  İŞLEM BÜYÜKLÜĞÜ: 100 USDT (sabit, bileşik büyüme YOK - kullanıcı
    özellikle "hep 100 usdt olsun" dedi, yani her işlem bakiyeden
    bağımsız sabit büyüklükte)
  KALDIRAÇ: 10x (gerçek bottaki ile tutarlı, karşılaştırma kolay olsun diye)

ÇIKIŞ MANTIĞI: gerçek canlı bottan öğrenilen derslere dayanıyor:
  - Sabit hedef + kısmi kâr alma + breakeven (v3.7/v3.9'dan taşındı)
  - SL, avlanan seviyenin biraz ötesine konur (fitilin dibinin/tepesinin
    az altına/üstüne - mantık: gerçek tersine dönüşse oraya bir daha
    dönmemeli)
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
log = logging.getLogger("PAPER_LIKIDITE_AVI")

# ════════════════════════════════════════════
# CONFIG — SANAL PARAMETRELER
# ════════════════════════════════════════════
# Telegram bildirimleri opsiyonel - varsa gerçek bottaki değişkenleri
# kullanır, yoksa sadece log'a yazar (hata vermez).
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
CHAT_ID = int(os.getenv("MY_CHAT_ID", "0") or "0")

try:
    import telebot
    bot = telebot.TeleBot(TELE_TOKEN) if TELE_TOKEN else None
except ImportError:
    bot = None


def tg(msg):
    if not bot or not CHAT_ID:
        log.info(f"[TG-atlandi] {msg}")
        return
    try:
        bot.send_message(CHAT_ID, str(msg)[:4096])
    except Exception as e:
        log.warning(f"[TG] {e}")


# Borsa - SADECE HALKA AÇIK VERİ okunur (OHLCV, ticker). API anahtarı
# GEREKMEZ, hiçbir gerçek emir gönderilmez.
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

# ── LİKİDİTE AVI TESPİT PARAMETRELERİ ──
LOOKBACK_MUM = int(os.getenv("LOOKBACK_MUM", "20"))  # swing dip/tepe için geriye bakış
AVLANMA_MIN_FITIL_PCT = float(os.getenv("AVLANMA_MIN_FITIL_PCT", "0.3"))  # swing noktayı en az bu kadar kırmalı (%)
GERI_DONUS_MIN_PCT = float(os.getenv("GERI_DONUS_MIN_PCT", "0.15"))  # kapanış, kırılan seviyenin en az bu kadar içinde olmalı (%)
HACIM_TEYIT_KATSAYI = float(os.getenv("HACIM_TEYIT_KATSAYI", "1.3"))  # avlanma mumunun hacmi ortalamanın kaç katı olmalı
HACIM_TEYIT_PERIYOT = int(os.getenv("HACIM_TEYIT_PERIYOT", "20"))

# ── ÇIKIŞ PARAMETRELERİ (gerçek canlı bottan öğrenilen dersler) ──
HEDEF_PCT = float(os.getenv("HEDEF_PCT", "0.03"))  # sabit hedef %3 (likidite avı stratejisi daha hızlı/küçük hareketler hedefler)
SL_BUFFER_PCT = float(os.getenv("SL_BUFFER_PCT", "0.005"))  # fitilin ötesine ek pay
MIN_SL_PCT = float(os.getenv("MIN_SL_PCT", "0.02"))
MAX_SL_PCT = float(os.getenv("MAX_SL_PCT", "0.04"))
KISMI_KAR_ESIK_PCT = float(os.getenv("KISMI_KAR_ESIK_PCT", "0.012"))  # hedefin ~%40'ı
KISMI_KAR_ORANI = float(os.getenv("KISMI_KAR_ORANI", "0.5"))
BREAKEVEN_KOMISYON_PAYI = float(os.getenv("BREAKEVEN_KOMISYON_PAYI", "0.001"))
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "6"))
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
COOLDOWN_SAAT = 1.0

STATE_PATH = os.getenv("PAPER_STATE_PATH", "/data/paper_likidite_state.json")
LOG_PATH = os.getenv("PAPER_LOG_PATH", "/data/paper_likidite_log.json")
BAKIYE_PATH = os.getenv("PAPER_BAKIYE_PATH", "/data/paper_likidite_bakiye.json")
COOLDOWN_PATH = os.getenv("PAPER_COOLDOWN_PATH", "/data/paper_likidite_cooldown.json")

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
# VERİ ÇEKME (SADECE HALKA AÇIK ENDPOINT'LER)
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
# LİKİDİTE AVI SONRASI TERSİNE DÖNÜŞ SİNYALİ
# ════════════════════════════════════════════
def likidite_avi_sinyal(sym):
    """
    LONG sinyali: son mum, önceki LOOKBACK_MUM mumun en düşük dip
    noktasını en az AVLANMA_MIN_FITIL_PCT kadar aşağı kırar (fitil ile),
    AMA kapanışı o dip noktasının en az GERI_DONUS_MIN_PCT kadar
    ÜSTÜNDE olur (geri dönüş teyidi) VE hacim ortalamanın üstündedir.

    SHORT sinyali: bunun simetriği (tepe kırılıp geri dönüş).

    Mantık: "avlanma" (dip'in kırılıp stop'ların tetiklenmesi) gerçekleşti,
    ama fiyat orada kalmadı - geri döndü. Bu, kırılımın gerçek bir trend
    değil, sadece likidite toplama olduğunun işareti. Biz şimdi gerçek
    yönün (yukarı, çünkü aşağı kırılım sahteydi) tarafındayız.
    """
    df = get_df(sym, "15m", max(LOOKBACK_MUM, HACIM_TEYIT_PERIYOT) + 5)
    if df is None or len(df) < LOOKBACK_MUM + 2:
        return None

    pencere = df.iloc[-(LOOKBACK_MUM + 1):-1]
    son_mum = df.iloc[-1]

    onceki_dip = pencere["low"].min()
    onceki_tepe = pencere["high"].max()

    # Hacim teyidi (ortak, hem LONG hem SHORT için)
    ort_hacim = df["volume"].iloc[-(HACIM_TEYIT_PERIYOT + 1):-1].mean()
    son_hacim = son_mum["volume"]
    if pd.isna(ort_hacim) or ort_hacim <= 0:
        return None
    hacim_yeterli = son_hacim >= ort_hacim * HACIM_TEYIT_KATSAYI
    if not hacim_yeterli:
        return None

    # ── LONG: dip kırıldı, geri döndü ──
    fitil_kirilma_pct = (onceki_dip - son_mum["low"]) / onceki_dip * 100
    if fitil_kirilma_pct >= AVLANMA_MIN_FITIL_PCT:
        geri_donus_pct = (son_mum["close"] - onceki_dip) / onceki_dip * 100
        kapanis_yukselen = son_mum["close"] > son_mum["open"]
        if geri_donus_pct >= GERI_DONUS_MIN_PCT and kapanis_yukselen:
            return {
                "symbol": sym, "yon": "long",
                "entry": float(son_mum["close"]),
                "avlanma_noktasi": float(son_mum["low"]),
                "onceki_seviye": float(onceki_dip),
                "fitil_kirilma_pct": round(fitil_kirilma_pct, 3),
                "geri_donus_pct": round(geri_donus_pct, 3),
            }

    # ── SHORT: tepe kırıldı, geri döndü ──
    fitil_kirilma_pct_ust = (son_mum["high"] - onceki_tepe) / onceki_tepe * 100
    if fitil_kirilma_pct_ust >= AVLANMA_MIN_FITIL_PCT:
        geri_donus_pct = (onceki_tepe - son_mum["close"]) / onceki_tepe * 100
        kapanis_dusen = son_mum["close"] < son_mum["open"]
        if geri_donus_pct >= GERI_DONUS_MIN_PCT and kapanis_dusen:
            return {
                "symbol": sym, "yon": "short",
                "entry": float(son_mum["close"]),
                "avlanma_noktasi": float(son_mum["high"]),
                "onceki_seviye": float(onceki_tepe),
                "fitil_kirilma_pct": round(fitil_kirilma_pct_ust, 3),
                "geri_donus_pct": round(geri_donus_pct, 3),
            }

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
    avlanma_noktasi = sinyal["avlanma_noktasi"]

    # SL: avlanma noktasının biraz ötesine (mantık: gerçek tersine
    # dönüşse fiyat oraya bir daha dönmemeli)
    if long_mu:
        sl = avlanma_noktasi * (1 - SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT, (entry - sl) / entry))
        sl = entry * (1 - sl_mesafe)
    else:
        sl = avlanma_noktasi * (1 + SL_BUFFER_PCT)
        sl_mesafe = max(MIN_SL_PCT, min(MAX_SL_PCT, (sl - entry) / entry))
        sl = entry * (1 + sl_mesafe)

    tp = entry * (1 + HEDEF_PCT) if long_mu else entry * (1 - HEDEF_PCT)
    notional = SANAL_ISLEM_BUYUKLUGU_USDT * LEV
    qty = notional / entry

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl": sl, "tp": tp, "yon": yon, "qty": qty,
            "notional": notional, "acilis_zamani": time.time(),
            "kismi_alindi": False,
            "avlanma_noktasi": avlanma_noktasi, "onceki_seviye": sinyal["onceki_seviye"],
            "fitil_kirilma_pct": sinyal["fitil_kirilma_pct"], "geri_donus_pct": sinyal["geri_donus_pct"],
        }
    durumu_diske_yaz()

    yon_emoji = "🟢 LONG" if long_mu else "🔴 SHORT"
    tg(f"🎯 [PAPER] LİKİDİTE AVI SİNYALİ: {sym} {yon_emoji}\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (%{sl_mesafe*100:.1f}) | TP:{tp:.6f} (%{HEDEF_PCT*100:.1f})\n"
       f"Avlanma noktası: {avlanma_noktasi:.6f} | Önceki seviye: {sinyal['onceki_seviye']:.6f}\n"
       f"Fitil kırılma: %{sinyal['fitil_kirilma_pct']:.2f} | Geri dönüş: %{sinyal['geri_donus_pct']:.2f}\n"
       f"Sanal işlem büyüklüğü: ${SANAL_ISLEM_BUYUKLUGU_USDT:.0f} ({LEV}x) — GERÇEK PARA DEĞİL")


def sanal_pozisyon_kapat(sym, sebep, kismi_qty=None):
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

    kapatilacak_qty = kismi_qty if kismi_qty is not None else durum["qty"]
    brut_pnl = (guncel - entry) * kapatilacak_qty if long_mu else (entry - guncel) * kapatilacak_qty
    komisyon = (entry + guncel) * kapatilacak_qty * KOMISYON_PCT
    net_pnl = brut_pnl - komisyon

    trade_log_kaydet({
        "symbol": sym, "entry": entry, "exit": guncel, "pnl": net_pnl,
        "yon": durum.get("yon", "long"), "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "not": sebep, "fitil_kirilma_pct": durum.get("fitil_kirilma_pct"),
        "geri_donus_pct": durum.get("geri_donus_pct"),
    })
    yeni_bakiye = bakiye_guncelle(net_pnl)

    if kismi_qty is not None:
        kalan_qty = durum["qty"] - kismi_qty
        yeni_sl = entry * (1 + BREAKEVEN_KOMISYON_PAYI) if long_mu else entry * (1 - BREAKEVEN_KOMISYON_PAYI)
        with state_lock:
            if sym in trade_state:
                trade_state[sym]["qty"] = kalan_qty
                trade_state[sym]["sl"] = yeni_sl
                trade_state[sym]["kismi_alindi"] = True
        durumu_diske_yaz()
        tg(f"🟢 [PAPER] {sym} KISMİ KÂR ALINDI: PnL≈{net_pnl:+.2f}$ (sanal)\n"
           f"Kalan miktar için SL breakeven'e çekildi. Sanal bakiye: {yeni_bakiye:.2f}$")
    else:
        with state_lock:
            trade_state.pop(sym, None)
        durumu_diske_yaz()
        if sebep == "sl":
            cooldown_uygula(sym)
        tg(f"{'🟢' if net_pnl>=0 else '🔴'} [PAPER] {sym} kapandı [{sebep}] PnL≈{net_pnl:+.2f}$ (sanal)\n"
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

                # Kısmi kâr alma
                if not durum.get("kismi_alindi", False):
                    kismi_esik_fiyat = (durum["entry"] * (1 + KISMI_KAR_ESIK_PCT) if long_mu
                                         else durum["entry"] * (1 - KISMI_KAR_ESIK_PCT))
                    kismi_esik_gecti = (guncel >= kismi_esik_fiyat) if long_mu else (guncel <= kismi_esik_fiyat)
                    if kismi_esik_gecti:
                        kismi_qty = durum["qty"] * KISMI_KAR_ORANI
                        sanal_pozisyon_kapat(sym, "kismi_kar_alma", kismi_qty=kismi_qty)
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
        acik = len(trade_state)

    satirlar = [
        "🎯 PAPER LİKİDİTE AVI BOTU — SANAL ÖZET",
        "(GERÇEK PARA DEĞİL - simülasyon)",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💼 Sanal bakiye: {bakiye:.2f}$ (başlangıç: {SANAL_BASLANGIC_BAKIYE:.0f}$)",
        f"📈 Açık pozisyon: {acik}/{MAX_POS}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if gecmis:
        toplam = len(gecmis)
        kazanan = [t for t in gecmis if t["pnl"] > 0]
        net = sum(t["pnl"] for t in gecmis)
        wr = len(kazanan) / toplam * 100
        satirlar.append(f"Toplam işlem: {toplam} | Kazanma: %{wr:.1f}")
        satirlar.append(f"Net PnL: {net:+.2f}$ | Ortalama: {net/toplam:+.3f}$")
    else:
        satirlar.append("Henüz kapanan işlem yok.")
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
                         f"[{t.get('not','?')}]\n   {t['zaman']} | fitil:%{t.get('fitil_kirilma_pct','?')} "
                         f"geri dönüş:%{t.get('geri_donus_pct','?')}")
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
            satirlar.append(f"{sym} {yon_etiket} (fitil:%{d.get('fitil_kirilma_pct','?')} "
                             f"geri dönüş:%{d.get('geri_donus_pct','?')})\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f} | TP:{d.get('tp',0):.6f}\n"
                             f"  Kısmi kâr alındı: {'Evet' if d.get('kismi_alindi') else 'Hayır'}\n"
                             f"  Açık süre: {sure_dk:.0f} dk | Max tutmaya kalan: {max(0,kalan_dk):.0f} dk")
        except Exception:
            satirlar.append(f"{sym} (fiyat alınamadı)")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    with bakiye_lock:
        bakiye = sanal_bakiye["deger"]
    return ("⚙️ PAPER LİKİDİTE AVI BOTU AYARLARI (SANAL PARA)\n\n"
            "⚠️ Bu bot GERÇEK PARA KULLANMAZ - tüm işlemler sanaldır.\n\n"
            f"Sanal bakiye: {bakiye:.2f}$ (başlangıç: {SANAL_BASLANGIC_BAKIYE:.0f}$)\n"
            f"İşlem büyüklüğü: sabit ${SANAL_ISLEM_BUYUKLUGU_USDT:.0f} (bileşik büyüme YOK), {LEV}x kaldıraç\n"
            f"MAX_POS: {MAX_POS}\n\n"
            "Strateji: Likidite avı sonrası tersine dönüş\n"
            f"  1) Fitil, önceki {LOOKBACK_MUM} mumun dip/tepesini en az %{AVLANMA_MIN_FITIL_PCT} kırmalı\n"
            f"  2) Kapanış, kırılan seviyenin en az %{GERI_DONUS_MIN_PCT} içine geri dönmeli\n"
            f"  3) Hacim, {HACIM_TEYIT_PERIYOT} mum ortalamasının en az {HACIM_TEYIT_KATSAYI}x'i olmalı\n\n"
            "Çıkış:\n"
            f"  Kısmi kâr alma: %{KISMI_KAR_ESIK_PCT*100:.1f}'te miktarın %{KISMI_KAR_ORANI*100:.0f}'i "
            f"kapatılır, kalan SL'i breakeven'e çekilir\n"
            f"  Tam hedef: %{HEDEF_PCT*100:.1f}\n"
            f"  SL: avlanma noktası bazlı (taban %{MIN_SL_PCT*100:.0f}, tavan %{MAX_SL_PCT*100:.0f})\n"
            f"  Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
            "⚠️ Bu strateji hiç test edilmedi (backtest dahil) - amaç veriyi "
            "sanal ortamda toplayıp gerçek bir sonuca ulaşmak.")


def ana_menu_klavye():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("📊 Özet", callback_data="paper_ozet"),
        telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="paper_ayarlar"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📜 Geçmiş", callback_data="paper_gecmis"),
        telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="paper_analiz"),
    )
    markup.row(telebot.types.InlineKeyboardButton("📉 Açık Pozisyon Detayı", callback_data="paper_risk"))
    markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="paper_ana"))
    return markup


def geri_butonu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="paper_ana"))
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

    @bot.callback_query_handler(func=lambda call: call.data.startswith("paper_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "paper_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye())
            elif veri == "paper_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "paper_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "paper_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "paper_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "paper_risk":
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
    tg(f"🎯 PAPER LİKİDİTE AVI BOTU başladı — SANAL PARA (gerçek işlem AÇILMAZ)\n"
       f"Sanal bakiye: {SANAL_BASLANGIC_BAKIYE:.0f}$ | İşlem büyüklüğü: sabit {SANAL_ISLEM_BUYUKLUGU_USDT:.0f}$ ({LEV}x)\n"
       f"MAX_POS={MAX_POS}\n\n"
       f"Strateji: likidite avı sonrası tersine dönüş\n"
       f"  - Fitil, önceki dip/tepeyi en az %{AVLANMA_MIN_FITIL_PCT} kırmalı\n"
       f"  - Kapanış, kırılan seviyenin en az %{GERI_DONUS_MIN_PCT} içine geri dönmeli\n"
       f"  - Hacim, ortalamanın en az {HACIM_TEYIT_KATSAYI}x'i olmalı\n\n"
       f"Çıkış: %{KISMI_KAR_ESIK_PCT*100:.1f}'te kısmi kâr al (%{KISMI_KAR_ORANI*100:.0f}) + breakeven, "
       f"tam hedef %{HEDEF_PCT*100:.1f}\n"
       f"SL: avlanma noktasının ötesinde (taban %{MIN_SL_PCT*100:.0f}, tavan %{MAX_SL_PCT*100:.0f})\n"
       f"Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
       f"⚠️ Bu strateji hiç test edilmedi - amaç veriyi sanal ortamda toplamak.\n")

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
                    gelecekler = {havuz.submit(likidite_avi_sinyal, sym): sym for sym in taranacaklar}
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
    print("PAPER LİKİDİTE AVI BOTU BAŞLIYOR... (SANAL PARA, GERÇEK İŞLEM YOK)")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    bakiye_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
