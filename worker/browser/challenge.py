import asyncio
import random
from typing import List, Optional

def get_qi_frames(page):
    try:
        return [page] + [f for f in page.frames]
    except Exception:
        return [page]

async def is_human_challenge_visible(page, hv_markers: List[str]) -> bool:
    markers = [m.lower() for m in hv_markers]
    for frame in get_qi_frames(page):
        try:
            body = (await frame.inner_text("body"))[:8000].lower()
        except Exception:
            continue
        if any(m in body for m in markers):
            return True
    return False

async def human_click_locator(page, frame, loc, behavior=None) -> bool:
    try:
        if await loc.count() == 0 or not await loc.is_visible():
            return False
        box = await loc.bounding_box()
        if behavior is not None and box and frame == page:
            await behavior.click(
                page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
        else:
            await loc.click(timeout=4000)
        return True
    except Exception:
        return False

async def try_tick_robot_checkbox(page, behavior, robot_texts: List[str]) -> bool:
    ticked = False
    for frame in get_qi_frames(page):
        for sel in ("input[type='checkbox']", "[role='checkbox']"):
            try:
                boxes = frame.locator(sel)
                n = await boxes.count()
                for i in range(min(n, 4)):
                    box_loc = boxes.nth(i)
                    if not await box_loc.is_visible():
                        continue
                    try:
                        if await box_loc.is_checked():
                            ticked = True
                            continue
                    except Exception:
                        pass
                    if await human_click_locator(page, frame, box_loc, behavior):
                        ticked = True
            except Exception:
                pass

        for txt in robot_texts:
            for getter in (
                lambda f, t=txt: f.get_by_label(t, exact=False),
                lambda f, t=txt: f.get_by_text(t, exact=False),
            ):
                try:
                    loc = getter(frame).first
                    if await human_click_locator(page, frame, loc, behavior):
                        ticked = True
                        break
                except Exception:
                    continue
            if ticked:
                break
    return ticked

async def try_click_proceed_after_human_check(page, behavior, proceed_texts: List[str]) -> bool:
    for frame in get_qi_frames(page):
        for sel in (
            "#btn-akamai-challenge",
            "#akamai-challenge-modal button",
            "button.ticket-btn",
        ):
            try:
                loc = frame.locator(sel).first
                if await human_click_locator(page, frame, loc, behavior):
                    return True
            except Exception:
                pass
        for txt in proceed_texts:
            for getter in (
                lambda f, t=txt: f.get_by_role("button", name=t),
                lambda f, t=txt: f.get_by_text(t, exact=False),
            ):
                try:
                    loc = getter(frame).first
                    if await human_click_locator(page, frame, loc, behavior):
                        return True
                except Exception:
                    continue
            for sel in (
                f"button:has-text('{txt}')",
                f"input[type='submit'][value='{txt}']",
                f"input[value='{txt}']",
            ):
                try:
                    loc = frame.locator(sel).first
                    if await human_click_locator(page, frame, loc, behavior):
                        return True
                except Exception:
                    continue
    return False

async def solve_human_challenge(
    page,
    behavior,
    hv_markers: List[str],
    robot_texts: List[str],
    proceed_texts: List[str],
    update_status_func,
    log_func
) -> bool:
    if not await is_human_challenge_visible(page, hv_markers):
        return False

    update_status_func("SOLVING_CHALLENGE")

    ticked = await try_tick_robot_checkbox(page, behavior, robot_texts)
    if ticked:
        await asyncio.sleep(random.uniform(0.5, 1.2))

    proceeded = await try_click_proceed_after_human_check(page, behavior, proceed_texts)
    if ticked or proceeded:
        await log_func("✅ ผ่านหน้ายืนยันมนุษย์ (Akamai): ติ๊กช่อง + กด Proceed แล้ว", "INFO")
        await asyncio.sleep(random.uniform(0.8, 1.6))
        return True
    return False

async def solve_final_captcha(page, behavior, log_func) -> bool:
    """
    Solve the final stage CAPTCHA on the ticket platform without using AI.
    Handles 5 captcha types: Quiz, Slider, Color Match, Sort Fan, Sort Lyric.
    Follows human behavior guidelines.
    """
    try:
        modal = page.locator("#final-captcha-modal").first
        if await modal.count() == 0 or not await modal.is_visible():
            return False

        # Detect active captcha type
        quiz_loc = page.locator("#captcha-quiz")
        slider_loc = page.locator("#captcha-slider")
        color_loc = page.locator("#captcha-color")
        sort_fan_loc = page.locator("#captcha-sort-fan")
        sort_lyric_loc = page.locator("#captcha-sort-lyric")

        # 1. QUIZ CAPTCHA
        if await quiz_loc.is_visible():
            await log_func("🧩 [CAPTCHA] ตรวจพบประเภท: Quiz (ตอบคำถาม)", "INFO")
            # Find options
            options = page.locator(".quiz-option-btn")
            n = await options.count()
            target_text = "7 สีคอนเสิร์ต"
            clicked = False
            for i in range(n):
                opt = options.nth(i)
                text = (await opt.inner_text()).strip()
                if text == target_text:
                    await log_func(f"👉 กำลังคลิกคำตอบ: '{target_text}'", "INFO")
                    box = await opt.bounding_box()
                    if box:
                        await behavior.click(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                        clicked = True
                        break
            if not clicked:
                await log_func(f"⚠️ ไม่พบตัวเลือกคำตอบ '{target_text}'", "WARN")
                return False
            await asyncio.sleep(random.uniform(0.5, 1.0))
            return True

        # 2. SLIDER CAPTCHA
        elif await slider_loc.is_visible():
            await log_func("🧩 [CAPTCHA] ตรวจพบประเภท: Slider (เลื่อนจิ๊กซอว์)", "INFO")
            # Get target percent from slot element style
            target_percent = await page.evaluate("""() => {
                const slot = document.getElementById("slider-slot");
                if (!slot) return null;
                const m = slot.style.left.match(/calc\(([\d.]+)%/);
                return m ? parseFloat(m[1]) : null;
            }""")
            if target_percent is None:
                # Fallback to random if slot not found
                target_percent = 50.0 + random.random() * 35.0
                await log_func("⚠️ ไม่พบข้อมูลเปอร์เซ็นต์เป้าหมายผ่านสไตล์ ใช้ค่าสุ่มแทน", "WARN")
            
            await log_func(f"👉 เป้าหมายสไลเดอร์: {target_percent:.2f}%", "INFO")
            
            slider_input = page.locator("#slider-input").first
            await slider_input.scroll_into_view_if_needed()
            box = await slider_input.bounding_box()
            if not box:
                await log_func("⚠️ ไม่พบตำแหน่งของปุ่มสไลด์", "WARN")
                return False
                
            x_start = box["x"] + 10
            y = box["y"] + box["height"] / 2
            # Bounding box width minus padding for slide
            track_w = box["width"] - 20
            x_target = x_start + (target_percent / 100.0) * track_w
            
            # Simulate human drag behavior
            await behavior.move_to(page, x_start, y)
            await asyncio.sleep(random.uniform(0.2, 0.4))
            await page.mouse.down()
            await asyncio.sleep(random.uniform(0.1, 0.2))
            
            # Drag smoothly with helper
            await behavior.move_to(page, x_target, y)
            await asyncio.sleep(random.uniform(0.2, 0.4))
            await page.mouse.up()
            await asyncio.sleep(random.uniform(0.5, 0.8))
            
            # Click verify
            verify_btn = page.locator("#btn-verify-slider").first
            btn_box = await verify_btn.bounding_box()
            if btn_box:
                await behavior.click(page, btn_box["x"] + btn_box["width"] / 2, btn_box["y"] + btn_box["height"] / 2)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                return True
            return False

        # 3. COLOR MATCH CAPTCHA
        elif await color_loc.is_visible():
            await log_func("🧩 [CAPTCHA] ตรวจพบประเภท: Color Match (คลิกสีที่ตรงกัน)", "INFO")
            matching_idx = await page.evaluate("""() => {
                const target = document.getElementById("color-target");
                if (!target) return -1;
                const targetColor = window.getComputedStyle(target).backgroundColor;
                const boxes = document.querySelectorAll("#color-grid .color-box");
                for (let i = 0; i < boxes.length; i++) {
                    if (window.getComputedStyle(boxes[i]).backgroundColor === targetColor) {
                        return i;
                    }
                }
                return -1;
            }""")
            
            if matching_idx == -1:
                await log_func("⚠️ ไม่พบกล่องสีที่ตรงกับสีเป้าหมาย", "WARN")
                return False
                
            color_box = page.locator("#color-grid .color-box").nth(matching_idx)
            box = await color_box.bounding_box()
            if box:
                await behavior.click(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                await asyncio.sleep(random.uniform(0.5, 0.8))
                
                # Click verify button
                verify_btn = page.locator("#btn-verify-color").first
                btn_box = await verify_btn.bounding_box()
                if btn_box:
                    await behavior.click(page, btn_box["x"] + btn_box["width"] / 2, btn_box["y"] + btn_box["height"] / 2)
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    return True
            return False

        # 4 & 5. ITEM SORT CAPTCHAs (Fan and Lyric)
        elif await sort_fan_loc.is_visible() or await sort_lyric_loc.is_visible():
            captcha_type = "fan" if await sort_fan_loc.is_visible() else "lyric"
            await log_func(f"🧩 [CAPTCHA] ตรวจพบประเภท: Sort ({captcha_type.upper()}) (เรียงภาพ/ประโยค)", "INFO")
            
            list_selector = f"#sortable-{captcha_type} .sortable-item"
            items = page.locator(list_selector)
            n = await items.count()
            
            # Sort items by data-id (ascending order: 0, 1, 2, 3, 4)
            # We sort indices 0 to n-2. The last item (n-1) will automatically fall into place.
            for target_idx in range(n - 1):
                # Retrieve current DOM state inside the loop since elements shift
                items = page.locator(list_selector)
                current_ids = []
                for idx in range(n):
                    data_id = await items.nth(idx).get_attribute("data-id")
                    current_ids.append(int(data_id) if data_id is not None else -1)
                
                if current_ids[target_idx] == target_idx:
                    continue
                    
                src_idx = current_ids.index(target_idx)
                src_item = items.nth(src_idx)
                tgt_item = items.nth(target_idx)
                
                await src_item.scroll_into_view_if_needed()
                await tgt_item.scroll_into_view_if_needed()
                
                box_src = await src_item.bounding_box()
                box_tgt = await tgt_item.bounding_box()
                
                if not box_src or not box_tgt:
                    await log_func("⚠️ ไม่สามารถระบุตำแหน่งของรายการเรียงลำดับได้", "WARN")
                    return False
                    
                x_src = box_src["x"] + box_src["width"] / 2
                y_src = box_src["y"] + box_src["height"] / 2
                
                x_tgt = box_tgt["x"] + box_tgt["width"] / 2
                # Drop in the upper quarter of the target element to insert before it
                y_tgt = box_tgt["y"] + box_tgt["height"] * 0.25
                
                await log_func(f"🔄 กำลังย้ายชิ้นส่วน id={target_idx} ไปตำแหน่งที่ {target_idx}", "INFO")
                
                # Human drag
                await behavior.move_to(page, x_src, y_src)
                await asyncio.sleep(random.uniform(0.2, 0.3))
                await page.mouse.down()
                await asyncio.sleep(random.uniform(0.1, 0.2))
                await behavior.move_to(page, x_tgt, y_tgt)
                await asyncio.sleep(random.uniform(0.3, 0.5))
                await page.mouse.up()
                await asyncio.sleep(random.uniform(0.8, 1.2)) # Wait for DOM to adjust
                
            # Click verify button
            verify_btn = page.locator(f"#btn-verify-{captcha_type}").first
            btn_box = await verify_btn.bounding_box()
            if btn_box:
                await behavior.click(page, btn_box["x"] + btn_box["width"] / 2, btn_box["y"] + btn_box["height"] / 2)
                await asyncio.sleep(random.uniform(0.5, 1.0))
                return True
            return False
            
        else:
            await log_func("⚠️ ตรวจพบ CAPTCHA modal แต่ไม่สามารถระบุประเภทได้", "WARN")
            return False
            
    except Exception as e:
        await log_func(f"⚠️ เกิดข้อผิดพลาดขณะแก้ไข CAPTCHA: {e}", "ERROR")
        return False

