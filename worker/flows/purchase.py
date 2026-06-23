import asyncio
import random
from typing import List, Dict, Optional
from browser.challenge import get_qi_frames
from flows.queue import click_text

async def try_selector(page, behavior, selector: str, hover_delay: bool = True) -> bool:
    for frame in get_qi_frames(page):
        try:
            loc = frame.locator(selector).first
            if await loc.count() == 0 or not await loc.is_visible():
                continue
            box = await loc.bounding_box()
            if not box:
                continue

            if hover_delay and frame == page:
                hover_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                hover_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                await behavior.move_to(page, hover_x, hover_y)
                await asyncio.sleep(random.uniform(0.3, 0.8))

            if box and frame == page:
                click_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                click_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                await behavior.click(page, click_x, click_y)
            else:
                await loc.click(timeout=3000)
            return True
        except Exception:
            continue
    return False

async def scroll_and_try_selector(
    page, behavior, selector: str, max_px: int = 3000, step_px: int = 280
) -> bool:
    if await try_selector(page, behavior, selector):
        return True

    async def _check(p):
        for frame in get_qi_frames(p):
            try:
                loc = frame.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                pass
        return False

    found = await behavior.human_scroll_search(
        page, _check, max_scroll_px=max_px, step_px=step_px
    )
    if found:
        return await try_selector(page, behavior, selector)
    return False

async def select_show_date(
    page,
    behavior,
    pref: str,
    show_dates: List[str],
    log_func
) -> bool:
    await log_func(f"📅 กำลังเลือกรอบการแสดง (preference: {pref or 'auto-first'})...", "INFO")

    radio_selectors = [
        "input[name='show-date']",
        "input[name*='show'][type='radio']",
        "input[name*='date'][type='radio']",
        "input[name*='round'][type='radio']",
        "input[name*='showtime'][type='radio']",
    ]

    for frame in get_qi_frames(page):
        for sel in radio_selectors:
            try:
                radios = await frame.locator(sel).all()
                if not radios:
                    continue

                target_radio = None
                target_label = ""

                if pref:
                    for radio in radios:
                        try:
                            val = await radio.get_attribute("value") or ""
                            if val == pref:
                                target_radio = radio
                                target_label = val
                                break
                        except Exception:
                            pass

                    if not target_radio and pref.isdigit():
                        idx = int(pref) - 1
                        if 0 <= idx < len(radios):
                            target_radio = radios[idx]
                            try:
                                target_label = await target_radio.get_attribute("value") or f"option {idx + 1}"
                            except Exception:
                                target_label = f"option {idx + 1}"

                    if not target_radio:
                        for radio in radios:
                            try:
                                val = await radio.get_attribute("value") or ""
                                if pref in val or val in pref:
                                    target_radio = radio
                                    target_label = val
                                    break
                            except Exception:
                                pass

                if not target_radio:
                    for radio in radios:
                        try:
                            if await radio.is_visible():
                                target_radio = radio
                                target_label = await radio.get_attribute("value") or "first option"
                                break
                        except Exception:
                            pass

                if target_radio:
                    try:
                        label_el = target_radio.locator("xpath=ancestor::label").first
                        if await label_el.count() > 0 and await label_el.is_visible():
                            if behavior:
                                box = await label_el.bounding_box()
                                if box:
                                    click_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                                    click_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                                    await behavior.click(page, click_x, click_y)
                                else:
                                    await label_el.click(timeout=3000)
                            else:
                                await label_el.click(timeout=3000)
                            await log_func(f"📅 เลือกรอบการแสดง: {target_label} (คลิก label)", "INFO")
                            await asyncio.sleep(random.uniform(0.3, 0.7))
                            return True
                    except Exception:
                        pass

                    try:
                        if behavior:
                            box = await target_radio.bounding_box()
                            if box:
                                await behavior.click(
                                    page,
                                    box["x"] + box["width"] / 2,
                                    box["y"] + box["height"] / 2,
                                )
                            else:
                                await target_radio.click(timeout=3000)
                        else:
                            await target_radio.click(timeout=3000)
                        await log_func(f"📅 เลือกรอบการแสดง: {target_label} (คลิก radio)", "INFO")
                        await asyncio.sleep(random.uniform(0.3, 0.7))
                        return True
                    except Exception:
                        pass

            except Exception:
                continue

    preferred_texts = []
    other_texts = []
    for txt in show_dates:
        if pref and pref in txt:
            preferred_texts.append(txt)
        else:
            other_texts.append(txt)
    ordered_texts = preferred_texts + other_texts

    for txt in ordered_texts:
        clicked = await click_text(page, behavior, [txt])
        if clicked:
            await log_func(f"📅 เลือกรอบการแสดงด้วย text: '{txt}'", "INFO")
            await asyncio.sleep(random.uniform(0.3, 0.7))
            return True

    return False

async def select_ticket_quantity(
    page,
    behavior,
    ticket_count: int,
    log_func
) -> bool:
    qty = str(ticket_count)
    qty_selectors = [
        "select[name*='qty']", "select[name*='quantity']",
        "select[name*='Qty']", "select[name*='Quantity']",
        "select[name*='ticket']", "select[name*='Ticket']",
        "select[id*='qty']", "select[id*='quantity']",
        "select[id*='ticket']",
        "select.qty-select", "select.ticket-qty",
        "select[data-qty]", "select[data-quantity]",
    ]
    num_input_selectors = [
        "input[type='number'][name*='qty']",
        "input[type='number'][name*='quantity']",
        "input[type='number'][name*='ticket']",
        "input[type='number'][id*='qty']",
        "input[type='number'][id*='quantity']",
    ]
    try:
        for frame in get_qi_frames(page):
            for sel in qty_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        if behavior:
                            box = await loc.bounding_box()
                            if box:
                                await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                await behavior.think(0.2, 0.4)
                        await loc.select_option(value=qty)
                        await log_func(f"🎫 เลือกจำนวนตั๋ว = {qty} (dropdown)", "INFO")
                        return True
                except Exception:
                    try:
                        await loc.select_option(label=qty)
                        await log_func(f"🎫 เลือกจำนวนตั๋ว = {qty} (dropdown/label)", "INFO")
                        return True
                    except Exception:
                        pass

            for sel in num_input_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        if behavior:
                            box = await loc.bounding_box()
                            if box:
                                await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                            await behavior.type_text(page, qty, mistake_prob=0.0)
                        else:
                            await loc.fill(qty)
                        await log_func(f"🎫 กรอกจำนวนตั๋ว = {qty} (input)", "INFO")
                        return True
                except Exception:
                    pass

            try:
                plus_loc = frame.locator(
                    "button:has-text('+'), button.qty-plus, button.btn-plus, "
                    "button[aria-label='increase'], button[data-action='increase']"
                ).first
                if await plus_loc.count() > 0 and await plus_loc.is_visible():
                    for _ in range(ticket_count - 1):
                        if behavior:
                            box = await plus_loc.bounding_box()
                            if box:
                                await behavior.click(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                            else:
                                await plus_loc.click(timeout=2000)
                        else:
                            await plus_loc.click(timeout=2000)
                        await asyncio.sleep(random.uniform(0.15, 0.4))
                    await log_func(f"🎫 กด + เพิ่มจำนวนตั๋วเป็น {qty}", "INFO")
                    return True
            except Exception:
                pass

        await log_func(f"⚠️ ไม่พบตัวเลือกจำนวนตั๋วบนหน้านี้ (ต้องการ {qty} ใบ)", "WARN")
        return False
    except Exception as e:
        await log_func(f"⚠️ เลือกจำนวนตั๋วไม่สำเร็จ: {e}", "WARN")
        return False
