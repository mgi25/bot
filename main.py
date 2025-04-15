# main.py
from strategy.entry_logic import check_entry
from strategy.executor import execute_trade
from mt5_wrapper import get_latest_data, connect_to_mt5, shutdown
from config import SYMBOLS

connect_to_mt5()

for symbol in SYMBOLS:
    df = get_latest_data(symbol)
    result = check_entry(df, symbol)

    if result:
        signal, confidence = result
        print(f"{symbol} Entry: {signal} @ {confidence}")
        execute_trade(symbol, signal)

shutdown()
