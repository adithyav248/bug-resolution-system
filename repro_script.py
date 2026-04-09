import sys
sys.path.append('./mini_repo')
from processor import process_refund

transaction = {
    'amount': 100,
    'exchange_rate': 0
}

try:
    process_refund(transaction)
except ZeroDivisionError as e:
    print(f"Successfully reproduced ZeroDivisionError: {e}")
except Exception as e:
    print(f"Reproduced an unexpected error: {e}")