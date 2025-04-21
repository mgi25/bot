import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time, timezone
import time as ptime

# === CONFIGURATION ===
LOGIN            = 240512732
PASSWORD         = "Mgi@2005"
SERVER           = "Exness-MT5Trial6"
SYMBOL           = "XAUUSDm"
TIMEFRAME        = mt5.TIMEFRAME_M1
LOT_SIZE         = 0.01               # You can change this
PRICE_STEP       = 0.01
ATR_PERIOD       = 14
SKEW_THRESHOLD   = 0.1
VOL_SPIKE_FACTOR = 1.5
TRADING_START    = time(0, 0)         # UTC
TRADING_END      = time(20, 55)       # UTC
MAGIC            = 123456

# === SKEW CALCULATION ===
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

# === MT5 INIT ===
def initialize():
    if not mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER):
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")
    mt5.symbol_select(SYMBOL, True)
    print(f"✅ Connected to MT5 and selected {SYMBOL}")

# === SHUTDOWN ===
def shutdown():
    mt5.shutdown()
    print("🔌 MT5 shutdown")

# === MAIN LOOP ===
def main():
    initialize()

    # Estimate tick volume threshold
    bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, 200)
    avg_tick_vol = pd.DataFrame(bars)['tick_volume'].mean()
    tick_threshold = avg_tick_vol * VOL_SPIKE_FACTOR
    print(f"📊 Avg ticks: {avg_tick_vol:.0f} | Threshold: {tick_threshold:.0f}")

    while True:
        # Wait till next candle opens
        now = datetime.now(timezone.utc)
        next_min = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        ptime.sleep(max((next_min - datetime.now(timezone.utc)).total_seconds(), 0))

        bar_time = next_min - timedelta(minutes=1)
        if not (TRADING_START <= bar_time.time() <= TRADING_END):
            print("⏳ Outside trading hours")
            continue

        # Fetch latest bar
        bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, ATR_PERIOD+1)
        df = pd.DataFrame(bars)
        if len(df) < ATR_PERIOD + 1:
            print("❌ Not enough bars")
            continue

        # Calculate ATR
        df['tr'] = df[['high','low','close']].apply(
            lambda r: max(r['high'] - r['low'], abs(r['high'] - r['close']), abs(r['low'] - r['close'])), axis=1)
        df['atr'] = df['tr'].rolling(ATR_PERIOD).mean()
        atr = df['atr'].iloc[-1]
        if pd.isna(atr):
            print("ATR not ready")
            continue

        bar = df.iloc[-1]
        tick_volume = bar['tick_volume']
        print(f"\n🕐 Processing bar at {datetime.fromtimestamp(bar['time'], tz=timezone.utc)}")
        print(f"ATR: {atr:.2f} | Tick Volume: {tick_volume}")

        if tick_volume < tick_threshold:
            print("🔇 Tick volume too low")
            continue

        # Fetch ticks
        start = datetime.fromtimestamp(bar['time'], tz=timezone.utc)
        end = start + timedelta(minutes=1)
        ticks = mt5.copy_ticks_range(SYMBOL, start, end, mt5.COPY_TICKS_ALL)
        df_ticks = pd.DataFrame(ticks)
        if df_ticks.empty:
            print("❌ No tick data")
            continue

        skew = calc_skew(df_ticks)
        print(f"Skew: {skew:.4f}")
        if skew is None or abs(skew) < SKEW_THRESHOLD:
            print("⛔ Skew too low")
            continue

        # Entry
        tick = mt5.symbol_info_tick(SYMBOL)
        if skew > 0:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            sl = price - atr
            tp = price + atr
            side = "BUY"
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            sl = price + atr
            tp = price - atr
            side = "SELL"

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": LOT_SIZE,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": MAGIC,
            "comment": "VolumeProfileEntry",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }

        result = mt5.order_send(request)
        print(f"📤 {side} at {price:.2f} | SL={sl:.2f} | TP={tp:.2f} | retcode={result.retcode}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        shutdown()
