import os

import httpx


async def chat(body: dict):
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    model = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.1-8b-instruct")
    if not account or not token:
        raise RuntimeError("Cloudflare is not configured")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
    body = dict(body)
    body["model"] = model
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        return r
