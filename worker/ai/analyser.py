import base64
import json
import logging
from typing import Optional
from playwright.async_api import Page
from ai.client import GeminiClient
from ai.prompts import BASE_INSTRUCTION, RESPONSE_SCHEMA, MULTI_STEP_INSTRUCTION

logger = logging.getLogger("AIRecovery")

async def get_dom_context(page: Page) -> str:
    try:
        body_text = await page.inner_text("body")
        body_text = body_text[:2000]

        try:
            buttons = await page.locator("button:visible, a:visible, [role=button]:visible").all_inner_texts()
            button_labels = [b.strip() for b in buttons[:20] if b.strip()]
            if button_labels:
                body_text += f"\n\n[VISIBLE BUTTONS]: {', '.join(button_labels)}"
        except Exception:
            pass

        try:
            inputs_info = []
            inputs = await page.locator("input:visible, select:visible").all()
            for inp in inputs[:15]:
                try:
                    name = await inp.get_attribute("name") or ""
                    placeholder = await inp.get_attribute("placeholder") or ""
                    inp_type = await inp.get_attribute("type") or "text"
                    if name or placeholder:
                        inputs_info.append(f"{inp_type}:{name or placeholder}")
                except Exception:
                    pass
            if inputs_info:
                body_text += f"\n[VISIBLE INPUTS]: {', '.join(inputs_info)}"
        except Exception:
            pass

        return body_text
    except Exception:
        return ""

async def analyze_purchase_page(page: Page, client: GeminiClient) -> Optional[dict]:
    if not client.is_api_ready():
        return None

    viewport = page.viewport_size
    if not viewport:
        return None

    w, h = viewport["width"], viewport["height"]

    try:
        screenshot_bytes = await page.screenshot()
        image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        dom_context = await get_dom_context(page)

        prompt = (
            BASE_INSTRUCTION.format(w=w, h=h)
            + "PHASE: PURCHASE PAGE PRE-SCAN\n"
            "Analyze this ticket purchase page thoroughly and identify ALL "
            "interactive elements. Your goal is to create a complete map of "
            "the page so the bot knows exactly what to do.\n\n"
            "Identify and report:\n"
            "1. Zone/section selection elements (VIP, GA, Standing, etc.)\n"
            "2. Seat map areas (if present) and which seats appear available\n"
            "3. Quantity dropdown or input\n"
            "4. 'Add to Cart' / 'ใส่ตะกร้า' / proceed buttons\n"
            "5. Any popups or overlays that need dismissal\n"
            "6. Registration/name input fields\n"
            "7. Showtime / round selection (รอบแสดง)\n\n"
            "Priority action: identify the FIRST thing that needs to be "
            "clicked to start the purchase process.\n\n"
            f"PAGE TEXT (first 2000 chars):\n```\n{dom_context[:2000]}\n```\n\n"
            + MULTI_STEP_INSTRUCTION
            + RESPONSE_SCHEMA
        )

        model = client.select_model("pre_scan")
        logger.info(f"🔍 AI Pre-scanning purchase page with {model}")
        result = await client.call_gemini(image_b64, prompt, model)

        if result:
            logger.info(f"🔍 Pre-scan result: {json.dumps(result, ensure_ascii=False)[:300]}")
        return result

    except Exception as e:
        logger.error(f"Error during purchase page pre-scan: {e}")
        return None

async def verify_checkout(page: Page, client: GeminiClient) -> Optional[dict]:
    if not client.is_api_ready():
        return None

    viewport = page.viewport_size
    if not viewport:
        return None

    w, h = viewport["width"], viewport["height"]

    try:
        screenshot_bytes = await page.screenshot()
        image_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        dom_context = await get_dom_context(page)

        prompt = (
            BASE_INSTRUCTION.format(w=w, h=h)
            + "PHASE: CHECKOUT VERIFICATION\n"
            "The bot has just filled in checkout/payment form data. "
            "Verify the following before proceeding:\n"
            "1. Are all required fields filled? (no red borders or error messages)\n"
            "2. Is there an error message visible? (e.g., 'กรุณากรอก...', 'Invalid...')\n"
            "3. Is the submit/pay button enabled and clickable?\n"
            "4. Is the correct payment method selected?\n"
            "5. Is the order summary/total visible and reasonable?\n\n"
            "If everything looks correct, set status='no_action_needed'.\n"
            "If there's an issue, set status='action_required' and specify what to fix.\n"
            "If the page shows a critical error, set status='human_intervention_required'.\n\n"
            f"PAGE TEXT:\n```\n{dom_context[:1500]}\n```\n\n"
            + RESPONSE_SCHEMA
        )

        model = client.select_model("verification")
        result = await client.call_gemini(image_b64, prompt, model)
        if result:
            logger.info(f"✅ Checkout verification: {result.get('status')} — {result.get('explanation', '')[:200]}")
        return result

    except Exception as e:
        logger.error(f"Error during checkout verification: {e}")
        return None
