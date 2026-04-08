# Bug Report: Crash on zero exchange rate refunds
**Title**: Batch processor crashes on failed transactions
**Symptoms**: The batch refund processor crashes completely when processing certain failed transactions.
**Expected Behavior**: It should process the refund gracefully or reject it without crashing the entire batch.
**Actual Behavior**: System exits with an unhandled exception.
**Environment**: Python 3.10
**Hints**: We recently introduced a database change where `exchange_rate` is explicitly set to `0` instead of `null` for non-foreign transactions.