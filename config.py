import os


BOT_TOKEN = os.environ.get("8802969772:AAE-SuorCHBkmK3AbxKNkdgw3yPS9eyI_o4")

ADMIN_IDS = [6419247159]

SUPPORT_ADMIN_USERNAME = "your_admin_username"

# FamPay UPI gateway ("Fam Pay Api Bot" — fampay.anujbots.xyz) — used for auto-verified
# UPI deposits/orders. The API key (needed only for verify.php) lives in the settings
# table (set it from Admin > Settings > FamPay API Key) so it can be rotated without
# redeploying the bot. The merchant UPI ID (needed for qr.php) is the existing
# Admin > Settings > UPI ID setting.
FAMPAY_BASE_URL = os.environ.get("FAMPAY_BASE_URL", "https://fampay.anujbots.xyz")

DB_PATH = os.path.join(os.path.dirname(__file__), "shop_bot.db")

CATEGORIES = [
    "Netflix",
]
