#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════
PAPER BOT — GÜNÜN EN ÇOK YÜKSELENİ / EN VOLATİLİ, KORUMALI (SANAL PARA)
16 Eylül 2026 (v1.0) → 22 Eylül 2026 (v2.0 - korumalı)

v2.0 (22.09.2026, kullanıcı isteğiyle): Bu bot artık orijinal
paper_yukselen_bot.py (KORUMASIZ, v1.0) ile PARALEL çalışıyor - amaç
A/B karşılaştırması. Canlı bot v4.1/v4.2'de doğrulanmış iki koruma
eklendi: zirveden mesafe filtresi (tam tepede alım önlenir) + erken
güvenlik çıkışı (sürekli kontrol, kötü giden işlem büyük SL'e
dönüşmeden erken kesilir). Orijinal bot DEĞİŞTİRİLMEDİ, kontrol grubu
olarak kalıyor.

⚠️ BU BOT SADECE SANAL (PAPER) İŞLEM YAPAR. GERÇEK EMİR AÇMAZ,
GERÇEK PARA KULLANMAZ.

STRATEJİ KÖKENİ (16.09.2026, kullanıcı isteğiyle bulundu):
"Günün en çok yükselen veya volatilitesi en yüksek coinlerine gir,
küçük kâr al çık" fikri, 136 coin/~51 günlük gerçek Bitget verisinde
büyük ölçekli backtest edildi:
  - Tüm coinler arasında son 24 saatteki getirisi üst %10'luk dilimde
    olanlar seçildi, hacim teyidi + yükselen kapanışla giriş yapıldı,
    sabit %6 hedef / %6 SL ile çıkıldı.
  - Sonuç: 2283 işlem, %48.2 kazanma, NET +7254$ (sabit $100/işlem,
    10x kaldıraç varsayımıyla)
  - KARARLILIK KONTROLÜ: TP/SL %4'ten %7'ye kadar, eşik yüzdeliği
    %80'den %95'e kadar denendi - HER KOMBİNASYONDA net pozitif kaldı
    (+2230$ ile +7740$ arası). Hem "en çok yükselen" (getiri) hem "en
    volatil" (volatilite) sıralaması ayrı ayrı test edildi, ikisi de
    pozitif çıktı.
  - Bu istikrar, aynı gün büyük ölçekte test edilip BAŞARISIZ olan
    diğer fikirlerden (likidite avı sonrası tersine dönüş: net -6323$,
    fonlama oranı bazlı ters pozisyon: net -6507$) BELİRGİN ŞEKİLDE
    FARKLI - gerçek bir sinyal olma ihtimalini güçlendiren bir işaret.

MANTIK: Bu temelde bir MOMENTUM DEVAMI stratejisi - "şu anda en güçlü
hareket eden coin, kısa vadede o yönde devam etme eğiliminde olabilir"
varsayımına dayanıyor. Fitil/tersine dönüş gibi karmaşık paternler
yerine basit bir sıralama + hacim teyidi kullanıyor - bugünkü diğer
denemelerden farklı olarak basitliği bir dezavantaj değil, avantaj
gibi görünüyor.

⚠️ DÜRÜSTLÜK NOTU: "İstikrarlı ve büyük örneklemde pozitif" demek
"garanti kazandırır" demek DEĞİLDİR. Tek bir 51 günlük geçmiş dönem
test edildi. Bu yüzden GERÇEK PARA DEĞİL, sanal ortamda canlı test
ediliyor.

DİNAMİK DAVRANIŞ: Bot her tarama turunda (60 saniyede bir) TÜM coin
havuzunu yeniden sıralar - "şu an en sıcak" coinlere yönelir, sabit
bir listeye takılı kalmaz. Aynı coin arka arkaya seçilebilir ama bu
garantili değil, piyasa dinamiğine bağlıdır.

SANAL PARAMETRELER: 500 USDT bakiye, işlem başına sabit 100 USDT
marjin, 10x kaldıraç.
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
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                     stream=sys.stdout, force=True)
log = logging.getLogger("PAPER_YUKSELEN_V2")

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
KONTROL_ARALIGI_SN = 60

# ── GİRİŞ PARAMETRELERİ (backtest'te en iyi/en kararlı: getiri, üst %10) ──
SIRALAMA_TIPI = os.getenv("SIRALAMA_TIPI", "getiri")  # "getiri" ya da "volatilite"
UST_YUZDELIK = float(os.getenv("UST_YUZDELIK", "0.90"))  # üst %10'luk dilim
HACIM_TEYIT_KATSAYI = float(os.getenv("HACIM_TEYIT_KATSAYI", "1.2"))
HACIM_TEYIT_PERIYOT = int(os.getenv("HACIM_TEYIT_PERIYOT", "20"))
MIN_HACIM_USDT = float(os.getenv("MIN_HACIM_USDT", "300000"))

# ── v2 YENİ: KORUMA MEKANİZMALARI (canlı bot v4.1/v4.2'de doğrulanmış) ──
# Bu bot, orijinal paper_yukselen_bot.py'nin (korumasız kontrol grubu)
# yanında PARALEL çalışacak - amaç, "korumalı vs korumasız" karşılaştırması
# yapmak. Canlı botta HOT (-63$ tarzı) büyük tekil kayıpları önlemek için
# eklenen iki mekanizma burada da test ediliyor.
ZIRVE_LOOKBACK = int(os.getenv("ZIRVE_LOOKBACK", "20"))
ZIRVEDEN_MIN_MESAFE_PCT = float(os.getenv("ZIRVEDEN_MIN_MESAFE_PCT", "0.015"))
ERKEN_GUVENLIK_CIKISI_AKTIF = os.getenv("ERKEN_GUVENLIK_CIKISI_AKTIF", "true").lower() == "true"
ERKEN_GUVENLIK_SURE_DK = float(os.getenv("ERKEN_GUVENLIK_SURE_DK", "40"))
ERKEN_GUVENLIK_MAX_ZARAR_PCT = float(os.getenv("ERKEN_GUVENLIK_MAX_ZARAR_PCT", "1.0"))
ERKEN_GUVENLIK_MIN_ILERLEME_PCT = float(os.getenv("ERKEN_GUVENLIK_MIN_ILERLEME_PCT", "0.3"))

# ── ÇIKIŞ PARAMETRELERİ (backtest'te en iyi/en kararlı: TP=SL=%6) ──
HEDEF_PCT = float(os.getenv("HEDEF_PCT", "0.06"))
SL_PCT = float(os.getenv("SL_PCT", "0.06"))
MAX_HOLD_SAAT = float(os.getenv("MAX_HOLD_SAAT", "8"))
KOMISYON_PCT = float(os.getenv("KOMISYON_PCT", "0.0006"))
COOLDOWN_SAAT = 1.0

STATE_PATH = os.getenv("PAPER_STATE_PATH", "/data/paper_yukselen_v2_state.json")
LOG_PATH = os.getenv("PAPER_LOG_PATH", "/data/paper_yukselen_v2_log.json")
BAKIYE_PATH = os.getenv("PAPER_BAKIYE_PATH", "/data/paper_yukselen_v2_bakiye.json")
COOLDOWN_PATH = os.getenv("PAPER_COOLDOWN_PATH", "/data/paper_yukselen_v2_cooldown.json")

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


def get_df(sym, tf, limit=110):
    for deneme in range(3):
        try:
            candles = exchange.fetch_ohlcv(sym, tf, limit=limit + 1)
            if not candles or len(candles) < 2:
                return None
            candles = candles[:-1]
            df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
            time.sleep(0.05)
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


# ════════════════════════════════════════════
# GÜNÜN EN ÇOK YÜKSELENİ / EN VOLATİLİ SIRALAMASI
# ════════════════════════════════════════════
def aday_havuzu_siralanmis():
    """Tüm likit coinleri, son 24 saatteki getirilerine (ya da ticker
    üzerinden volatilite yaklaşık değerine) göre sıralar - ekstra 15m
    veri çekmeden, sadece ticker'lardaki 24s % değişim bilgisini
    kullanır (SIRALAMA_TIPI='getiri' - backtest'te en iyi çıkan
    yöntem). 'volatilite' seçilirse |değişim| kullanılır (kabaca bir
    yaklaşım - gerçek std hesabı için OHLC geçmişi gerekirdi)."""
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
        if vol < MIN_HACIM_USDT:
            continue
        chg = t.get("percentage")
        if chg is None:
            continue
        skor = chg if SIRALAMA_TIPI == "getiri" else abs(chg)
        adaylar.append((sym, skor))

    if not adaylar:
        return []
    skorlar = sorted([s for _, s in adaylar])
    esik_idx = int(len(skorlar) * UST_YUZDELIK)
    esik_idx = min(esik_idx, len(skorlar) - 1)
    esik_deger = skorlar[esik_idx]
    ust_dilim = [sym for sym, s in adaylar if s >= esik_deger]
    return ust_dilim


def giris_sinyali(sym):
    """Üst dilimdeki coin için: hacim teyidi + yükselen kapanış şartı
    + [v2 YENİ] zirveden mesafe filtresi (tam tepede alım önlenir)."""
    df = get_df(sym, "15m", max(HACIM_TEYIT_PERIYOT, 20, ZIRVE_LOOKBACK) + 5)
    if df is None or len(df) < HACIM_TEYIT_PERIYOT + 2:
        return None

    son_mum = df.iloc[-1]
    ort_hacim = df["volume"].iloc[-(HACIM_TEYIT_PERIYOT + 1):-1].mean()
    if pd.isna(ort_hacim) or ort_hacim <= 0 or son_mum["volume"] < ort_hacim * HACIM_TEYIT_KATSAYI:
        return None
    if son_mum["close"] <= son_mum["open"]:
        return None

    if len(df) >= ZIRVE_LOOKBACK:
        zirve = df["high"].iloc[-ZIRVE_LOOKBACK:].max()
        if zirve > 0:
            zirve_mesafe = (zirve - son_mum["close"]) / zirve
            if zirve_mesafe < ZIRVEDEN_MIN_MESAFE_PCT:
                return None

    return {"symbol": sym, "yon": "long", "entry": float(son_mum["close"])}


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

    entry = sinyal["entry"]
    sl = entry * (1 - SL_PCT)
    tp = entry * (1 + HEDEF_PCT)
    notional = SANAL_ISLEM_BUYUKLUGU_USDT * LEV
    qty = notional / entry

    with state_lock:
        trade_state[sym] = {
            "entry": entry, "sl": sl, "tp": tp, "yon": "long", "qty": qty,
            "notional": notional, "acilis_zamani": time.time(),
            "erken_kontrol_yapildi": False,
        }
    durumu_diske_yaz()

    tg(f"🚀 [PAPER-YUKSELEN-V2, korumalı] SİNYAL: {sym} 🟢 LONG\n"
       f"Giriş≈{entry:.6f} | SL:{sl:.6f} (%{SL_PCT*100:.0f}) | TP:{tp:.6f} (%{HEDEF_PCT*100:.0f})\n"
       f"Sıralama: {SIRALAMA_TIPI}, üst %{(1-UST_YUZDELIK)*100:.0f}'luk dilim\n"
       f"Sanal işlem büyüklüğü: ${SANAL_ISLEM_BUYUKLUGU_USDT:.0f} ({LEV}x) — GERÇEK PARA DEĞİL")


def sanal_pozisyon_kapat(sym, sebep):
    with state_lock:
        durum = trade_state.get(sym)
    if not durum:
        return

    entry = durum["entry"]
    try:
        t = exchange.fetch_ticker(sym)
        guncel = safe(t["last"])
    except Exception as e:
        log.warning(f"[FIYAT_ALINAMADI] {sym}: {e}")
        return

    qty = durum["qty"]
    brut_pnl = (guncel - entry) * qty
    komisyon = (entry + guncel) * qty * KOMISYON_PCT
    net_pnl = brut_pnl - komisyon

    trade_log_kaydet({
        "symbol": sym, "entry": entry, "exit": guncel, "pnl": net_pnl,
        "yon": "long", "zaman": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "not": sebep,
    })
    yeni_bakiye = bakiye_guncelle(net_pnl)

    with state_lock:
        trade_state.pop(sym, None)
    durumu_diske_yaz()
    if sebep in ("sl", "erken_guvenlik_cikisi"):
        cooldown_uygula(sym)
    tg(f"{'🟢' if net_pnl>=0 else '🔴'} [PAPER-YUKSELEN] {sym} kapandı [{sebep}] PnL≈{net_pnl:+.2f}$ (sanal)\n"
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

                if (time.time() - durum["acilis_zamani"]) > MAX_HOLD_SAAT * 3600:
                    sanal_pozisyon_kapat(sym, "max_hold_timeout")
                    continue

                # ── v2 YENİ: ERKEN GÜVENLİK ÇIKIŞI (sürekli kontrol) ──
                if ERKEN_GUVENLIK_CIKISI_AKTIF and not durum.get("erken_kontrol_yapildi", False):
                    gecen_dk = (time.time() - durum["acilis_zamani"]) / 60
                    ilerleme_pct = (guncel - durum["entry"]) / durum["entry"] * 100
                    if gecen_dk < ERKEN_GUVENLIK_SURE_DK:
                        if ilerleme_pct <= -ERKEN_GUVENLIK_MAX_ZARAR_PCT:
                            sanal_pozisyon_kapat(sym, "erken_guvenlik_cikisi")
                            continue
                    else:
                        if ilerleme_pct < ERKEN_GUVENLIK_MIN_ILERLEME_PCT:
                            sanal_pozisyon_kapat(sym, "erken_guvenlik_cikisi")
                            continue
                        else:
                            with state_lock:
                                if sym in trade_state:
                                    trade_state[sym]["erken_kontrol_yapildi"] = True
                            durumu_diske_yaz()

                if guncel <= durum["sl"]:
                    sanal_pozisyon_kapat(sym, "sl")
                    continue

                if guncel >= durum["tp"]:
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
            anlik = (guncel - entry) / entry * notional
            gerceklesmeyen_net += anlik
            acik_detay.append((sym, anlik))
        except Exception:
            continue

    satirlar = [
        "🚀 PAPER YÜKSELEN-COIN BOTU v2 (KORUMALI) — SANAL ÖZET",
        "(GERÇEK PARA DEĞİL - simülasyon, en çok yükselen/volatil coin)",
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
        satirlar.append(f"{emoji} {t['symbol'].split('/')[0]} LONG {t['pnl']:+.2f}$ "
                         f"[{t.get('not','?')}]\n   {t['zaman']}")
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
            pnl_pct = (guncel - entry) / entry * 100
            anlik_kar = pnl_pct / 100 * d.get("notional", 0)
            sure_dk = (time.time() - d["acilis_zamani"]) / 60
            kalan_dk = MAX_HOLD_SAAT * 60 - sure_dk
            satirlar.append(f"{sym} LONG\n"
                             f"  Giriş:{entry:.6f} Şimdi:{guncel:.6f} (%{pnl_pct:+.2f})\n"
                             f"  Anlık PnL: {anlik_kar:+.2f}$ | SL:{d['sl']:.6f} | TP:{d.get('tp',0):.6f}\n"
                             f"  Açık süre: {sure_dk:.0f} dk | Max tutmaya kalan: {max(0,kalan_dk):.0f} dk")
        except Exception:
            satirlar.append(f"{sym} (fiyat alınamadı)")
    return "\n".join(satirlar)


def panel_ayarlar_metni():
    with bakiye_lock:
        bakiye = sanal_bakiye["deger"]
    return ("⚙️ PAPER YÜKSELEN-COIN BOTU v2 - KORUMALI (SANAL PARA)\n\n""Bu bot, orijinal (korumasız) paper_yukselen_bot.py ile PARALEL çalışır - amaç A/B karşılaştırması. Zirveden mesafe filtresi + erken güvenlik çıkışı eklenmiş hali (canlı bot v4.1/v4.2'de doğrulanmış).\n\n"
            "⚠️ Bu bot GERÇEK PARA KULLANMAZ - tüm işlemler sanaldır.\n\n"
            f"Sanal bakiye: {bakiye:.2f}$ (başlangıç: {SANAL_BASLANGIC_BAKIYE:.0f}$)\n"
            f"İşlem büyüklüğü: sabit ${SANAL_ISLEM_BUYUKLUGU_USDT:.0f}, {LEV}x kaldıraç\n"
            f"MAX_POS: {MAX_POS}\n\n"
            f"Strateji: Günün en çok yükseleni/en volatili ({SIRALAMA_TIPI} bazlı)\n"
            f"  1) Tüm likit coinler arasında son 24s getirisi üst "
            f"%{(1-UST_YUZDELIK)*100:.0f}'luk dilimde olmalı\n"
            f"  2) Son 15m mum hacmi, {HACIM_TEYIT_PERIYOT} mum ortalamasının "
            f"en az {HACIM_TEYIT_KATSAYI}x'i olmalı\n"
            f"  3) Son mum yükselen kapanışlı olmalı (close > open)\n\n"
            "Çıkış (backtest'te en iyi/en kararlı sonucu veren):\n"
            f"  TP: sabit %{HEDEF_PCT*100:.0f}\n"
            f"  SL: sabit %{SL_PCT*100:.0f}\n"
            f"  Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
            "📊 BU STRATEJİNİN GEÇMİŞİ: 136 coin, ~51 günlük gerçek Bitget "
            "verisinde büyük ölçekli backtest edildi (2283 işlem), net "
            "+7254$ (sabit $100/işlem, 10x kaldıraç varsayımıyla). Eşik "
            "yüzdeliği %80-95 ve TP/SL %4-7 arasında denendi, HER "
            "KOMBİNASYONDA pozitif kaldı - kararlı bir sonuç.\n\n"
            "⚠️ Bu geçmiş performans gelecekteki sonuçları garanti etmez. "
            "Bu yüzden gerçek para değil, sanal ortamda canlı test ediliyor.\n\n"
            "🔄 DİNAMİK DAVRANIŞ: Bot her turda TÜM coin havuzunu yeniden "
            "sıralar - sabit bir coin listesine takılı kalmaz, o anda en "
            "çok yükselen/volatil olan coinlere yönelir.")


def ana_menu_klavye():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(
        telebot.types.InlineKeyboardButton("📊 Özet", callback_data="py_ozet"),
        telebot.types.InlineKeyboardButton("⚙️ Ayarlar", callback_data="py_ayarlar"),
    )
    markup.row(
        telebot.types.InlineKeyboardButton("📜 Geçmiş", callback_data="py_gecmis"),
        telebot.types.InlineKeyboardButton("🔬 Analiz", callback_data="py_analiz"),
    )
    markup.row(telebot.types.InlineKeyboardButton("📉 Açık Pozisyon Detayı", callback_data="py_risk"))
    markup.row(telebot.types.InlineKeyboardButton("🔄 Yenile", callback_data="py_ana"))
    return markup


def geri_butonu():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row(telebot.types.InlineKeyboardButton("⬅️ Menüye Dön", callback_data="py_ana"))
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

    @bot.callback_query_handler(func=lambda call: call.data.startswith("py_"))
    def panel_buton_yaniti(call):
        if not yetkili_mi(call):
            try: bot.answer_callback_query(call.id)
            except Exception: pass
            return
        veri = call.data
        try:
            if veri == "py_ana":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=ana_menu_klavye())
            elif veri == "py_ozet":
                bot.edit_message_text(panel_ozet_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "py_ayarlar":
                bot.edit_message_text(panel_ayarlar_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "py_gecmis":
                bot.edit_message_text(panel_gecmis_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "py_analiz":
                bot.edit_message_text(panel_analiz_metni(), call.message.chat.id, call.message.message_id, reply_markup=geri_butonu())
            elif veri == "py_risk":
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
    tg(f"🚀 PAPER YÜKSELEN-COIN BOTU v2 (KORUMALI) başladı — SANAL PARA (gerçek işlem AÇILMAZ)\n"f"Orijinal (korumasız) bot ile PARALEL çalışıyor - A/B karşılaştırması için.\n"f"Ek korumalar: zirveden mesafe filtresi (%{ZIRVEDEN_MIN_MESAFE_PCT*100:.1f}) + "f"erken güvenlik çıkışı (ilk {ERKEN_GUVENLIK_SURE_DK:.0f} dk, %{ERKEN_GUVENLIK_MAX_ZARAR_PCT:.1f})\n\n"
       f"Sanal bakiye: {SANAL_BASLANGIC_BAKIYE:.0f}$ | İşlem büyüklüğü: sabit {SANAL_ISLEM_BUYUKLUGU_USDT:.0f}$ ({LEV}x)\n"
       f"MAX_POS={MAX_POS}\n\n"
       f"Strateji: Günün en çok yükseleni ({SIRALAMA_TIPI} bazlı, üst %{(1-UST_YUZDELIK)*100:.0f}) "
       f"+ hacim teyidi + yükselen kapanış\n"
       f"Sabit TP: %{HEDEF_PCT*100:.0f} | Sabit SL: %{SL_PCT*100:.0f} | Max tutma: {MAX_HOLD_SAAT:.0f} saat\n\n"
       f"📊 136 coin/~51 gün gerçek veride backtest: 2283 işlem, net "
       f"+7254$. Eşik ve TP/SL aralığında (%80-95, %4-7) İSTİKRARLI "
       f"pozitif kaldı.\n"
       f"🔄 Bot her turda TÜM coin havuzunu yeniden sıralar - sabit bir "
       f"coin listesine takılı kalmaz, o anda en çok yükselen/volatil "
       f"olan coinlere yönelir.\n\n"
       f"⚠️ Geçmiş performans garanti değildir - sanal ortamda test "
       f"ediliyor.\n\n"
       f"📱 /panel yaz — tam menüyü görürsün.")

    while True:
        try:
            with state_lock:
                bos_slot = MAX_POS - len(trade_state) - len(acilis_rezervasyonlari)
            if bos_slot <= 0:
                time.sleep(KONTROL_ARALIGI_SN)
                continue

            adaylar = aday_havuzu_siralanmis()
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
                    gelecekler = {havuz.submit(giris_sinyali, sym): sym for sym in taranacaklar}
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

            log.info(f"[NABIZ] tur tamam | üst_dilim={len(adaylar)} | bulunan={bulunan} | "
                     f"acik={MAX_POS-bos_slot}/{MAX_POS}")
            time.sleep(KONTROL_ARALIGI_SN)
        except Exception as e:
            log.error(f"[TARAMA] {e}")
            time.sleep(15)


if __name__ == "__main__":
    print("PAPER YÜKSELEN-COIN BOTU v2 KORUMALI BAŞLIYOR... (SANAL PARA, GERÇEK İŞLEM YOK)")
    durumu_diskten_yukle()
    cooldown_diskten_yukle()
    bakiye_diskten_yukle()
    trade_log_yukle()
    threading.Thread(target=manage_loop, daemon=True).start()
    threading.Thread(target=telebot_polling_baslat, daemon=True).start()
    tarama_loop()
