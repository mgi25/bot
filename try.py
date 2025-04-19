import MetaTrader5 as mt5
import pandas as pd
import time

# === CONFIG === #
LOGIN = 52278049
PASSWORD = "c$O1f@g3S@hUqs"
SERVER = "ICMarketsSC-Demo"
MT5_PATH = "C:\\Program Files\\MetaTrader 5 IC Markets Global\\terminal64.exe"
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
EMA_PERIOD = 30
RISK_LOT = 0.01

# === INIT MT5 === #
mt5.initialize(path=MT5_PATH, login=LOGIN, password=PASSWORD, server=SERVER)
if not mt5.initialize():
    raise SystemExit("MT5 init failed", mt5.last_error())

# === EMA Rejection Detection === #
def get_ema_rejection():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, EMA_PERIOD + 3)
    df = pd.DataFrame(rates)
    df['ema'] = df['close'].ewm(span=EMA_PERIOD).mean()

    last = df.iloc[-2]  # previous candle
    curr_price = mt5.symbol_info_tick(SYMBOL).bid

    wick = last['high'] - max(last['open'], last['close'])
    body = abs(last['open'] - last['close'])
    above_ema = last['high'] > last['ema']
    close_below_open = last['close'] < last['open']

    if above_ema and close_below_open and wick > (body * 1.5):
        print(f"[🟢] Rejection detected at {last['time']}")
        return True
    return False

# === Place SELL === #
def place_sell():
    tick = mt5.symbol_info_tick(SYMBOL)
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": RISK_LOT,
        "type": mt5.ORDER_TYPE_SELL,
        "price": tick.bid,
        "deviation": 20,
        "magic": 909090,
        "comment": "EMA_Rejection_Sell",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.symbol_info(SYMBOL).filling_mode if mt5.symbol_info(SYMBOL) else mt5.ORDER_FILLING_IOC
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[✓] SELL Placed @ {tick.bid}")
    else:
        print(f"[x] SELL Failed → {result.retcode} | {result.comment}")

# === MAIN LOOP === #
while True:
    if get_ema_rejection():
        place_sell()
        time.sleep(60)  # Wait 1 minute after entry
    else:
        print("[...] No rejection found")
    time.sleep(5)
