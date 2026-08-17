"""
Integration with the "Fam Pay Api Bot" UPI gateway (fampay.anujbots.xyz).
Two endpoints are used:
  - qr.php      -> generates a UPI QR code for a payment (no API key needed)
  - verify.php  -> polled repeatedly to check if that order got paid (needs API key)

IMPORTANT — this gateway does NOT expose a distinct "pending" vs "failed" state.
verify.php returns {"status":"error","message":"Transaction failed - Payment not
received"} both WHILE the customer simply hasn't paid yet, and (presumably) once
the order is truly dead — there's no documented way to tell those apart from the
response alone. To avoid wrongly cancelling live payments, this module treats
EVERY "error" response as still-pending and never returns "failed"/"expired".
Expiry is instead handled entirely by the bot's own 5-minute stale-transaction
cleanup job (see main.py: cleanup_stale_transactions), independent of the gateway.
"""
import json
import logging
import urllib.parse
import urllib.request
import urllib.error

from config import FAMPAY_BASE_URL
import database as db

logger = logging.getLogger("fampay_utils")

# Orders on this gateway expire 5 minutes after creation (matches the bot's
# existing 5-minute stale-transaction cleanup in main.py).
ORDER_TTL_SECONDS = 5 * 60


def _get(path, params, include_key=False):
    params = dict(params)
    if include_key:
        api_key = db.get_setting("fampay_api_key", "")
        if not api_key:
            logger.error("_get %s: fampay_api_key not set in Admin > Settings", path)
            return None
        params["api_key"] = api_key
    url = f"{FAMPAY_BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        logger.error("_get %s: HTTP %s - %s", path, e.code, e.read().decode("utf-8", errors="ignore"))
        return None
    except Exception as e:
        logger.error("_get %s: request failed - %s", path, e)
        return None
    try:
        return json.loads(raw)
    except Exception:
        logger.error("_get %s: non-JSON response - %s", path, raw[:300])
        return None


def create_order(amount_inr):
    """Generates a UPI QR code for the given INR amount, paid to the merchant
    UPI ID configured in Admin > Settings > UPI ID.
    Returns dict {order_id, qr_url, upi_id, amount, expires_at} or None on failure."""
    upi_id = db.get_setting("upi_id", "")
    if not upi_id:
        logger.error("create_order: no merchant UPI ID set — configure it in Admin > Settings > UPI ID")
        return None
    data = _get("/qr.php", {"upi": upi_id, "amount": amount_inr})
    if not data or data.get("status") != "success":
        logger.error("create_order failed for amount=%s: %s", amount_inr, data)
        return None
    d = data.get("data", {})
    order_id = d.get("order_id")
    if not order_id:
        logger.error("create_order: missing order_id in response: %s", data)
        return None
    return {
        "order_id": order_id,
        "qr_url": d.get("qr_url"),
        "upi_id": d.get("upi_id", upi_id),
        "amount": d.get("amount", amount_inr),
        "expires_at": d.get("expires_at_ist"),
    }


def verify_order(order_id):
    """Polls verify.php for this order_id.
    Returns (status, raw_response) where status is one of: 'success' | 'pending' | 'unknown'.
    (No 'failed'/'expired' — see module docstring for why.)"""
    data = _get("/verify.php", {"order_id": order_id}, include_key=True)
    if data is None:
        return "unknown", None
    if isinstance(data, dict) and data.get("status") == "success":
        return "success", data
    if isinstance(data, dict) and data.get("status") == "error":
        return "pending", data
    logger.warning("verify_order: unrecognized response shape for %s: %s", order_id, data)
    return "unknown", data


# Small float-safe slack for rupee rounding (e.g. amount stored as 500 vs gateway
# returning 500.0) — NOT a discount tolerance. Anything paid less than
# expected_amount - AMOUNT_TOLERANCE still fails the check.
AMOUNT_TOLERANCE = 0.01


def get_paid_amount(raw):
    """Extracts the actual amount FamPay confirms was received, from a 'success'
    verify_order() raw response (raw['data']['amount']). Returns float, or None if
    the field is missing/unparseable — callers MUST treat None as "can't confirm,
    do not auto-complete", never as "amount was fine"."""
    if not isinstance(raw, dict):
        return None
    try:
        return float(raw.get("data", {}).get("amount"))
    except (TypeError, ValueError):
        return None


def amount_is_sufficient(raw, expected_amount):
    """True only if verify_order's 'success' response confirms a received amount
    that is >= expected_amount (within AMOUNT_TOLERANCE for float rounding).
    This is the fix for the QR-tampering scam: a scammer can edit the 'am='
    parameter in the UPI intent link extracted from the QR and pay less (e.g. ₹1
    instead of ₹500) to the same merchant VPA. FamPay's own gateway still reports
    status:"success" for that order_id because *a* payment landed — only checking
    the actually-received amount against what the QR was generated for catches this.
    Any missing/unparseable amount is treated as insufficient (fail closed)."""
    paid = get_paid_amount(raw)
    if paid is None:
        logger.warning("amount_is_sufficient: no parseable amount in success response: %s", raw)
        return False
    return paid >= (float(expected_amount) - AMOUNT_TOLERANCE)
