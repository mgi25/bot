import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt

# === CONFIG ===
LOGIN = 244499687
PASSWORD = "Mgi@2005"
SERVER = "Exness-MT5Trial14"

SYMBOL = "XAUUSDm"
START_DATE = datetime(2024, 12, 1)
END_DATE = datetime(2025, 1, 1)
RISK_PER_TRADE = 0.01
BALANCE = 1000.0
TP_MULTIPLIER = 2

# === CONNECT TO MT5 ===
def connect():
    if not mt5.initialize():
        print("Init failed", mt5.last_error())
        quit()
    if not mt5.login(LOGIN, PASSWORD, SERVER):
        print("Login failed", mt5.last_error())
        quit()
    print("🟢 Connected to MT5")

connect()

# === LOAD HISTORICAL DATA ===
rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M1, START_DATE, END_DATE)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)

# === CALCULATE INDICATORS ===
df['EMA5'] = df['close'].ewm(span=5).mean()
df['EMA10'] = df['close'].ewm(span=10).mean()
df['ATR'] = df['high'] - df['low']

# === BACKTEST LOGIC ===
balance = BALANCE
open_trade = None
trade_log = []

for i in range(15, len(df)):
    row = df.iloc[i]
    prev = df.iloc[i - 1]
    point = mt5.symbol_info(SYMBOL).point

    # Check for entry
    if open_trade is None:
        bullish = row['EMA5'] > row['EMA10']
        atr = row['ATR']
        price = row['close']
        sl_pips = atr / point if atr > 0 else 50
        tp_pips = sl_pips * TP_MULTIPLIER

        if bullish:
            sl = price - sl_pips * point
            tp = price + tp_pips * point
            risk_amount = balance * RISK_PER_TRADE
            pip_value = 1 if "USD" not in SYMBOL else 10
            lot = round(risk_amount / (sl_pips * pip_value), 2)
            open_trade = {
                'entry_price': price,
                'sl': sl,
                'tp': tp,
                'lot': lot,
                'entry_time': row.name,
                'sl_pips': sl_pips,
                'tp_pips': tp_pips
            }

    # Check for exit
    elif open_trade:
        high = row['high']
        low = row['low']
        entry = open_trade['entry_price']
        sl = open_trade['sl']
        tp = open_trade['tp']
        lot = open_trade['lot']

        if low <= sl:
            # SL hit
            loss = -RISK_PER_TRADE * balance
            balance += loss
            trade_log.append({'time': row.name, 'result': 'SL', 'pnl': loss, 'balance': balance})
            open_trade = None

        elif high >= tp:
            # TP hit
            reward = RISK_PER_TRADE * balance * TP_MULTIPLIER
            balance += reward
            trade_log.append({'time': row.name, 'result': 'TP', 'pnl': reward, 'balance': balance})
            open_trade = None

# === RESULTS ===
results = pd.DataFrame(trade_log)
print("\n📈 Backtest Summary:")
print(f"Total Trades: {len(results)}")
print(f"Wins: {len(results[results['result'] == 'TP'])}")
print(f"Losses: {len(results[results['result'] == 'SL'])}")
print(f"Win Rate: {len(results[results['result'] == 'TP']) / len(results) * 100:.2f}%" if len(results) > 0 else "No trades")
print(f"Final Balance: ${balance:.2f}")

# === PLOT BALANCE CURVE ===
if not results.empty:
    plt.plot(results['time'], results['balance'])
    plt.title("Equity Curve")
    plt.ylabel("Balance")
    plt.grid()
    plt.show()

# === DISCONNECT ===
mt5.shutdown()
