import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8802969772:AAGIVPoTPhTNwjXvUzsKHVVXQCVzwpisPIs")
ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_IDS", "6419247159,6271161907").split(",") if i]
RBS_BASE_URL = os.getenv("RBS_BASE_URL", "https://rpshivabot-production.up.railway.app/api/v1")
RBS_BEARER_TOKEN = os.getenv("RBS_BEARER_TOKEN", "bkey_dtL7R_Tvx2AviMCKNmNxLXLU-MtY1vQJ4JvWIhkFccI")

