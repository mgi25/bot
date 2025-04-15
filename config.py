# config.py
SYMBOLS = ["XAUUSDm", "EURUSDm", "GBPUSDm"]
TIMEFRAME = "M1"

RISK_PER_TRADE = 0.01  # 1%
MIN_WIN_PROB = 0.75  # Minimum ML confidence to enter

TRADING_SESSIONS = {
    "London": ("07:00", "16:00"),
    "NewYork": ("13:00", "21:00")
}

MAX_SPREAD = 15  # in points
STOP_AFTER_LOSSES = 3
