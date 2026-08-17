import time
import json
import hmac
import hashlib
import logging
import urllib.parse
import urllib.request
import urllib.error

import database as db

logger = logging.getLogger("binance_utils")

PAY_HISTORY_BASE_URL = "https://binance.com"  # Updated to official API base URL
PAY_HISTORY_PATH = "/sapi/v1/pay/transactions"

def get_pay_transactions(limit=100):
    """Normal Binance account ki pay history nikalne ke liye endpoint."""
    api_key = db.get_setting("binance_api_key", "")
    api_secret = db.get_setting("binance_api_secret", "")
    
    if not api_key or not api_secret:
        logger.error("get_pay_transactions: Credentials missing in database Settings.")
        return None

    # Server time synchronization ke liye timestamp aur parameter setup [2]
    params = {
        "timestamp": str(int(time.time() * 1000)), 
        "limit": limit
    }

    query_string = urllib.parse.urlencode(params)
    signature = hmac.new(api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    url = f"{PAY_HISTORY_BASE_URL}{PAY_HISTORY_PATH}?{query_string}&signature={signature}"

    try:
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key}, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        logger.error("get_pay_transactions: HTTP %s - %s", e.code, e.read().decode("utf-8", errors="ignore"))
        return None
    except Exception as e:
        logger.error("get_pay_transactions: Request failed - %s", e)
        return None

    # Binance response list format me deta hai ya code '000000' ke sath [2]
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and (str(data.get("code")) == "000000" or data.get("success") is True):
        return data.get("data", [])
    
    logger.error("get_pay_transactions: Unexpected API response format: %s", data)
    return None

def find_matching_payment(submitted_txid, expected_amount_usd, tolerance=0.01):
    """User ki di gayi TxID aur Amount ko history se match karna [2]."""
    transactions = get_pay_transactions()
    if not transactions:
        logger.error("find_matching_payment: History empty ya API keys error.")
        return False

    sub_clean = "".join(ch for ch in str(submitted_txid).upper() if ch.isalnum()).strip()
    if not sub_clean:
        return False

    for tx in transactions:
        # Binance Pay dono keys me se koi bhi return kar sakta hai [2]
        tx_id = tx.get("transactionId")
        order_id = tx.get("orderId")
        
        t_id_clean = "".join(ch for ch in str(tx_id).upper() if ch.isalnum()) if tx_id else ""
        o_id_clean = "".join(ch for ch in str(order_id).upper() if ch.isalnum()) if order_id else ""

        # Match check (Exact match ya last 8-digit match user convenience ke liye) [2]
        if (sub_clean == t_id_clean or sub_clean == o_id_clean or 
            (len(sub_clean) >= 8 and (t_id_clean.endswith(sub_clean) or o_id_clean.endswith(sub_clean)))):
            
            # Security Guardrail: Sirf aane wale paise (IN) verify honge, bheje hue nahi (OUT) [2]
            if str(tx.get("fundsType")).upper() == "OUT" or str(tx.get("fundsDirection")).upper() == "OUT":
                logger.error("find_matching_payment: ID matched lekin ye OUTGOING payment hai.")
                continue

            try:
                amount = float(tx.get("amount", 0))
            except (TypeError, ValueError):
                continue

            # Amount aur safe margin deviation limit check [2]
            if abs(amount - float(expected_amount_usd)) <= tolerance:
                logger.info("find_matching_payment: SUCCESS MATCH for ID %s", submitted_txid)
                return True
            else:
                logger.error("find_matching_payment: ID match par Amount Mismatch (Got: %s, Expected: %s)", amount, expected_amount_usd)

    return False
