import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time

# === CONFIGURATION ===
SYMBOL             = "XAUUSDm"
TIMEFRAME          = mt5.TIMEFRAME_M1
N_BARS             = 2000       # Number of M1 bars to backtest
LOT_SIZE           = 0.1       # Adjustable lot size
PRICE_STEP         = 0.01       # Volume profile bin size
ATR_PERIOD         = 14         # ATR period
SKEW_THRESHOLD     = 0.1        # Minimum absolute skew to consider
VOL_SPIKE_FACTOR   = 1.5        # Require bar volume > factor * avg volume
TRADING_START      = time(7,5)  # UTC start time
TRADING_END        = time(20,55)# UTC end time
START_BALANCE      = 50.0       # Initial balance in USD

# === INIT MT5 ===
if not mt5.initialize():
    raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

# === FETCH HISTORICAL BARS ===
bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, N_BARS)
df_b = pd.DataFrame(bars)
df_b['time'] = pd.to_datetime(df_b['time'], unit='s')

# === CALCULATE ATR ===
df_b['tr'] = df_b[['high','low','close']].apply(
    lambda r: max(r['high']-r['low'], abs(r['high']-r['close']), abs(r['low']-r['close'])),
    axis=1)
df_b['atr'] = df_b['tr'].rolling(ATR_PERIOD).mean()

# === SKEW FUNCTION ===
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

# === GATHER FEATURES ===
records = []
for _, row in df_b.iterrows():
    if pd.isna(row['atr']):
        continue
    t = row['time'].time()
    if not (TRADING_START <= t <= TRADING_END):
        continue
    start = row['time']
    end = start + timedelta(minutes=1)
    ticks = mt5.copy_ticks_range(SYMBOL, start.to_pydatetime(), end.to_pydatetime(), mt5.COPY_TICKS_ALL)
    df_ticks = pd.DataFrame(ticks)
    if df_ticks.empty:
        continue
    bar_vol = df_ticks['volume'].sum()
    records.append({
        'time': row['time'],
        'open': row['open'], 'high': row['high'], 'low': row['low'],
        'atr': row['atr'], 'bar_vol': bar_vol, 'ticks': df_ticks
    })

df_feats = pd.DataFrame(records)
avg_vol = df_feats['bar_vol'].mean()
vol_thresh = avg_vol * VOL_SPIKE_FACTOR

# === BACKTEST ===
results = []
balance = START_BALANCE
peak = START_BALANCE
drawdowns = []

for _, r in df_feats.iterrows():
    if r['atr'] < df_b['atr'].mean():
        continue
    if r['bar_vol'] < vol_thresh:
        continue
    skew = calc_skew(r['ticks'])
    if skew is None or abs(skew) < SKEW_THRESHOLD:
        continue

    if skew > 0:
        side = 'BUY'
        pnl_points = r['high'] - r['open']
    else:
        side = 'SELL'
        pnl_points = r['open'] - r['low']

    pnl_usd = pnl_points * (LOT_SIZE / 0.01)
    balance += pnl_usd
    peak = max(peak, balance)
    dd = peak - balance
    drawdowns.append(dd)

    results.append({
        'time': r['time'], 'side': side, 'skew': skew,
        'pnl_points': pnl_points, 'net_usd': pnl_usd,
        'balance': balance
    })

df_res = pd.DataFrame(results)

# === METRICS ===
total_trades = len(df_res)
total_pnl = df_res['net_usd'].sum()
avg_pnl = df_res['net_usd'].mean()
win_rate = (df_res['net_usd'] > 0).mean()
max_drawdown = max(drawdowns) if drawdowns else 0.0

# === PRINT RESULTS ===
print("\n📊 Backtest Results for", SYMBOL)
print(f"Total trades:     {total_trades}")
print(f"Win rate:         {win_rate:.2%}")
print(f"Total PnL:        ${total_pnl:.2f}")
print(f"Avg PnL/trade:    ${avg_pnl:.4f}")
print(f"Max drawdown:     ${max_drawdown:.2f}")
print(f"Ending balance:   ${balance:.2f}")

# === SHUTDOWN ===
mt5.shutdown()
