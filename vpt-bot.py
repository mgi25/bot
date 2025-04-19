import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time, timezone
import time as ptime
import logging

# === CONFIGURATION ===
LOGIN            = 240512732
PASSWORD         = "Mgi@2005"
SERVER           = "Exness-MT5Trial6"
SYMBOL           = "XAUUSDm"
TIMEFRAME        = mt5.TIMEFRAME_M1
LOT_SIZE         = 0.01        # 0.01 lot = 1 oz
PRICE_STEP       = 0.01        # volume profile bin size
ATR_PERIOD       = 14          # ATR period
SKEW_THRESHOLD   = 0.1         # minimum absolute skew to trade
VOL_SPIKE_FACTOR = 1.5         # bar volume > factor * avg volume
TRADING_START    = time(7,5)   # UTC
TRADING_END      = time(20,55) # UTC
MAGIC            = 123456

# === SETUP LOGGING ===
logging.basicConfig(
    filename='live_bot.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

# === MT5 INIT ===
def initialize():
    print("Initializing MT5...")
    if not mt5.initialize(server=SERVER, login=LOGIN, password=PASSWORD):
        msg = f"MT5 init failed: {mt5.last_error()}"
        print(msg)
        logging.error(msg)
        raise SystemExit
    mt5.symbol_select(SYMBOL, True)
    print(f"Connected to MT5 and selected symbol {SYMBOL}")
    logging.info("MT5 initialized and symbol selected")

# === CLEANUP ===
def shutdown():
    mt5.shutdown()
    print("MT5 shutdown completed")
    logging.info("MT5 shutdown")

# === FEATURE: VOLUME-PROFILE SKEW ===
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
    for p, v in vp.sort_values(ascending=False).items():
        cum += v; included.append(p)
        if cum >= 0.7 * total:
            break
    val, vah = min(included), max(included)
    width = vah - val; mid = (val + vah) / 2
    return (poc - mid) / width if width > 0 else 0

# === MAIN LOOP ===
def main():
    initialize()
    # Precompute average bar volume for spike filter
    bars_hist = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, 200)
    df_hist = pd.DataFrame(bars_hist)
    df_hist['bar_vol'] = df_hist['tick_volume']
    avg_bar_vol = df_hist['bar_vol'].mean()
    vol_thresh = avg_bar_vol * VOL_SPIKE_FACTOR
    print(f"Average bar volume: {avg_bar_vol:.2f}, threshold set to {vol_thresh:.2f}")

    logging.info("Live bot started")
    print("Live bot started. Entering main loop...")
    while True:
        now = datetime.now(timezone.utc)
        # Sleep until the top of the next minute
        next_min = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        secs = (next_min - datetime.now(timezone.utc)).total_seconds()
        ptime.sleep(max(secs, 0))

        # Determine bar timestamp
        bar_time = next_min - timedelta(minutes=1)
        t = bar_time.time()
        # Time-of-day filter
        if not (TRADING_START <= t <= TRADING_END):
            print(f"Outside trading hours: {t}")
            continue

        # Fetch last closed bar via position offset
        bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, 1)
        if not bars:
            print("No bars returned")
            continue
        bar = bars[0]
        open_time = datetime.fromtimestamp(bar['time'])
        print(f"Processing bar at {open_time}")

        # ATR filter
        atr_bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, ATR_PERIOD+1)
        df_atr = pd.DataFrame(atr_bars)
        df_atr['tr'] = df_atr[['high','low','close']].apply(
            lambda r: max(r['high']-r['low'], abs(r['high']-r['close']), abs(r['low']-r['close'])), axis=1)
        df_atr['atr'] = df_atr['tr'].rolling(ATR_PERIOD).mean()
        atr = df_atr['atr'].iloc[-1]
        if pd.isna(atr):
            print("ATR not ready")
            continue
        print(f"ATR: {atr:.5f}")

        # Tick data for this bar and volume-spike filter
        end_time = open_time + timedelta(minutes=1)
        ticks = mt5.copy_ticks_range(SYMBOL, open_time, end_time, mt5.COPY_TICKS_ALL)
        df_ticks = pd.DataFrame(ticks)
        bar_vol = df_ticks['volume'].sum() if not df_ticks.empty else 0
        print(f"Bar volume: {bar_vol}")
        if bar_vol < vol_thresh:
            print("Volume below threshold")
            continue

        # Compute skew signal
        skew = calc_skew(df_ticks)
        print(f"Skew: {skew:.4f}")
        if skew is None or abs(skew) < SKEW_THRESHOLD:
            print("Skew below threshold")
            continue

        # Determine order parameters
        tick = mt5.symbol_info_tick(SYMBOL)
        if skew > 0:
            order_type = mt5.ORDER_TYPE_BUY; price = tick.ask; side = 'BUY'
        else:
            order_type = mt5.ORDER_TYPE_SELL; price = tick.bid; side = 'SELL'

        # Send market order
        req = {
            'action':       mt5.TRADE_ACTION_DEAL,
            'symbol':       SYMBOL,
            'volume':       LOT_SIZE,
            'type':         order_type,
            'price':        price,
            'deviation':    10,
            'magic':        MAGIC,
            'comment':      'HFT_DP',
            'type_time':    mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC
        }
        res = mt5.order_send(req)
        print(f"Entry {side} at {price:.3f}, retcode={res.retcode}")
        logging.info(f"Entry {side} at {price:.3f}, retcode={res.retcode}")

        # Exit at bar close: sleep until end of candle
        exit_time = open_time + timedelta(minutes=1)
        secs_exit = (exit_time - datetime.now(timezone.utc)).total_seconds() - 0.5
        ptime.sleep(max(secs_exit, 0))

        # Close any open position for this symbol
        positions = mt5.positions_get(symbol=SYMBOL)
        for pos in positions:
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = mt5.symbol_info_tick(SYMBOL).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(SYMBOL).ask
            close_req = {
                'action':       mt5.TRADE_ACTION_DEAL,
                'symbol':       SYMBOL,
                'volume':       pos.volume,
                'type':         close_type,
                'position':     pos.ticket,
                'price':        close_price,
                'deviation':    10,
                'magic':        MAGIC,
                'comment':      'HFT_DP_CLOSE',
                'type_time':    mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC
            }
            res2 = mt5.order_send(close_req)
            print(f"Exit {side} at {close_price:.3f}, retcode={res2.retcode}")
            logging.info(f"Exit {side} at {close_price:.3f}, retcode={res2.retcode}")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Error in live bot: {e}")
        logging.exception("Error in live bot")
    finally:
        shutdown()