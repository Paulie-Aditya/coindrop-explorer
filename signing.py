"""
Signed, opaque URL tokens for carrying tx display data (amount, to_address, fee)
from the bot to the explorer without a DB round-trip or a chain/API call.

HMAC-SHA256 for integrity only -- the payload is not secret (amount/addresses are
already public on-chain), this just stops a crafted link from showing a fake amount.

Token shape: "<base64url(json payload, no padding)>.<base64url(hmac digest, no padding)>"
"""

import base64
import hashlib
import hmac
import json


def _b64encode(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64decode(data: bytes) -> bytes:
    padding = b"=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def build_token(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body_b64 = _b64encode(body)
    sig = hmac.new(secret.encode("utf-8"), body_b64, hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)
    return f"{body_b64.decode()}.{sig_b64.decode()}"


def verify_token(token: str, secret: str) -> dict | None:
    try:
        body_b64_str, sig_b64_str = token.split(".", 1)
    except ValueError:
        return None

    body_b64 = body_b64_str.encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), body_b64, hashlib.sha256).digest()
    expected_sig_b64 = _b64encode(expected_sig)

    if not hmac.compare_digest(expected_sig_b64, sig_b64_str.encode("utf-8")):
        return None

    try:
        return json.loads(_b64decode(body_b64))
    except (ValueError, UnicodeDecodeError):
        return None
