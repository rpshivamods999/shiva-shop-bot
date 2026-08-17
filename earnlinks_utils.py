import logging
import urllib.parse
import urllib.request
import urllib.error

import database as db

logger = logging.getLogger(__name__)

EARNLINKS_API_URL = "https://earnlinks.in/api"


def shorten_url(destination_url: str):
    """Shortens destination_url via the Earnlinks.in API using the token stored in
    settings (Admin > Settings > Earnlinks API Token). Returns the shortened URL,
    or None if the token isn't set or the API call fails — callers should decide
    on a fallback (e.g. serve the direct link) rather than let the trial break.
    """
    token = db.get_setting("earnlinks_api_token", "")
    if not token:
        logger.warning("earnlinks_utils: shorten_url called but no API token is set")
        return None

    params = {"api": token, "url": destination_url, "format": "text"}
    url = f"{EARNLINKS_API_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
        if text.startswith("http"):
            return text
        logger.error("earnlinks_utils: unexpected response for %s: %s", destination_url, text)
        return None
    except Exception as e:
        logger.error("earnlinks_utils: shorten_url failed for %s: %s", destination_url, e)
        return None
