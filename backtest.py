import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time

# === CONFIGURATION ===
SYMBOL             = "XAUUSDm"
TIMEFRAME          = mt5.TIMEFRAME_M1
N_BARS             = 2000       # number of M1 bars to backtest
PRICE_STEP         = 0.01       # volume profile bin size
ATR_PERIOD         = 14         # ATR period for volatility filter
SKEW_THRESHOLD     = 0.1        # minimum absolute skew to consider
VOL_SPIKE_FACTOR   = 1.5        # require bar volume > factor * avg volume
TRADING_START      = time(7,5)  # UTC start of trading window
TRADING_END        = time(20,55)# UTC end of trading window

# === INITIALIZE MT5 ===
if not mt5.initialize():
    raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

# === FETCH HISTORICAL BARS ===
bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, N_BARS)
df_b = pd.DataFrame(bars)
df_b['time'] = pd.to_datetime(df_b['time'], unit='s')

# === COMPUTE ATR ===
df_b['tr'] = df_b[['high','low','close']].apply(
    lambda r: max(r['high']-r['low'], abs(r['high']-r['close']), abs(r['low']-r['close'])),
    axis=1)
df_b['atr'] = df_b['tr'].rolling(ATR_PERIOD).mean()

# === FUNCTION TO CALCULATE SKEW ===
def calc_skew(df_ticks):
    if df_ticks.empty:
        return None
    df = df_ticks.copy()
    df['price'] = (df['bid'] + df['ask']) / 2
    df['volume'] = df['volume'].replace(0, 1)
    df['bin'] = (df['price'] / PRICE_STEP).round() * PRICE_STEP
    vp = df.groupby('bin')['volume'].sum().sort_index()
    if vp.empty:
        return None
    poc = vp.idxmax()
    total = vp.sum(); cum = 0.0; included = []
    for price, vol in vp.sort_values(ascending=False).items():
        cum += vol; included.append(price)
        if cum >= 0.7 * total:
            break
    val = min(included); vah = max(included)
    width = vah - val; mid = (val + vah) / 2
    return (poc - mid) / width if width > 0 else 0

# === COLLECT BAR-LEVEL FEATURES ===
records = []
for i, row in df_b.iterrows():
    if pd.isna(row['atr']):
        continue
    # Time-of-day filter
    t = row['time'].time()
    if not (TRADING_START <= t <= TRADING_END):
        continue
    # Tick data for this bar
    start = row['time']; end = start + timedelta(minutes=1)
    ticks = mt5.copy_ticks_range(SYMBOL, start.to_pydatetime(), end.to_pydatetime(), mt5.COPY_TICKS_ALL)
    df_ticks = pd.DataFrame(ticks)
    if df_ticks.empty:
        continue
    # Compute total bar volume for spike filter
    bar_vol = df_ticks['volume'].sum()
    records.append({
        'time': row['time'],
        'open': row['open'], 'high': row['high'], 'low': row['low'],
        'atr': row['atr'], 'bar_vol': bar_vol,
        'ticks': df_ticks
    })

# Build DataFrame
df_feats = pd.DataFrame(records)
# Volume spike threshold
avg_vol = df_feats['bar_vol'].mean()
vol_thresh = avg_vol * VOL_SPIKE_FACTOR

# === BACKTEST SIMULATION ===
results = []
for _, r in df_feats.iterrows():
    # ATR filter
    if r['atr'] < df_b['atr'].mean():
        continue
    # Volume spike filter
    if r['bar_vol'] < vol_thresh:
        continue
    # Compute skew
    skew = calc_skew(r['ticks'])
    if skew is None or abs(skew) < SKEW_THRESHOLD:
        continue
    # Determine PnL capturing full intrabar movement
    if skew > 0:
        side = 'BUY'
        pnl = r['high'] - r['open']
    else:
        side = 'SELL'
        pnl = r['open'] - r['low']
    results.append({'time': r['time'], 'side': side, 'skew': skew, 'pnl': pnl})

# === SUMMARY ===
df_res = pd.DataFrame(results)
print(f"Total signals: {len(df_res)}")
print(f"Total PnL: {df_res['pnl'].sum():.4f} points")
print(f"Avg PnL per trade: {df_res['pnl'].mean():.4f}")
print(f"Win rate: {(df_res['pnl'] > 0).mean():.2%}")

mt5.shutdown()
