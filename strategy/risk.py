def calculate_lot_size(balance, stop_loss_pips, pip_value=10):
    risk_amount = balance * 0.01
    lot = risk_amount / (stop_loss_pips * pip_value)
    return round(max(lot, 0.01), 2)
