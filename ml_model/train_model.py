# train_model.py
import pandas as pd
from xgboost import XGBClassifier
import joblib

def train_model():
    df = pd.read_csv('data/historical/XAUUSDm_1min.csv')

    # Feature Engineering here
    df['target'] = (df['future_return'] > 0).astype(int)  # Label

    features = df[['ema9', 'ema21', 'rsi', 'atr']]
    target = df['target']

    model = XGBClassifier()
    model.fit(features, target)

    joblib.dump(model, 'ml_model/model.pkl')
