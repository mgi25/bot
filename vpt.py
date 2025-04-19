import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# === MT5 Login === #
login = 240512732
password = "Mgi@2005"
server = "Exness-MT5Trial6"
symbol = "XAUUSDm"
price_step = 0.01
timeframe = mt5.TIMEFRAME_M1
num_candles = 5  # <== You can change this

# === Connect === #
if not mt5.initialize(server=server, login=login, password=password):
    print("MT5 init failed:", mt5.last_error())
    quit()

# === Get last N closed M1 candles === #
candles = mt5.copy_rates_from_pos(symbol, timeframe, 1, num_candles)
if candles is None or len(candles) == 0:
    print("No candle data.")
    mt5.shutdown()
    quit()

# === Create the plot === #
fig, axs = plt.subplots(num_candles, 1, figsize=(8, num_candles * 2.2), sharex=True)
if num_candles == 1:
    axs = [axs]
def calculate_value_area(volume_profile, percentage=0.7):
    total_volume = volume_profile.sum()
    sorted_profile = volume_profile.sort_values(ascending=False)
    
    cum_volume = 0
    included_prices = []

    for price, vol in sorted_profile.items():
        cum_volume += vol
        included_prices.append(price)
        if cum_volume >= total_volume * percentage:
            break

    return min(included_prices), max(included_prices)

# === Loop over each candle === #
for i, candle in enumerate(candles):
    start_time = datetime.fromtimestamp(candle['time'])
    end_time = start_time + timedelta(minutes=1)
    ticks = mt5.copy_ticks_range(symbol, start_time, end_time, mt5.COPY_TICKS_ALL)
    df = pd.DataFrame(ticks)

    if df.empty:
        axs[i].set_title(f"No Tick Data @ {start_time.strftime('%H:%M')}")
        continue

    # Price calculation
    df['price'] = (df['bid'] + df['ask']) / 2
    if df['volume'].sum() == 0:
        df['volume'] = 1

    # Volume profile
    df['binned'] = (df['price'] / price_step).round() * price_step
    vp = df.groupby('binned')['volume'].sum()
    poc = vp.idxmax()
    val, vah = calculate_value_area(vp)

    # Plot
    axs[i].barh(vp.index.astype(str), vp.values, color='gold')
    axs[i].axhline(y=poc, color='red', linestyle='--', linewidth=1.2, label=f"POC: {poc:.2f}")
    axs[i].axhline(y=vah, color='green', linestyle=':', linewidth=1.2, label=f"VAH: {vah:.2f}")
    axs[i].axhline(y=val, color='blue', linestyle=':', linewidth=1.2, label=f"VAL: {val:.2f}")
    axs[i].set_ylabel("Price")
    axs[i].set_title(f"{start_time.strftime('%H:%M')} | POC: {poc:.2f}")

    axs[i].legend(loc="upper right")
    

plt.xlabel("Volume")
plt.suptitle(f"{symbol} | Last {num_candles} M1 Candle Volume Profiles", fontsize=14)
plt.tight_layout(rect=[0, 0.03, 1, 0.97])
plt.grid(True)
plt.show()

mt5.shutdown()
