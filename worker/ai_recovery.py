import os
from typing import Dict, Any, Optional, List
from playwright.async_api import Page
from ai.executor import AIVisualRecoveryManager as ModularAIVisualRecoveryManager
from ai import analyser

class AIVisualRecoveryManager:
    """Backward-compatible wrapper for the modular AIVisualRecoveryManager."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-pro"):
        self.delegate = ModularAIVisualRecoveryManager(api_key, model_name)

    async def attempt_recovery(
        self,
        page: Page,
        screenshot_dir: str = "tmp",
        behavior=None,
        phase: str = "generic",
        seat_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        return await self.delegate.attempt_recovery(
            page,
            screenshot_dir=screenshot_dir,
            behavior=behavior,
            phase=phase,
            seat_context=seat_context
        )

    async def analyze_purchase_page(self, page: Page) -> Optional[dict]:
        return await analyser.analyze_purchase_page(page, self.delegate.client)

    async def verify_checkout(self, page: Page) -> Optional[dict]:
        return await analyser.verify_checkout(page, self.delegate.client)

    async def close(self):
        await self.delegate.close()
