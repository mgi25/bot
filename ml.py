import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import xgboost as xgb
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.metrics import classification_report

# === CONFIGURATION ===
SYMBOL      = "XAUUSDm"
TIMEFRAME   = mt5.TIMEFRAME_M1
PRICE_STEP  = 0.01     # Price bin size
N_CANDLES   = 5000     # Increase data size to 5k bars
HORIZON     = 3        # Future candles for labeling
THRESHOLD   = 0.0003   # Label threshold
ATR_PERIOD  = 14       # ATR period
MODEL_FILE  = "xgb_volume_profile_advanced.json"

# === MT5 SETUP ===
def initialize_mt5():
    if not mt5.initialize():
        raise RuntimeError(f"MT5 init failed: {mt5.last_error()}")

def shutdown_mt5():
    mt5.shutdown()

# === FEATURE FUNCTIONS ===
def compute_volume_profile_features(ticks, price_step=PRICE_STEP):
    # Skip invalid data
    if ticks is None or len(ticks) == 0:
        return None
    df = pd.DataFrame(ticks)
    if not {'bid','ask','volume'}.issubset(df.columns):
        return None
    # Mid‐price and volume fallback
    df['price']  = (df['bid'] + df['ask']) / 2
    df['volume'] = df['volume'].replace(0, 1)
    # Volume imbalance using Python sum to avoid overflow
    df['tick_ret'] = df['price'].diff()
    uv = sum(df.loc[df['tick_ret'] > 0, 'volume'])
    dv = sum(df.loc[df['tick_ret'] < 0, 'volume'])
    vol_imbalance = (uv - dv) / (uv + dv) if (uv + dv) > 0 else 0
    # Bin and aggregate profile
    df['bin'] = (df['price'] / price_step).round() * price_step
    vp = df.groupby('bin')['volume'].sum().sort_index()
    if vp.empty:
        return None
    poc = vp.idxmax()
    total = vp.sum(); cum = 0.0; included = []
    for p, v in vp.sort_values(ascending=False).items():
        cum += v; included.append(p)
        if cum >= 0.7 * total:
            break
    val = min(included); vah = max(included)
    width = vah - val; mid = (val + vah) / 2
    skew  = (poc - mid) / width if width > 0 else 0
    return poc, vah, val, width, skew, vol_imbalance

# === BUILD FEATURE MATRIX ===
def build_feature_matrix(symbol=SYMBOL):
    bars = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 1, N_CANDLES + HORIZON)
    dfb = pd.DataFrame(bars)
    dfb['time'] = pd.to_datetime(dfb['time'], unit='s')
    # ATR calculation
    dfb['tr']  = dfb[['high','low','close']].apply(
        lambda row: max(row['high']-row['low'], abs(row['high']-row['close']), abs(row['low']-row['close'])),
        axis=1)
    dfb['atr'] = dfb['tr'].rolling(ATR_PERIOD).mean()

    records = []
    for i in range(len(dfb) - HORIZON):
        row    = dfb.iloc[i]
        future = dfb.iloc[i + HORIZON]
        fut_ret = (future['close'] - row['open']) / row['open']
        # Tick data for this candle
        start = row['time']; end = start + timedelta(minutes=1)
        ticks = mt5.copy_ticks_range(symbol, start.to_pydatetime(), end.to_pydatetime(), mt5.COPY_TICKS_ALL)
        feats = compute_volume_profile_features(ticks)
        if feats is None or pd.isna(row['atr']):
            continue
        poc, vah, val, width, skew, vol_imb = feats
        mom = (row['close'] - row['open']) / row['open']
        records.append({
            'time':          start,
            'poc':           poc,
            'vah':           vah,
            'val':           val,
            'va_width':      width,
            'va_skew':       skew,
            'mom':           mom,
            'atr':           row['atr'],
            'vol_imbalance': vol_imb,
            'fut_ret':       fut_ret
        })
    df = pd.DataFrame(records)
    # Compute POC momentum deltas
    df['poc_delta_1'] = df['poc'].diff(1)
    df['poc_delta_3'] = df['poc'].diff(HORIZON)
    df.dropna(inplace=True)
    # Label: 0=SELL,1=HOLD,2=BUY
    df['label'] = df['fut_ret'].apply(lambda r: 2 if r > THRESHOLD else (0 if r < -THRESHOLD else 1))
    print("Label distribution after cleaning:", df['label'].value_counts().to_dict())
    return df

# === MAIN TRAINING FLOW ===
if __name__ == '__main__':
    initialize_mt5()
    print(f"Fetching {N_CANDLES} bars and building features...")
    df = build_feature_matrix(SYMBOL)
    shutdown_mt5()

    # Balance classes by downsampling HOLD
    df_sell = df[df.label == 0]
    df_buy  = df[df.label == 2]
    df_hold = df[df.label == 1].sample(n=min(len(df_sell), len(df_buy)), random_state=42)
    df_bal  = pd.concat([df_sell, df_buy, df_hold]).sample(frac=1, random_state=42)

    features = ['poc','vah','val','va_width','va_skew','mom','atr','poc_delta_1','poc_delta_3','vol_imbalance']
    X = df_bal[features]
    y = df_bal['label']

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    # Hyperparameter search
    xgb_clf = xgb.XGBClassifier(
        objective='multi:softprob', num_class=3,
        tree_method='hist', eval_metric='mlogloss', use_label_encoder=False
    )
    param_dist = {
        'n_estimators':     [100, 200, 300],
        'max_depth':        [3, 4, 5],
        'learning_rate':    [0.01, 0.05, 0.1],
        'subsample':        [0.7, 0.8, 1.0],
        'colsample_bytree': [0.7, 0.8, 1.0],
        'reg_alpha':        [0, 0.01, 0.1],
        'reg_lambda':       [1, 1.5, 2]
    }
    rs = RandomizedSearchCV(
        estimator=xgb_clf,
        param_distributions=param_dist,
        n_iter=20, cv=3, scoring='accuracy',
        random_state=42, n_jobs=-1, verbose=2
    )
    print("Starting hyperparameter search...")
    rs.fit(X_train, y_train)
    print("Best parameters found:", rs.best_params_)

    best_model = rs.best_estimator_
    preds = best_model.predict(X_test)
    print(classification_report(y_test, preds, target_names=['SELL','HOLD','BUY']))

    print(f"Saving best model to {MODEL_FILE}...")
    best_model.save_model(MODEL_FILE)
    print("Advanced training complete.")