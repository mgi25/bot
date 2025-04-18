import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import time

# === CONFIG ===
LOGIN = 244499687
PASSWORD = "Mgi@2005"
SERVER = "Exness-MT5Trial14"

SYMBOLS = ["XAUUSDm", "EURUSDm"]
RISK_PER_TRADE = 0.01
LOOP_DELAY = 5  # seconds between checks
SL_MULTIPLIER = 1.2
TP_MULTIPLIER = 2.0

# === CONNECT ===
def connect():
    if not mt5.initialize():
        print("MT5 Init failed:", mt5.last_error())
        quit()
    if mt5.login(LOGIN, password=PASSWORD, server=SERVER):
        print("🟢 Connected to Exness MT5")
    else:
        print("❌ Login failed:", mt5.last_error())
        quit()

# === DATA FETCH ===
def get_data(symbol, timeframe=mt5.TIMEFRAME_M1, bars=100):
    utc_from = datetime.now() - timedelta(minutes=bars)
    rates = mt5.copy_rates_from(symbol, timeframe, utc_from, bars)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# === INDICATORS ===
def ema(df, period): return df['close'].ewm(span=period).mean()
def rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
def atr(df, period=14):
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# === ROUND LOTS TO PROP-FIRM RULES ===
def round_lot(lot):
    return max(0.01, round(lot * 100) / 100.0)

# === MARGIN-AWARE LOT CALC ===
def calc_dynamic_lot(symbol, sl_pips, balance):
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.01
    pip_value = 10  # General estimate
    risk_dollars = balance * RISK_PER_TRADE
    lot = risk_dollars / (sl_pips * pip_value)
    return round_lot(lot)

# === ENTRY STRATEGY ===
def check_entry(df):
    df['ema9'] = ema(df, 9)
    df['ema21'] = ema(df, 21)
    df['rsi'] = rsi(df)
    df['atr'] = atr(df)

    bullish = (
        df['ema9'].iloc[-1] > df['ema21'].iloc[-1] and
        df['rsi'].iloc[-1] > 55
    )
    bearish = (
        df['ema9'].iloc[-1] < df['ema21'].iloc[-1] and
        df['rsi'].iloc[-1] < 45
    )

    if bullish:
        return "BUY", df['atr'].iloc[-1]
    elif bearish:
        return "SELL", df['atr'].iloc[-1]
    return None

# === TRADE EXECUTION ===
def send_trade(symbol, signal, atr_value, balance):
    info = mt5.symbol_info(symbol)
    point = info.point
    digits = info.digits
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if signal == "BUY" else tick.bid

    sl_pips = round(atr_value * SL_MULTIPLIER / point)
    tp_pips = round(atr_value * TP_MULTIPLIER / point)
    lot = calc_dynamic_lot(symbol, sl_pips, balance)

    sl = price - sl_pips * point if signal == "BUY" else price + sl_pips * point
    tp = price + tp_pips * point if signal == "BUY" else price - tp_pips * point

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "deviation": 20,
        "magic": 77777,
        "comment": "ScalperBot v4.0🔥",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    print(f"⚡ {signal} | {symbol} @ {round(price, digits)} | Lot: {lot} | SL: {round(sl, digits)} | TP: {round(tp, digits)} | Result: {result.retcode}")

# === LIVE LOOP ===
def run():
    connect()
    while True:
        account = mt5.account_info()
        balance = account.balance
        print(f"\n🕒 {datetime.now().strftime('%H:%M:%S')} | Balance: ${balance:.2f}")

        for symbol in SYMBOLS:
            df = get_data(symbol)
            signal = check_entry(df)
            if signal:
                send_trade(symbol, signal[0], signal[1], balance)
            else:
                print(f"{symbol} → No signal")
        time.sleep(LOOP_DELAY)

# === START ===
if __name__ == "__main__":
    run()
