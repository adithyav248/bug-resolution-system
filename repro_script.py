import sys
sys.path.append('./mini_repo')
from processor import process_refund

transaction = {'amount': 100, 'exchange_rate': 0}
process_refund(transaction)