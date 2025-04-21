import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time, timezone
import time as ptime
import logging

# === CONFIGURATION ===
LOGIN = 240512732
PASSWORD = "Mgi@2005"
SERVER = "Exness-MT5Trial6"
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
LOT_SIZE = 0.01
PRICE_STEP = 0.01
ATR_PERIOD = 14
SKEW_THRESHOLD = 0.1
VOL_SPIKE_FACTOR = 0.8
TRADING_START = time(0, 0)
TRADING_END = time(20, 55)
MAGIC = 123456
TRAIL_BUFFER = 3
RECOVERY_ZONE = 2
VOLUME_CLUSTER_RATIO = 1
MAX_POSITIONS = 5

# === LOGGING ===
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler('live_bot.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[console_handler, file_handler]
)

def initialize():
    if not mt5.initialize(server=SERVER, login=LOGIN, password=PASSWORD):
        logging.error(f"MT5 init failed: {mt5.last_error()}")
        raise SystemExit
    mt5.symbol_select(SYMBOL, True)
    logging.info("Bot initialized and symbol selected")

def shutdown():
    mt5.shutdown()
    logging.info("MT5 shutdown")

def calc_skew(df_ticks, return_poc=False):
    if df_ticks.empty:
        return (None, None) if return_poc else None
    df = df_ticks.copy()
    df['price'] = (df['bid'] + df['ask']) / 2
    df['volume'] = df['volume'].replace(0, 1)
    df['bin'] = (df['price'] / PRICE_STEP).round() * PRICE_STEP
    vp = df.groupby('bin')['volume'].sum().sort_index()
    if vp.empty:
        return (None, None) if return_poc else None
    poc = vp.idxmax(); total = vp.sum(); cum = 0.0; inc = []
    for p, v in vp.sort_values(ascending=False).items():
        cum += v; inc.append(p)
        if cum >= 0.7 * total:
            break
    val, vah = min(inc), max(inc)
    width = vah - val; mid = (val + vah) / 2
    skew = (poc - mid) / width if width > 0 else 0
    return (skew, poc) if return_poc else skew

def volume_cluster_exit(df_ticks, entry_price, direction):
    if df_ticks.empty:
        return False
    df = df_ticks.copy()
    df['price'] = (df['bid'] + df['ask']) / 2
    df['volume'] = df['volume'].replace(0, 1)
    if direction == 'SELL':
        above_vol = df[df['price'] > entry_price]['volume'].sum()
    else:
        above_vol = df[df['price'] < entry_price]['volume'].sum()
    total_vol = df['volume'].sum()
    ratio = above_vol / total_vol if total_vol > 0 else 0
    logging.info(f"Volume cluster ratio ({direction}): {ratio:.2f}")
    return ratio > VOLUME_CLUSTER_RATIO

def place_entry(side, price):
    order_type = mt5.ORDER_TYPE_BUY if side == 'BUY' else mt5.ORDER_TYPE_SELL
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': SYMBOL,
        'volume': LOT_SIZE,
        'type': order_type,
        'price': price,
        'deviation': 10,
        'magic': MAGIC,
        'comment': 'VP_MULTI_ENTRY',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC
    }
    result = mt5.order_send(req)
    logging.info(f"Stacked Entry {side} at {price:.3f}, retcode={result.retcode}")

def main():
    initialize()
    bars_hist = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, 200)
    df_hist = pd.DataFrame(bars_hist)
    avg_ticks = df_hist['tick_volume'].mean()
    tick_thresh = avg_ticks * VOL_SPIKE_FACTOR

    logging.info("VP Recovery v1.2 with Multi-Entry Armed.")

    while True:
        now = datetime.now(timezone.utc)
        next_min = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        ptime.sleep(max((next_min - datetime.now(timezone.utc)).total_seconds(), 0))

        bar_time = next_min - timedelta(minutes=1)
        if not (TRADING_START <= bar_time.time() <= TRADING_END):
            continue

        bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, 1)
        if not bars:
            continue
        bar = bars[0]
        open_time = datetime.fromtimestamp(bar['time'], tz=timezone.utc)

        atr_bars = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 1, ATR_PERIOD + 1)
        df_atr = pd.DataFrame(atr_bars)
        df_atr['tr'] = df_atr[['high','low','close']].apply(
            lambda r: max(r['high']-r['low'], abs(r['high']-r['close']), abs(r['low']-r['close'])), axis=1)
        df_atr['atr'] = df_atr['tr'].rolling(ATR_PERIOD).mean()
        atr = df_atr['atr'].iloc[-1]
        if pd.isna(atr):
            continue

        if bar['tick_volume'] < tick_thresh:
            continue

        end_time = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
        ticks = mt5.copy_ticks_range(SYMBOL, open_time, end_time, mt5.COPY_TICKS_ALL)
        df_ticks = pd.DataFrame(ticks)
        if df_ticks.empty:
            continue

        skew, poc = calc_skew(df_ticks, return_poc=True)
        if skew is None or abs(skew) < SKEW_THRESHOLD:
            continue

        tick = mt5.symbol_info_tick(SYMBOL)
        side = 'BUY' if skew > 0 else 'SELL'
        price = tick.ask if side == 'BUY' else tick.bid

        # Check open positions before placing new one
        current_positions = mt5.positions_get(symbol=SYMBOL)
        if current_positions and len(current_positions) >= MAX_POSITIONS:
            logging.info(f"Max positions ({MAX_POSITIONS}) already open, skipping entry.")
        else:
            place_entry(side, price)

        # Manage all positions independently
        for pos in mt5.positions_get(symbol=SYMBOL):
            tick = mt5.symbol_info_tick(SYMBOL)
            point = mt5.symbol_info(SYMBOL).point
            current_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
            entry_price = pos.price_open
            profit_points = (current_price - entry_price) / point if pos.type == mt5.POSITION_TYPE_BUY else (entry_price - current_price) / point

            # Trailing Stop-Loss
            if profit_points > 5:
                sl_price = current_price - TRAIL_BUFFER * point if pos.type == mt5.POSITION_TYPE_BUY else current_price + TRAIL_BUFFER * point
                sl_req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": SYMBOL,
                    "position": pos.ticket,
                    "sl": sl_price,
                    "tp": 0.0,
                }
                mt5.order_send(sl_req)
                logging.info(f"Trailing SL set at {sl_price:.3f} for ticket {pos.ticket}")

            # Recovery zone exit near POC
            if profit_points < 0 and abs(current_price - poc) <= RECOVERY_ZONE * point:
                close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
                close_req = {
                    'action': mt5.TRADE_ACTION_DEAL,
                    'symbol': SYMBOL,
                    'volume': pos.volume,
                    'type': close_type,
                    'position': pos.ticket,
                    'price': close_price,
                    'deviation': 10,
                    'magic': MAGIC,
                    'comment': 'POC_RECOVERY_EXIT',
                    'type_time': mt5.ORDER_TIME_GTC,
                    'type_filling': mt5.ORDER_FILLING_IOC
                }
                mt5.order_send(close_req)
                logging.warning(f"Exited near POC at {close_price:.3f} for ticket {pos.ticket}")

            # Volume cluster pressure exit
            ticks_live = mt5.copy_ticks_from(SYMBOL, datetime.now(timezone.utc) - timedelta(seconds=10), 100, mt5.COPY_TICKS_ALL)
            df_live = pd.DataFrame(ticks_live)
            direction = 'BUY' if pos.type == mt5.POSITION_TYPE_BUY else 'SELL'
            if profit_points < 0 and volume_cluster_exit(df_live, entry_price, direction):
                close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
                close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
                close_req = {
                    'action': mt5.TRADE_ACTION_DEAL,
                    'symbol': SYMBOL,
                    'volume': pos.volume,
                    'type': close_type,
                    'position': pos.ticket,
                    'price': close_price,
                    'deviation': 10,
                    'magic': MAGIC,
                    'comment': 'CLUSTER_EXIT',
                    'type_time': mt5.ORDER_TIME_GTC,
                    'type_filling': mt5.ORDER_FILLING_IOC
                }
                mt5.order_send(close_req)
                logging.warning(f"Cluster exit @ {close_price:.3f} for ticket {pos.ticket}")

        ptime.sleep(1)

    shutdown()

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.exception("Bot crashed")
    finally:
        shutdown()
