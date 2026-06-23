import asyncio
import random
from typing import List
from browser.challenge import get_qi_frames

async def click_text(page, behavior, texts: List[str], wait_hidden: bool = False) -> bool:
    """Click the first visible button/link/role=button matching any text.
    Searches the main page AND all iframes, with a human-like click.
    """
    for frame in get_qi_frames(page):
        for txt in texts:
            for sel in (
                f"button:has-text('{txt}')",
                f"a:has-text('{txt}')",
                f"[role=button]:has-text('{txt}')",
                f"input[value='{txt}']",
            ):
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() == 0 or not await loc.is_visible():
                        continue
                    box = await loc.bounding_box()
                    if box and frame == page:
                        # Check if element is outside viewport → scroll first
                        centre_y = box["y"] + box["height"] / 2
                        if centre_y < 0 or centre_y > behavior.vh:
                            await behavior.scroll_to_element(page, loc)
                            box = await loc.bounding_box()
                            if not box:
                                continue
                        click_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                        click_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                        await behavior.click(page, click_x, click_y)
                    else:
                        await loc.click(timeout=3000)

                    if wait_hidden:
                        try:
                            await loc.wait_for(state="hidden", timeout=3000)
                        except Exception:
                            pass
                    return True
                except Exception:
                    continue
    return False

async def is_in_queue(page, queue_markers: List[str]) -> bool:
    try:
        url = (page.url or "").lower()
        if any(p in url for p in ("/seats", "/member-code", "/checkout", "/payment")):
            return False
        if any(m.lower() in url for m in queue_markers):
            return True
        for frame in get_qi_frames(page):
            try:
                body = (await frame.inner_text("body"))[:4000].lower()
            except Exception:
                continue
            for m in ("entry zone", "buying queue", "waiting room", "you are now in",
                      "please wait", "your turn", "ห้องรอ", "กำลังรอ"):
                if m in body:
                    return True
    except Exception:
        pass
    return False

async def is_on_purchase_page(page, queue_markers: List[str], seat_selector: str, addtocart_selector: str) -> bool:
    try:
        if await is_in_queue(page, queue_markers):
            return False

        for frame in get_qi_frames(page):
            try:
                # Check if any matching seat selector elements are actually visible
                seat_loc = frame.locator(seat_selector)
                seat_count = await seat_loc.count()
                for i in range(seat_count):
                    try:
                        if await seat_loc.nth(i).is_visible():
                            return True
                    except Exception:
                        pass

                # Check if any matching add-to-cart/submit elements are actually visible
                cart_loc = frame.locator(addtocart_selector)
                cart_count = await cart_loc.count()
                for i in range(cart_count):
                    try:
                        if await cart_loc.nth(i).is_visible():
                            return True
                    except Exception:
                        pass

                body = (await frame.inner_text("body"))[:4000].lower()
            except Exception:
                continue
                
            if "ผ่านคิวแล้ว" in body or "admitted" in body:
                return False
                
            if any(k in body for k in ("เลือกที่นั่ง", "เลือกโซน", "select seat", "ใส่ตะกร้า", "add to cart")):
                return True
    except Exception:
        pass
    return False
