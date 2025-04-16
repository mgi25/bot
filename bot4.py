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
LOOP_DELAY = 5
SL_MULTIPLIER = 0.5
TP_MULTIPLIER = 2.2
TRAIL_AFTER_PIPS = 6
TRAIL_STEP_PIPS = 3
TRAIL_COOLDOWN = 30  # cooldown time in seconds
open_positions = set()
last_sl_update = {}

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
def atr(df, period=10):
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()
def trend_strength(df):
    return df['ema9'].iloc[-1] - df['ema21'].iloc[-1]

# === ENTRY STRATEGY ===
def check_entry(df):
    df['ema9'] = ema(df, 9)
    df['ema21'] = ema(df, 21)
    df['rsi'] = rsi(df)
    df['atr'] = atr(df)
    last = df.iloc[-1]

    body = abs(last['close'] - last['open'])
    wick = last['high'] - last['low']
    slope = trend_strength(df)
    choppy = 45 < last['rsi'] < 55 or body < wick * 0.4 or df['atr'].iloc[-1] < 0.05

    if choppy or abs(slope) < 0.03:
        return None
    if slope > 0 and last['rsi'] > 58:
        return "BUY", df['atr'].iloc[-1]
    elif slope < 0 and last['rsi'] < 42:
        return "SELL", df['atr'].iloc[-1]
    return None

# === LOT CALCULATION ===
def round_lot(lot): return max(0.01, round(lot * 100) / 100.0)
def calc_lot(symbol, balance, sl_pips):
    info = mt5.symbol_info(symbol)
    pip_value = 10
    risk_amt = balance * RISK_PER_TRADE
    raw_lot = risk_amt / (sl_pips * pip_value)
    margin_limit = info.margin_initial or 10
    max_lot = (mt5.account_info().margin_free * 0.2) / margin_limit
    return round_lot(min(raw_lot, max_lot))

# === SEND ORDER ===
def send_trade(symbol, signal, atr_val, balance):
    info = mt5.symbol_info(symbol)
    point, digits = info.point, info.digits
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if signal == "BUY" else tick.bid

    sl_pips = round(atr_val * SL_MULTIPLIER / point)
    tp_pips = round(atr_val * TP_MULTIPLIER / point)
    lot = calc_lot(symbol, balance, sl_pips)

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
        "comment": "Ironman V12 ⚡",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode == 10009:
        open_positions.add(symbol)
        last_sl_update[symbol] = datetime.now()
        print(f"⚡ {signal} | {symbol} @ {round(price, digits)} | Lot: {lot} | SL: {round(sl, digits)} | TP: {round(tp, digits)} | Result: {result.retcode}")
    else:
        print(f"❌ Failed to send trade on {symbol}: {result.retcode}")

# === TRAILING SL ===
def trail_stops():
    positions = mt5.positions_get()
    if not positions:
        return

    for pos in positions:
        try:
            info = mt5.symbol_info(pos.symbol)
            tick = mt5.symbol_info_tick(pos.symbol)
            point = info.point
            digits = info.digits
            price = tick.bid if pos.type == mt5.ORDER_TYPE_SELL else tick.ask

            move = (price - pos.price_open) if pos.type == 0 else (pos.price_open - price)
            if move / point < TRAIL_AFTER_PIPS:
                continue

            if pos.symbol in last_sl_update and (datetime.now() - last_sl_update[pos.symbol]).total_seconds() < TRAIL_COOLDOWN:
                continue

            new_sl = price - TRAIL_STEP_PIPS * point if pos.type == 0 else price + TRAIL_STEP_PIPS * point
            current_sl = pos.sl if pos.sl > 0 else (price - 1000 * point if pos.type == 0 else price + 1000 * point)
            freeze = getattr(info, 'freeze_level', 5) * point

            if abs(new_sl - current_sl) > freeze and ((pos.type == 0 and new_sl > current_sl) or (pos.type == 1 and new_sl < current_sl)):
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": pos.symbol,
                    "sl": round(new_sl, digits),
                    "tp": pos.tp
                }
                result = mt5.order_send(request)
                if result.retcode == 10009:
                    last_sl_update[pos.symbol] = datetime.now()
                    print(f"🔁 Trailed SL on {pos.symbol} | New SL: {round(new_sl, digits)}")
                else:
                    print(f"❌ Failed to trail SL on {pos.symbol}: {result.retcode}")
        except Exception as e:
            print(f"⚠️ Error trailing SL on {pos.symbol}: {e}")

# === BOT LOOP ===
def run():
    connect()
    while True:
        balance = mt5.account_info().balance
        print(f"\n🕒 {datetime.now().strftime('%H:%M:%S')} | Balance: ${balance:.2f}")
        open_positions.clear()
        for p in mt5.positions_get() or []:
            open_positions.add(p.symbol)
        for sym in SYMBOLS:
            df = get_data(sym)
            signal = check_entry(df)
            if signal:
                send_trade(sym, signal[0], signal[1], balance)
            else:
                print(f"{sym} → No valid signal.")
        trail_stops()
        time.sleep(LOOP_DELAY)

if __name__ == "__main__":
    run()
