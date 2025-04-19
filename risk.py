import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# === MT5 ACCOUNT CONFIG ===
LOGIN    = 52278049
PASSWORD = "c$O1f@g3S@hUqs"
SERVER   = "ICMarketsSC-Demo"
MT5_PATH = "C:/Program Files/MetaTrader 5 IC Markets Global/terminal64.exe"
SYMBOL   = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M5  # 5-minute
RR_RATIO = 2.0
RISK_PER_TRADE = 0.03  # 3%

# === INIT CONNECTION ===
mt5.initialize(path=MT5_PATH, login=LOGIN, password=PASSWORD, server=SERVER)
if not mt5.initialize():
    raise SystemExit("❌ MT5 initialization failed")

# === FETCH HISTORICAL CANDLES (LAST 30 DAYS) ===
end = datetime.now()
start = end - timedelta(days=30)
rates = mt5.copy_rates_range(SYMBOL, TIMEFRAME, start, end)

if rates is None or len(rates) == 0:
    raise SystemExit("❌ Failed to retrieve historical data")

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)

# === STRATEGY ===
df['ema_fast'] = df['close'].ewm(span=9).mean()
df['ema_slow'] = df['close'].ewm(span=21).mean()

df['signal'] = np.where((df['close'] > df['ema_fast']) & (df['ema_fast'] > df['ema_slow']), 'BUY',
                np.where((df['close'] < df['ema_fast']) & (df['ema_fast'] < df['ema_slow']), 'SELL', None))

entries = []
results = []

for i in range(1, len(df)):
    row = df.iloc[i]
    if row['signal'] and df.iloc[i - 1]['signal'] != row['signal']:
        entry_price = row['close']
        sl = entry_price - 100 if row['signal'] == 'BUY' else entry_price + 100
        tp = entry_price + (RR_RATIO * 100) if row['signal'] == 'BUY' else entry_price - (RR_RATIO * 100)
        entries.append({
            'entry_time': row.name,
            'direction': row['signal'],
            'entry': entry_price,
            'sl': sl,
            'tp': tp
        })

# === SIMULATE TRADES ===
for trade in entries:
    entry_index = df.index.get_loc(trade['entry_time'])
    candles = df.iloc[entry_index + 1:entry_index + 50]  # look 50 candles ahead
    hit_tp = False
    hit_sl = False

    for _, candle in candles.iterrows():
        if trade['direction'] == 'BUY':
            if candle['low'] <= trade['sl']:
                hit_sl = True
                break
            elif candle['high'] >= trade['tp']:
                hit_tp = True
                break
        else:
            if candle['high'] >= trade['sl']:
                hit_sl = True
                break
            elif candle['low'] <= trade['tp']:
                hit_tp = True
                break

    if hit_tp:
        results.append(1 * RR_RATIO)  # profit
    elif hit_sl:
        results.append(-1)  # loss

# === REPORT ===
total = len(results)
wins = sum(1 for r in results if r > 0)
losses = total - wins
net_rr = sum(results)
winrate = (wins / total) * 100 if total > 0 else 0

print("\n🔥 EMA Smart Scalper v3.0 Backtest (Last 30 Days - XAUUSD)")
print("────────────────────────────────────────────")
print(f"Total Trades: {total}")
print(f"Wins: {wins} | Losses: {losses}")
print(f"Win Rate: {winrate:.2f}%")
print(f"Net RR Units: {net_rr:.2f}")
