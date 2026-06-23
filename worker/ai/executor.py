import os
import json
import base64
import asyncio
import hashlib
import logging
from typing import Dict, Any, Optional, List
from playwright.async_api import Page
from ai.client import GeminiClient
from ai.prompts import (
    BASE_INSTRUCTION, RESPONSE_SCHEMA, MULTI_STEP_INSTRUCTION,
    build_seat_selection_prompt, build_show_date_prompt, PHASE_PROMPTS
)
from ai.analyser import get_dom_context

logger = logging.getLogger("AIRecovery")

class AIVisualRecoveryManager:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-pro"):
        self.client = GeminiClient(api_key, model_name)
        self.default_model = model_name
        
        self._cache: Dict[str, dict] = {}
        self._cache_max = 20

        self.recovery_attempts: Dict[str, int] = {}
        self.max_attempts_per_state = 3
        self._current_phase: str = "generic"

        self._last_url: str = ""
        self._last_dom_snippet: str = ""
        self._last_failed_action: Optional[dict] = None
        self._consecutive_no_change = 0

        self._pending_steps: List[dict] = []

    def _screenshot_hash(self, image_data: bytes) -> str:
        return hashlib.md5(image_data).hexdigest()

    def _build_prompt(
        self,
        phase: str,
        viewport_width: int,
        viewport_height: int,
        dom_context: str = "",
        failed_action_hint: str = "",
        seat_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        base = BASE_INSTRUCTION.format(w=viewport_width, h=viewport_height)

        if phase in ("seat_selection", "add_to_cart") and seat_context:
            phase_block = build_seat_selection_prompt(
                seat_color_priorities=seat_context.get("seat_color_priorities"),
                zone_name_priorities=seat_context.get("zone_name_priorities"),
                scroll_info=seat_context.get("scroll_info"),
            )
        elif phase == "show_date_selection" and seat_context:
            phase_block = build_show_date_prompt(
                show_dates=seat_context.get("show_dates"),
                show_date_preference=seat_context.get("show_date_preference"),
            )
        else:
            phase_block = PHASE_PROMPTS.get(phase, PHASE_PROMPTS["generic"])

        parts = [base, phase_block]

        if dom_context:
            parts.append(
                f"\nADDITIONAL CONTEXT — visible text and buttons on this page "
                f"(first 2000 chars):\n```\n{dom_context[:2000]}\n```\n"
            )

        if failed_action_hint:
            parts.append(
                f"\n⚠️ PREVIOUS ATTEMPT FAILED: The last AI action did NOT change "
                f"the page state. The failed action was:\n{failed_action_hint}\n"
                f"Try a DIFFERENT action or coordinate this time.\n"
            )

        parts.append(MULTI_STEP_INSTRUCTION)
        parts.append(RESPONSE_SCHEMA)

        return "\n".join(parts)

    def _check_page_changed(self, current_url: str, current_dom: str) -> bool:
        changed = (
            current_url != self._last_url
            or current_dom[:500] != self._last_dom_snippet[:500]
        )
        self._last_url = current_url
        self._last_dom_snippet = current_dom[:500]
        return changed

    def reset_phase(self, phase: str) -> None:
        if phase != self._current_phase:
            old = self._current_phase
            self._current_phase = phase
            keys_to_clear = [k for k in self.recovery_attempts if k.startswith(f"{old}_")]
            for k in keys_to_clear:
                del self.recovery_attempts[k]
            self._pending_steps.clear()
            self._last_failed_action = None
            self._consecutive_no_change = 0
            logger.info(f"🔄 AI Phase changed: {old} → {phase}")

    async def attempt_recovery(
        self,
        page: Page,
        screenshot_dir: str = "tmp",
        behavior=None,
        phase: str = "generic",
        seat_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if not self.client.is_api_ready():
            return False

        self.reset_phase(phase)

        if self._pending_steps:
            step = self._pending_steps.pop(0)
            logger.info(f"📋 Executing queued step: {step.get('description', 'N/A')}")
            executed = await self._execute_action(page, step, behavior)
            if executed:
                try:
                    dom = await page.inner_text("body")
                    if not self._check_page_changed(page.url, dom[:500]):
                        self._consecutive_no_change += 1
                        if self._consecutive_no_change >= 2:
                            logger.warning("⚠️ Queued steps not changing page — clearing plan")
                            self._pending_steps.clear()
                            self._consecutive_no_change = 0
                    else:
                        self._consecutive_no_change = 0
                except Exception:
                    pass
            return executed

        viewport = page.viewport_size
        if not viewport:
            logger.error("Could not retrieve viewport size from Playwright page.")
            return False

        w, h = viewport["width"], viewport["height"]

        os.makedirs(screenshot_dir, exist_ok=True)
        temp_img_path = os.path.join(screenshot_dir, "ai_recovery_state.png")

        try:
            await page.screenshot(path=temp_img_path)
            logger.info(f"Captured screenshot for AI analysis: {w}x{h} (phase={phase})")

            with open(temp_img_path, "rb") as f:
                image_bytes = f.read()

            img_hash = self._screenshot_hash(image_bytes)
            cache_key = f"{phase}:{img_hash}"
            if cache_key in self._cache:
                logger.info("⚡ Cache hit — reusing previous AI analysis")
                decision = self._cache[cache_key]
            else:
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                dom_context = await get_dom_context(page)

                failed_hint = ""
                if self._last_failed_action:
                    failed_hint = json.dumps(self._last_failed_action, ensure_ascii=False)

                prompt = self._build_prompt(
                    phase, w, h, dom_context, failed_hint,
                    seat_context=seat_context,
                )

                model = self.client.select_model(phase)
                logger.info(f"🧠 Using model: {model} for phase: {phase}")

                decision = await self.client.call_gemini(image_b64, prompt, model)
                if not decision:
                    return False

                if len(self._cache) >= self._cache_max:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]
                self._cache[cache_key] = decision

            logger.info(f"AI Decision: {json.dumps(decision, ensure_ascii=False)[:300]}")
            status = decision.get("status")

            if status == "no_action_needed":
                return False

            if status == "human_intervention_required":
                logger.warning(f"🚨 AI requested human intervention: {decision.get('explanation')}")
                return False

            if status == "action_required":
                action = decision.get("action")
                coords = decision.get("coordinates")

                if not coords or "x" not in coords or "y" not in coords:
                    logger.error("AI response is missing valid coordinates.")
                    return False

                x, y = int(coords["x"]), int(coords["y"])

                state_key = f"{phase}_{action}_{x}_{y}"
                self.recovery_attempts[state_key] = self.recovery_attempts.get(state_key, 0) + 1
                if self.recovery_attempts[state_key] > self.max_attempts_per_state:
                    logger.warning(f"⚠️ Limit reached for state {state_key}. Aborting to prevent ban.")
                    return False

                try:
                    pre_url = page.url
                    pre_dom = (await page.inner_text("body"))[:500]
                except Exception:
                    pre_url = ""
                    pre_dom = ""

                executed = await self._execute_action(page, decision, behavior)

                if executed:
                    await asyncio.sleep(0.8)
                    try:
                        post_url = page.url
                        post_dom = (await page.inner_text("body"))[:500]
                        if not self._check_page_changed(post_url, post_dom):
                            self._consecutive_no_change += 1
                            self._last_failed_action = {
                                "action": action,
                                "x": x,
                                "y": y,
                                "explanation": decision.get("explanation", ""),
                            }
                            if self._consecutive_no_change >= 3:
                                logger.warning("⚠️ 3 consecutive AI actions had no effect — pausing AI")
                                return False
                        else:
                            self._consecutive_no_change = 0
                            self._last_failed_action = None
                    except Exception:
                        pass

                    steps = decision.get("steps", [])
                    if len(steps) > 1:
                        self._pending_steps = steps[1:]
                        logger.info(f"📋 Queued {len(self._pending_steps)} additional steps from AI plan")

                return executed

        except Exception as e:
            logger.error(f"Exception during AI recovery cycle: {e}")
        finally:
            if os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except Exception:
                    pass

        return False

    async def _execute_action(self, page: Page, decision: dict, behavior=None) -> bool:
        action = decision.get("action")
        coords = decision.get("coordinates", {})
        x = int(coords.get("x", 0))
        y = int(coords.get("y", 0))

        try:
            if action == "click":
                logger.info(f"👉 AI Action: Clicking coordinates ({x}, {y})")
                if behavior:
                    await behavior.click(page, x, y)
                    await asyncio.sleep(1.0)
                else:
                    await page.mouse.click(x, y)
                    await asyncio.sleep(1.0)
                return True

            elif action == "drag_slider":
                offset_x = int(decision.get("drag_offset_x", 0))
                if offset_x == 0:
                    logger.error("Drag action requested but drag_offset_x is 0.")
                    return False

                logger.info(f"↔️ AI Action: Dragging from ({x}, {y}) horizontally by {offset_x}px")
                if behavior:
                    await behavior.move_to(page, x, y)
                    await asyncio.sleep(0.2)
                    await page.mouse.down()
                    await asyncio.sleep(0.1)
                    await behavior.move_to(page, x + offset_x, y)
                    await asyncio.sleep(0.3)
                    await page.mouse.up()
                    await asyncio.sleep(1.5)
                return True

            elif action == "drag_to":
                target = decision.get("target_coordinates")
                if not target or "x" not in target or "y" not in target:
                    logger.error("Drag-to action requested but target_coordinates missing.")
                    return False

                tx, ty = int(target["x"]), int(target["y"])
                logger.info(f"↖️ AI Action: Dragging from ({x}, {y}) to ({tx}, {ty})")

                if behavior:
                    await behavior.move_to(page, x, y)
                    await asyncio.sleep(0.3)
                    await page.mouse.down()
                    await asyncio.sleep(0.1)
                    await behavior.move_to(page, tx, ty)
                    await asyncio.sleep(0.4)
                    await page.mouse.up()
                    await asyncio.sleep(1.5)
                return True

            elif action == "type":
                text = decision.get("type_text", "")
                if not text:
                    logger.error("Type action requested but type_text is empty.")
                    return False
                logger.info(f"⌨️ AI Action: Clicking ({x}, {y}) and typing text")
                if behavior:
                    await behavior.click(page, x, y)
                    await asyncio.sleep(0.3)
                    await behavior.type_text(page, text, mistake_prob=0.02)
                else:
                    await page.mouse.click(x, y)
                    await asyncio.sleep(0.3)
                    await page.keyboard.type(text, delay=80)
                await asyncio.sleep(0.5)
                return True

            elif action == "scroll_down":
                amount = int(decision.get("scroll_amount", 400))
                logger.info(f"📜 AI Action: Scroll down by {amount}px")
                if behavior:
                    await behavior.scroll(page, total=amount)
                else:
                    scrolled = 0
                    while scrolled < amount:
                        step = min(120, amount - scrolled)
                        try:
                            await page.mouse.wheel(0, step)
                        except Exception:
                            pass
                        scrolled += step
                        await asyncio.sleep(0.08)
                await asyncio.sleep(0.5)
                return True

            elif action == "wait":
                logger.info("⏳ AI Action: Wait (no immediate action needed)")
                return False

        except Exception as e:
            logger.error(f"Error executing AI action '{action}': {e}")

        return False

    async def close(self):
        await self.client.close()
