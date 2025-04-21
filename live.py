import MetaTrader5 as mt5
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import time
import os

# === CONFIG ===
SYMBOL = "BTCUSDm"              # Change to "XAUUSDm" for gold
LOT_SIZE = 0.1
PRICE_STEP = 1.0                # Wider bins for clean visuals
TIMEFRAME = mt5.TIMEFRAME_M1
ATR_PERIOD = 14
VOL_COVERAGE = 0.7              # 70% value area
SKEW_THRESHOLD = 0.1            # Optional filter if you add signal logic

# === INIT ===
if not mt5.initialize():
    raise RuntimeError("MT5 init failed")

print(f"📡 Connected to MT5 for {SYMBOL}")
log_path = "vp_log.csv"

# === VOLUME PROFILE FUNCTION ===
def calc_volume_profile(df_ticks):
    df = df_ticks.copy()
    df['price'] = (df['bid'] + df['ask']) / 2
    df['bin'] = (df['price'] / PRICE_STEP).round() * PRICE_STEP
    vp = df.groupby('bin')['volume'].sum().sort_index()
    return vp

# === VALUE AREA & SKEW CALCULATION ===
def get_skew(vp):
    if vp.empty:
        return None, None, None
    poc = vp.idxmax()
    total = vp.sum()
    sorted_vp = vp.sort_values(ascending=False)
    cum = 0.0
    included = []
    for price, vol in sorted_vp.items():
        cum += vol
        included.append(price)
        if cum >= total * VOL_COVERAGE:
            break
    val = min(included)
    vah = max(included)
    mid = (val + vah) / 2
    width = vah - val
    skew = (poc - mid) / width if width > 0 else 0
    return poc, (val, vah), skew

# === PLOT FUNCTION ===
def plot_vp(vp, candle_time, poc, val_range, ohlc, skew):
    from matplotlib.ticker import FuncFormatter

    vp = vp.sort_index()
    prices = vp.index.values
    volumes = vp.values

    fig, ax = plt.subplots(figsize=(6, 10))
    ax.barh(prices, volumes, height=PRICE_STEP * 0.9, color='skyblue', label='Volume')

    # Highlight POC
    ax.axhline(poc, color='red', linestyle='--', linewidth=2, label='POC')

    # Highlight Value Area
    val_low, val_high = val_range
    ax.axhspan(val_low, val_high, color='orange', alpha=0.3, label='Value Area')

    # Annotate OHLC and skew
    text = f"Open: {ohlc['open']:.2f}\nHigh: {ohlc['high']:.2f}\nLow: {ohlc['low']:.2f}\nClose: {ohlc['close']:.2f}\nSkew: {skew:.4f}"
    ax.text(0.95, 0.02, text, transform=ax.transAxes, fontsize=9,
            verticalalignment='bottom', horizontalalignment='right',
            bbox=dict(facecolor='black', alpha=0.1), color='black')

    # Formatting
    ax.set_title(f"Volume Profile - {SYMBOL} @ {candle_time}")
    ax.set_xlabel("Volume")
    ax.set_ylabel("Price")
    ax.invert_yaxis()  # Flip Y-axis like TradingView
    ax.legend(loc='upper right')
    plt.tight_layout()
    plt.savefig("vp_plot.png")
    plt.close()
    print("📊 Volume profile saved.")

# === LIVE MONITORING LOOP ===
print("🚀 Starting live Volume Profile monitor...")
while True:
    now = datetime.utcnow()
    start = now.replace(second=0, microsecond=0)
    end = start + timedelta(minutes=1)

    # Wait until this candle ends
    while datetime.utcnow() < end:
        time.sleep(0.5)

    # === Fetch candle and ticks ===
    bars = mt5.copy_rates_range(SYMBOL, TIMEFRAME, start, end)
    if bars is None or len(bars) == 0:
        print("⚠️ No candle data.")
        continue
    bar = bars[0]
    ohlc = {
        'open': bar['open'],
        'high': bar['high'],
        'low': bar['low'],
        'close': bar['close']
    }

    ticks = mt5.copy_ticks_range(SYMBOL, start, end, mt5.COPY_TICKS_ALL)
    df_ticks = pd.DataFrame(ticks)
    if df_ticks.empty:
        print("⚠️ No ticks found.")
        continue

    # === Generate Volume Profile + Metrics ===
    vp = calc_volume_profile(df_ticks)
    poc, (val, vah), skew = get_skew(vp)
    if poc is None:
        continue

    # === Plot & Save ===
    plot_vp(vp, start.strftime("%H:%M"), poc, (val, vah), ohlc, skew)

    with open(log_path, "a") as f:
        f.write(f"{start},{poc},{val},{vah},{skew:.4f}\n")

    print(f"✅ {start.strftime('%H:%M')} | POC={poc} | VAL={val} | VAH={vah} | SKEW={skew:.4f}")
