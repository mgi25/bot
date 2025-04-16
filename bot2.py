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
MAX_MARGIN_USAGE = 0.15  # Use max 15% of account margin
LOOP_DELAY = 5
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

# === DATA ===
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
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))
def atr(df, period=14):
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

# === ENTRY STRATEGY ===
def check_entry(df):
    df['ema9'] = ema(df, 9)
    df['ema21'] = ema(df, 21)
    df['rsi'] = rsi(df)
    df['atr'] = atr(df)

    last = df.iloc[-1]
    trend_up = last['ema9'] > last['ema21']
    trend_down = last['ema9'] < last['ema21']
    strong_momentum_up = last['rsi'] > 60
    strong_momentum_down = last['rsi'] < 40
    body = abs(last['close'] - last['open'])
    wick = last['high'] - last['low']
    volatility_ok = wick != 0 and (body / wick) > 0.5

    if trend_up and strong_momentum_up and volatility_ok:
        return "BUY", last['atr']
    elif trend_down and strong_momentum_down and volatility_ok:
        return "SELL", last['atr']
    return None

# === LOT SIZE BASED ON AVAILABLE MARGIN ===
def calc_lot(symbol, sl_pips, balance):
    info = mt5.symbol_info(symbol)
    contract_size = info.trade_contract_size
    tick_value = info.trade_tick_value
    margin_per_lot = info.margin_initial

    if margin_per_lot == 0:
        print(f"⚠️ Could not get margin per lot for {symbol}")
        return 0.01

    max_margin = balance * MAX_MARGIN_USAGE
    lots = max_margin / margin_per_lot
    return round(max(min(lots, 1.0), 0.01), 2)

# === EXECUTION ===
def send_trade(symbol, signal, atr_value, balance):
    info = mt5.symbol_info(symbol)
    point = info.point
    digits = info.digits
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if signal == "BUY" else tick.bid

    sl_pips = round(atr_value * SL_MULTIPLIER / point)
    tp_pips = round(atr_value * TP_MULTIPLIER / point)
    lot = calc_lot(symbol, sl_pips, balance)

    if lot == 0.01:
        print(f"⚠️ Minimum lot used due to margin constraints.")

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
        "comment": "ScalperBot🔥",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    print(f"⚡ {signal} | {symbol} @ {round(price, digits)} | Lot: {lot} | SL: {round(sl, digits)} | TP: {round(tp, digits)} | Result: {result.retcode}")

# === BOT LOOP ===
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
                print(f"{symbol} → No strong setup.")
        time.sleep(LOOP_DELAY)

# === START ===
if __name__ == "__main__":
    run()
