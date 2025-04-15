import MetaTrader5 as mt5
import pandas as pd
import pytz
from datetime import datetime, timedelta

# 🟢 Connect to Exness account
def connect_to_mt5():
    if not mt5.initialize():
        print("MT5 Initialize failed:", mt5.last_error())
        quit()

    authorized = mt5.login(
        login=244499687,  # 🔑 YOUR EXNESS LOGIN ID
        password="Mgi@2005",  # 🔐 EXNESS PASSWORD
        server="Exness-MT5Trial14"  # Make sure this matches your server in Exness
    )

    if authorized:
        print("🟢 Connected to Exness MT5 successfully.")
    else:
        print("❌ Failed to connect. Error:", mt5.last_error())
        quit()

# 📊 Get recent candles for a symbol
def get_latest_data(symbol, timeframe=mt5.TIMEFRAME_M1, bars=100):
    utc_from = datetime.now() - timedelta(minutes=bars)
    rates = mt5.copy_rates_from(symbol, timeframe, utc_from, bars)

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# 🔴 Close connection
def shutdown():
    mt5.shutdown()
