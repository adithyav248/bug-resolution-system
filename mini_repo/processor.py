def process_refund(transaction):
    amount = transaction.get('amount', 0)
    exchange_rate = transaction.get('exchange_rate')
    
    # BUG: If exchange_rate is explicitly 0, this causes a ZeroDivisionError
    if exchange_rate is not None:
        base_amount = amount / exchange_rate
    else:
        base_amount = amount
        
    # Standard refund fee is 2%
    return base_amount * 0.98