import os
import json
import logging
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger("AIRecovery")

PHASE_MODEL_MAP: Dict[str, str] = {
    "login":                "gemini-2.5-flash",
    "queue":                "gemini-2.5-flash",
    "show_date_selection":  "gemini-2.5-flash",
    "seat_selection":       "gemini-2.5-pro",
    "registration":         "gemini-2.5-flash",
    "add_to_cart":          "gemini-2.5-flash",
    "checkout":             "gemini-2.5-flash",
    "captcha":              "gemini-2.5-pro",
    "generic":              "gemini-2.5-pro",
    "verification":         "gemini-2.5-flash",
    "pre_scan":             "gemini-2.5-pro",
}

class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, default_model: str = "gemini-2.5-pro"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.default_model = default_model
        self.fallback_model = "gemini-2.5-flash"
        self.endpoint_tpl = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        self._client: Optional[httpx.AsyncClient] = None

    def is_api_ready(self) -> bool:
        if not self.api_key or self.api_key.startswith("YOUR_"):
            logger.error("❌ GEMINI_API_KEY is missing or invalid. Please check your config/env.")
            return False
        return True

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
            )
        return self._client

    def select_model(self, phase: str) -> str:
        return PHASE_MODEL_MAP.get(phase, self.default_model)

    async def call_gemini(self, image_data_b64: str, prompt: str, model: str) -> Optional[dict]:
        client = await self.get_client()
        endpoint = self.endpoint_tpl.format(model=model)
        url = f"{endpoint}?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": image_data_b64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }

        result = await self._post_gemini(client, url, payload)
        if result is not None:
            return result

        if model != self.fallback_model:
            logger.info(f"⚡ Retrying with fallback model: {self.fallback_model}")
            fallback_endpoint = self.endpoint_tpl.format(model=self.fallback_model)
            fallback_url = f"{fallback_endpoint}?key={self.api_key}"
            return await self._post_gemini(client, fallback_url, payload)

        return None

    async def _post_gemini(self, client: httpx.AsyncClient, url: str, payload: dict) -> Optional[dict]:
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                raw_content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw_content)
            else:
                logger.error(f"Gemini API returned status {resp.status_code}: {resp.text[:300]}")
        except httpx.TimeoutException:
            logger.warning("⏰ Gemini API timeout — will retry or fallback")
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
        return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
