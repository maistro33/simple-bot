#!/usr/bin/env python3
"""
HIZLANDIRILMIŞ FVG STRATEJİSİ — BACKTEST (4h/1h/15m/5m)
🔖 VERSİYON: v1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gerçek parayla çalışan FVG botunun (1d+4h+1h+15m, swing — işlemler
günlerce sürüyor) zaman dilimlerini bir kademe HIZLANDIRILMIŞ hali:

  ORİJİNAL (kanıtlanmış, gerçek para):  1 GÜNLÜK + 4 SAATLİK trend teyidi
                                        1 SAATLİK likidite süpürmesi
                                        15 DAKİKALIK FVG girişi

  BU VARYANT (TEST EDİLİYOR):           4 SAATLİK + 1 SAATLİK trend teyidi
                                        15 DAKİKALIK likidite süpürmesi
                                        5 DAKİKALIK FVG girişi

Amaç: Aynı mantığı daha kısa vadede uygulayıp işlem sıklığının artıp
artmadığını VE edge'in (kazanma oranı/R) korunup korunmadığını görmek.
Endüstri pratiği M1/M5'in çok gürültülü olduğunu söylüyor — bu test
bunun gerçekten öyle olup olmadığını BİZİM verimizle sınayacak.

ÖNEMLİ: Gerçek para KULLANMAZ. Bakış-öne hatası olmaması için mum-mum
ilerler, yönetim sinyal mumundan SONRAKİ mumdan başlar.
"""

import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta, timezone

# ════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════
BASLANGIC_TARIHI = None
BITIS_TARIHI     = None
GECMIS_GUN       = 90     # 5m veri çok yer kapladığı için daha kısa pencere

TOP_COINS        = 60
MAX_POS_BACKTEST = 5
MIN_VOLUME       = 5_000_000
BUFFER_PCT       = 0.0015
TP_SPLIT         = [0.4, 0.3, 0.3]

exchange = ccxt.bitget({"options": {"defaultType": "swap"}, "enableRateLimit": True})


# ════════════════════════════════════════════
# VERİ ÇEKME (kanıtlanmış, önceki scriptlerle aynı)
# ════════════════════════════════════════════
def gecmis_veri_cek(symbol, timeframe, baslangic_ms, bitis_ms):
    tum_mumlar = []
    since = baslangic_ms
    while True:
        try:
            mumlar = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        except Exception as e:
            print(f"  [HATA] {symbol} {timeframe}: {e}")
            break
        if not mumlar:
            break
        tum_mumlar.extend(mumlar)
        if len(mumlar) < 2:
            break
        son_zaman = mumlar[-1][0]
        if son_zaman >= bitis_ms:
            break
        yeni_since = son_zaman + 1
        if yeni_since <= since:
            break
        since = yeni_since
        time.sleep(exchange.rateLimit / 1000)
    if not tum_mumlar:
        return None
    df = pd.DataFrame(tum_mumlar, columns=["t", "o", "h", "l", "c", "v"])
    df = df.drop_duplicates(subset="t").sort_values("t").reset_index(drop=True)
    df = df[(df["t"] >= baslangic_ms) & (df["t"] <= bitis_ms)].reset_index(drop=True)
    return df


def tarih_araligi_hesapla():
    if BASLANGIC_TARIHI:
        baslangic = datetime.strptime(BASLANGIC_TARIHI, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        bitis_gecici = datetime.now(timezone.utc) if not BITIS_TARIHI else datetime.strptime(BITIS_TARIHI, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        baslangic = bitis_gecici - timedelta(days=GECMIS_GUN)
    bitis = datetime.strptime(BITIS_TARIHI, "%Y-%m-%d").replace(tzinfo=timezone.utc) if BITIS_TARIHI else datetime.now(timezone.utc)
    return int(baslangic.timestamp() * 1000), int(bitis.timestamp() * 1000)


def sembol_listesi_al(top_n, min_hacim):
    tickers = exchange.fetch_tickers()
    filtreli = []
    for sym, data in tickers.items():
        if ":USDT" not in sym:
            continue
        vol = data.get("quoteVolume") or 0
        if vol >= min_hacim:
            filtreli.append((sym, vol))
    filtreli.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in filtreli[:top_n]]


# ════════════════════════════════════════════
# SİNYAL MANTIĞI — AYNI KAVRAM, KADEME KAYDIRILMIŞ ZAMAN DİLİMLERİ
# ════════════════════════════════════════════
def yon_belirle(h4_df, h1_df, i_h4, i_h1):
    """Orijinalde 1d+4h idi — burada 4h+1h."""
    if i_h4 < 2 or i_h1 < 2:
        return None
    h4_high = h4_df["h"].iloc[i_h4 - 1]; h4_high_onceki = h4_df["h"].iloc[i_h4 - 2]
    h4_low = h4_df["l"].iloc[i_h4 - 1]; h4_low_onceki = h4_df["l"].iloc[i_h4 - 2]
    h1_high = h1_df["h"].iloc[i_h1 - 1]; h1_high_onceki = h1_df["h"].iloc[i_h1 - 2]
    h1_low = h1_df["l"].iloc[i_h1 - 1]; h1_low_onceki = h1_df["l"].iloc[i_h1 - 2]

    if h4_high > h4_high_onceki and h1_high > h1_high_onceki:
        return "long"
    if h4_low < h4_low_onceki and h1_low < h1_low_onceki:
        return "short"
    return None


def likidite_supurmesi(m15_df, i_m15, direction):
    """Orijinalde 1h idi — burada 15m."""
    if i_m15 < 30:
        return False
    pencere_low = m15_df["l"].iloc[i_m15 - 30:i_m15 - 1]
    pencere_high = m15_df["h"].iloc[i_m15 - 30:i_m15 - 1]
    son_low = m15_df["l"].iloc[i_m15 - 1]
    son_high = m15_df["h"].iloc[i_m15 - 1]
    if direction == "long":
        return son_low < pencere_low.min()
    else:
        return son_high > pencere_high.max()


def giris_modeli(m5_df, i_m5, direction):
    """Orijinalde 15m idi — burada 5m."""
    if i_m5 < 60:
        return None
    o = m5_df["o"]; h = m5_df["h"]; l = m5_df["l"]; c = m5_df["c"]

    idx = i_m5 - 1
    body = abs(c.iloc[idx] - o.iloc[idx])
    avg_body = sum(abs(c.iloc[idx - k] - o.iloc[idx - k]) for k in range(1, 10)) / 9
    if body < avg_body * 1.5:
        return None

    if direction == "long" and h.iloc[idx - 2] < l.iloc[idx]:
        entry = (h.iloc[idx - 2] + l.iloc[idx]) / 2
        swing_low = l.iloc[idx - 14: idx + 1].min()
        sl = swing_low - (swing_low * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    if direction == "short" and l.iloc[idx - 2] > h.iloc[idx]:
        entry = (l.iloc[idx - 2] + h.iloc[idx]) / 2
        swing_high = h.iloc[idx - 14: idx + 1].max()
        sl = swing_high + (swing_high * BUFFER_PCT)
        return {"entry": entry, "sl": sl}

    return None


# ════════════════════════════════════════════
# İŞLEM SİMÜLASYONU (kanıtlanmış, aynı)
# ════════════════════════════════════════════
def islemi_simule_et(m5_df, giris_idx, direction, entry, sl):
    risk = abs(entry - sl)
    if risk <= 0:
        return None
    tp1 = entry + risk if direction == "long" else entry - risk
    tp2 = entry + 2 * risk if direction == "long" else entry - 2 * risk
    tp3 = entry + 3 * risk if direction == "long" else entry - 3 * risk

    kalan = 1.0
    r_toplam = 0.0
    aktif_sl = sl
    tp1_oldu = tp2_oldu = False

    for i in range(giris_idx, len(m5_df)):
        h = m5_df["h"].iloc[i]; l = m5_df["l"].iloc[i]

        sl_vuruldu = (l <= aktif_sl) if direction == "long" else (h >= aktif_sl)
        if sl_vuruldu:
            r_bu_parca = (aktif_sl - entry) / risk if direction == "long" else (entry - aktif_sl) / risk
            r_toplam += r_bu_parca * kalan
            return {"r": r_toplam, "sure_mum": i - giris_idx, "sonuc": "SL/BE", "cikis_i": i}

        if not tp1_oldu:
            tp1_vuruldu = (h >= tp1) if direction == "long" else (l <= tp1)
            if tp1_vuruldu:
                r_toplam += 1.0 * TP_SPLIT[0]
                kalan -= TP_SPLIT[0]
                tp1_oldu = True
                aktif_sl = entry

        if tp1_oldu and not tp2_oldu:
            tp2_vuruldu = (h >= tp2) if direction == "long" else (l <= tp2)
            if tp2_vuruldu:
                r_toplam += 2.0 * TP_SPLIT[1]
                kalan -= TP_SPLIT[1]
                tp2_oldu = True

        if tp2_oldu:
            tp3_vuruldu = (h >= tp3) if direction == "long" else (l <= tp3)
            if tp3_vuruldu:
                r_toplam += 3.0 * TP_SPLIT[2]
                return {"r": r_toplam, "sure_mum": i - giris_idx, "sonuc": "TP3", "cikis_i": i}

    return {"r": r_toplam, "sure_mum": len(m5_df) - giris_idx, "sonuc": "AÇIK_KALDI(veri bitti)", "cikis_i": len(m5_df) - 1}


# ════════════════════════════════════════════
# ADIM 1: SİNYAL TOPLAMA
# ════════════════════════════════════════════
def coin_sinyalleri_bul(symbol, baslangic_ms, bitis_ms):
    print(f"[{symbol}] veri indiriliyor...")
    buffer_ms = 5 * 24 * 60 * 60 * 1000
    fetch_baslangic = baslangic_ms - buffer_ms

    h4_df = gecmis_veri_cek(symbol, "4h", fetch_baslangic, bitis_ms)
    h1_df = gecmis_veri_cek(symbol, "1h", fetch_baslangic, bitis_ms)
    m15_df = gecmis_veri_cek(symbol, "15m", fetch_baslangic, bitis_ms)
    m5_df = gecmis_veri_cek(symbol, "5m", fetch_baslangic, bitis_ms)

    if any(df is None or len(df) < 60 for df in [h4_df, h1_df, m15_df, m5_df]):
        print(f"[{symbol}] yetersiz veri, atlandı")
        return None, []

    sinyaller = []
    for i in range(60, len(m5_df)):
        simdiki_zaman = m5_df["t"].iloc[i]
        if simdiki_zaman < baslangic_ms:
            continue

        i_h4 = h4_df[h4_df["t"] <= simdiki_zaman].shape[0]
        i_h1 = h1_df[h1_df["t"] <= simdiki_zaman].shape[0]
        i_m15 = m15_df[m15_df["t"] <= simdiki_zaman].shape[0]

        direction = yon_belirle(h4_df, h1_df, i_h4, i_h1)
        if not direction:
            continue
        if not likidite_supurmesi(m15_df, i_m15, direction):
            continue
        setup = giris_modeli(m5_df, i + 1, direction)
        if not setup:
            continue

        sinyaller.append({
            "symbol": symbol, "i": i + 1, "t": simdiki_zaman,
            "direction": direction, "entry": setup["entry"], "sl": setup["sl"],
        })

    print(f"[{symbol}] {len(sinyaller)} aday sinyal bulundu")
    return m5_df, sinyaller


# ════════════════════════════════════════════
# ADIM 2: PORTFÖY SİMÜLASYONU
# ════════════════════════════════════════════
def portfoy_simulasyonu(tum_m5, tum_sinyaller, max_pos=1):
    tum_sinyaller.sort(key=lambda s: s["t"])
    islemler = []
    acik_pozisyonlar = []

    for sig in tum_sinyaller:
        acik_pozisyonlar = [bitis for bitis in acik_pozisyonlar if bitis > sig["t"]]
        if len(acik_pozisyonlar) >= max_pos:
            continue

        m5_df = tum_m5[sig["symbol"]]
        sonuc = islemi_simule_et(m5_df, sig["i"], sig["direction"], sig["entry"], sig["sl"])
        if not sonuc:
            continue

        cikis_i = sonuc["cikis_i"]
        cikis_zaman = m5_df["t"].iloc[min(cikis_i, len(m5_df) - 1)]
        sonuc["symbol"] = sig["symbol"]
        sonuc["direction"] = sig["direction"]
        sonuc["zaman"] = datetime.fromtimestamp(sig["t"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        islemler.append(sonuc)
        acik_pozisyonlar.append(cikis_zaman)

    return islemler


# ════════════════════════════════════════════
# ANA
# ════════════════════════════════════════════
def main():
    print("🔖 VERSİYON: v1 (hızlandırılmış FVG — 4h/1h/15m/5m)\n")
    baslangic_ms, bitis_ms = tarih_araligi_hesapla()
    b_str = datetime.fromtimestamp(baslangic_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    e_str = datetime.fromtimestamp(bitis_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    print(f"═══ HIZLI FVG BACKTEST — {b_str} → {e_str}, en yüksek hacimli {TOP_COINS} coin, MAX_POS={MAX_POS_BACKTEST} ═══\n")

    semboller = sembol_listesi_al(TOP_COINS, MIN_VOLUME)
    print(f"{len(semboller)} coin bulundu: {', '.join(s.split('/')[0] for s in semboller[:10])}...\n")

    tum_m5 = {}
    tum_sinyaller = []
    for sym in semboller:
        try:
            m5_df, sinyaller = coin_sinyalleri_bul(sym, baslangic_ms, bitis_ms)
            if m5_df is not None:
                tum_m5[sym] = m5_df
                tum_sinyaller.extend(sinyaller)
        except Exception as e:
            print(f"[{sym}] HATA: {e}")

    print(f"\nToplam aday sinyal: {len(tum_sinyaller)}")
    print(f"Portföy genelinde MAX_POS={MAX_POS_BACKTEST} kısıtı uygulanıyor...\n")

    tum_islemler = portfoy_simulasyonu(tum_m5, tum_sinyaller, max_pos=MAX_POS_BACKTEST)

    if not tum_islemler:
        print("\nHİÇ İŞLEM BULUNAMADI.")
        return

    df = pd.DataFrame(tum_islemler)
    kazanan = df[df["r"] > 0]
    kaybeden = df[df["r"] <= 0]

    print("\n" + "═" * 50)
    print(f"TOPLAM İŞLEM: {len(df)} (aday: {len(tum_sinyaller)}, kaçırılan: {len(tum_sinyaller)-len(df)})")
    print(f"Kazanan: {len(kazanan)} ({len(kazanan)/len(df)*100:.1f}%)")
    print(f"Kaybeden: {len(kaybeden)} ({len(kaybeden)/len(df)*100:.1f}%)")
    print(f"Toplam R: {df['r'].sum():+.2f}")
    print(f"Ortalama R/işlem: {df['r'].mean():+.3f}")
    print(f"Ortalama kazanan R: {kazanan['r'].mean():+.3f}" if len(kazanan) else "Kazanan yok")
    print(f"Ortalama kaybeden R: {kaybeden['r'].mean():+.3f}" if len(kaybeden) else "Kaybeden yok")
    print(f"Ortalama işlem süresi: {df['sure_mum'].mean()*5:.0f} dakika")
    toplam_gun = (bitis_ms - baslangic_ms) / (1000 * 60 * 60 * 24)
    print(f"Günde ortalama işlem: {len(df)/toplam_gun:.2f}")
    print("═" * 50)

    df.to_csv("fvg_hizli_backtest_sonuclar.csv", index=False)
    print("\nDetaylı sonuçlar 'fvg_hizli_backtest_sonuclar.csv' dosyasına kaydedildi.")


if __name__ == "__main__":
    main()
