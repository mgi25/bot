from indicators.ema import calculate_ema
from indicators.rsi import calculate_rsi
from indicators.atr import calculate_atr
from config import MIN_WIN_PROB
from ml_model.model_loader import predict_trade  # Placeholder

def check_entry(df, symbol):
    df['ema9'] = calculate_ema(df, 9)
    df['ema21'] = calculate_ema(df, 21)

    if df['ema9'].iloc[-1] > df['ema21'].iloc[-1]:  # Buy Bias
        signal = "BUY"
    elif df['ema9'].iloc[-1] < df['ema21'].iloc[-1]:  # Sell Bias
        signal = "SELL"
    else:
        return None

    confidence = predict_trade(df.tail(50))  # Last 50 candles
    if confidence >= MIN_WIN_PROB:
        return signal, confidence
    return None
