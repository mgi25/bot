import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import time

# Connect to MT5
mt5.initialize(server="Exness-MT5Trial6", login=240512732, password="Mgi@2005")
symbol = "XAUUSDm"
lot_size = 0.01

def get_last_candle():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 2)
    if rates is not None and len(rates) == 2:
        return rates[0], rates[1]  # closed, current
    return None, None

def get_tick_price():
    tick = mt5.symbol_info_tick(symbol)
    return tick.ask if tick else None

def get_volume_profile(start, end):
    ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
    df = pd.DataFrame(ticks)
    df['price'] = (df['bid'] + df['ask']) / 2
    if df['volume'].sum() == 0:
        df['volume'] = 1
    df['binned'] = (df['price'] / 0.01).round() * 0.01
    vp = df.groupby('binned')['volume'].sum()
    return vp

def calculate_value_area(vp, percentage=0.7):
    total_volume = vp.sum()
    sorted_profile = vp.sort_values(ascending=False)
    cum_volume = 0
    included = []
    for price, vol in sorted_profile.items():
        cum_volume += vol
        included.append(price)
        if cum_volume >= total_volume * percentage:
            break
    return min(included), max(included)

def place_trade():
    price = get_tick_price()
    sl = price - 1.0
    tp = price + 2.0
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 123456,
        "comment": "POC Retest Entry",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    print("Trade Result:", result)

# === LIVE MONITOR LOOP === #
print("Sniper mode ON. Waiting for next POC retest...")

while True:
    closed_candle, _ = get_last_candle()
    start = datetime.fromtimestamp(closed_candle['time'])
    end = start + timedelta(minutes=1)
    
    vp = get_volume_profile(start, end)
    if vp.empty:
        time.sleep(10)
        continue

    poc = vp.idxmax()
    val, vah = calculate_value_area(vp)

    print(f"[{start.strftime('%H:%M')}] POC: {poc}, VAH: {vah}, VAL: {val}")

    # Wait for live price to dip into POC range
    for _ in range(30):  # 30 checks (~30 secs)
        live_price = get_tick_price()
        if live_price and (poc - 0.01 <= live_price <= poc + 0.01):
            print("🔥 Retest detected. Sending BUY.")
            place_trade()
            break
        time.sleep(1)

    # Wait for next minute
    print("Waiting for next candle...")
    time.sleep(30)
