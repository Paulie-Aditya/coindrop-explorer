"""
Craft a signed token for local testing.

Usage:
    EXPLORER_SIGNING_SECRET=test123 python3 scripts/make_token.py

Then hit, e.g.:
    http://localhost:8002/ltc/<tx_hash below>?d=<printed token>

amount/fee are in base units (litoshis here), exactly as withdrawal_queue
stores them -- the explorer formats them using currencies.decimals.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from signing import build_token

secret = os.getenv("EXPLORER_SIGNING_SECRET", "test123")

payload = {
    "chain_id": 100004,
    "tx_hash": "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b",
    "currency": "LTC",
    "amount": "125000000",
    "fee": "2260",
    "to_address": "ltc1qg9stkxrszkdqsuj92lm4c7akvk36zvhqw7p6ck",
}

print(build_token(payload, secret))
