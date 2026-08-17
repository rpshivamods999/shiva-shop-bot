import os


BOT_TOKEN = os.environ.get("BOT_TOKEN", "8551075183:AAF0RlWWCeD0PnX19bzHPiShuDA_37OPTvk")

ADMIN_IDS = [
    8357256746,
    7521404290
]

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
