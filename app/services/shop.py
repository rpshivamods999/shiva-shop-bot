import aiohttp
from app.config import RBS_BASE_URL, RBS_BEARER_TOKEN

async def fetch_rbs_balance() -> str:
    headers = {"Authorization": f"Bearer {RBS_BEARER_TOKEN}", "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{RBS_BASE_URL}/balance", headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return str(data.get("balance", "0.00"))
        except Exception:
            pass
    return "0.00"

async def generate_rbs_key(variant_id: int) -> dict:
    headers = {"Authorization": f"Bearer {RBS_BEARER_TOKEN}", "Content-Type": "application/json"}
    payload = {"variant_id": int(variant_id), "quantity": 1}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{RBS_BASE_URL}/generate-key", headers=headers, json=payload, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    key = data.get("key") or data.get("license_key") or data.get("keys")
                    return {"success": True, "key": key}
                else:
                    text = await resp.text()
                    return {"success": False, "msg": text}
        except Exception as e:
            return {"success": False, "msg": str(e)}
