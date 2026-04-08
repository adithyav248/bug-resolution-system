import sys
sys.path.append('./mini_repo')
from processor import process_refund

# This transaction will cause a ZeroDivisionError
buggy_transaction = {
    'amount': 100,
    'exchange_rate': 0
}

print(f"Attempting to process transaction: {buggy_transaction}")
process_refund(buggy_transaction)