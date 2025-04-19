import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import os

# === CONFIG ===
LOGIN = 52278049
PASSWORD = "c$O1f@g3S@hUqs"
SERVER = "ICMarketsSC-Demo"
MT5_PATH = "C:\\Program Files\\MetaTrader 5 IC Markets Global\\terminal64.exe"

SYMBOLS = ["XAUUSD", "EURUSD"]
RISK_PER_TRADE = 0.01
TRAIL_TRIGGER = 5
TRAIL_STEP = 3
SPREAD_LIMIT = 300
ATR_MULTIPLIER = 1.5  # Multiply ATR to give trades more breathing room

# === CONNECT ===
def connect():
    if not mt5.initialize(MT5_PATH):
        print("MT5 Init failed:", mt5.last_error())
        quit()
    if mt5.login(LOGIN, password=PASSWORD, server=SERVER):
        print("🟢 Connected to ICMarkets MT5")
    else:
        print("❌ Login failed:", mt5.last_error())
        quit()

# === TICK INFO ===
def get_latest_tick(symbol):
    return mt5.symbol_info_tick(symbol)

# === ENTRY LOGIC ===
def should_enter_trade(symbol):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 20)
    if rates is None or len(rates) < 15:
        print(f"⚠️ Not enough data for {symbol}")
        return False, None, 0

    df = pd.DataFrame(rates)
    df['EMA5'] = df['close'].ewm(span=5).mean()
    df['EMA10'] = df['close'].ewm(span=10).mean()
    df['ATR'] = df['high'] - df['low']

    last = df.iloc[-1]
    tick = get_latest_tick(symbol)
    spread = tick.ask - tick.bid
    point = mt5.symbol_info(symbol).point
    avg_atr = df['ATR'].mean()

    bullish = last['EMA5'] > last['EMA10']
    bearish = last['EMA5'] < last['EMA10']
    low_spread = spread < SPREAD_LIMIT * point

    print(f"📊 {symbol} | Bullish: {bullish} | Bearish: {bearish} | Spread OK: {low_spread} | ATR: {last['ATR']:.5f}/{avg_atr:.5f} | Spread: {spread/point:.1f} pts")

    if low_spread:
        if bullish:
            return True, "BUY", last['ATR']
        elif bearish:
            return True, "SELL", last['ATR']

    return False, None, 0

# === LOT SIZE CALC ===
def calc_lot(balance, symbol, sl_points):
    info = mt5.symbol_info(symbol)
    tick_value = info.trade_tick_value
    tick_size = info.point
    min_lot = info.volume_min
    risk_amount = balance * RISK_PER_TRADE
    lot = risk_amount / (sl_points * tick_value / tick_size)
    return max(min_lot, round(lot, 2))

# === PLACE ORDER ===
def place_order(symbol, direction, sl_pips, tp_pips, balance):
    tick = get_latest_tick(symbol)
    info = mt5.symbol_info(symbol)
    point = info.point
    digits = info.digits
    price = tick.ask if direction == "BUY" else tick.bid

    sl = price - sl_pips * point if direction == "BUY" else price + sl_pips * point
    tp = price + tp_pips * point if direction == "BUY" else price - tp_pips * point
    lot = calc_lot(balance, symbol, sl_pips)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "deviation": 10,
        "magic": 99988,
        "comment": "💹HFT-BOT-PRO",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    print(f"🚀 {direction} {symbol} @ {round(price, digits)} | Lot: {lot} | SL: {round(sl, digits)} | TP: {round(tp, digits)} | Result: {result.retcode}")

# === TRAIL STOPS ===
def trail_stops():
    positions = mt5.positions_get()
    for pos in positions:
        tick = get_latest_tick(pos.symbol)
        info = mt5.symbol_info(pos.symbol)
        point = info.point
        digits = info.digits
        current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        move = (current_price - pos.price_open) if pos.type == mt5.ORDER_TYPE_BUY else (pos.price_open - current_price)

        if move / point >= TRAIL_TRIGGER:
            new_sl = current_price - TRAIL_STEP * point if pos.type == mt5.ORDER_TYPE_BUY else current_price + TRAIL_STEP * point
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "sl": round(new_sl, digits),
                "tp": pos.tp
            }
            result = mt5.order_send(request)
            if result.retcode == 10009:
                print(f"🔁 Trailed SL for {pos.symbol} | New SL: {round(new_sl, digits)}")
            else:
                print(f"❌ Trail SL failed on {pos.symbol} | Code: {result.retcode}")

# === MAIN LOOP ===
def run():
    connect()
    while True:
        acc = mt5.account_info()
        if acc is None:
            print("⚠️ Account info fetch failed")
            break

        balance = acc.balance
        print(f"\n🕒 {datetime.now().strftime('%H:%M:%S')} | Balance: ${balance:.2f}")

        for symbol in SYMBOLS:
            entry_ok, direction, atr = should_enter_trade(symbol)
            if entry_ok:
                point = mt5.symbol_info(symbol).point
                sl_pips = int((atr / point) * ATR_MULTIPLIER) if atr > 0 else 50
                tp_pips = sl_pips * 2
                place_order(symbol, direction, sl_pips, tp_pips, balance)

        trail_stops()
        time.sleep(1)

if __name__ == "__main__":
    run()
