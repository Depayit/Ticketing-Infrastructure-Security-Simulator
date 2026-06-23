import asyncio
import random
import json
from datetime import datetime
from typing import Optional
from browser.challenge import get_qi_frames
from core.config import get_tg_bot_instances

async def select_promptpay_payment(page, behavior, log_func) -> bool:
    try:
        await log_func("🛒 [Checkout] เริ่มกระบวนการชำระเงิน...", "INFO")
        
        # 1. Uncheck Ticket Protect (ถ้ามี)
        try:
            protect_sel = "input[name*='protect'], input[id*='protect'], [data-name*='protect']"
            protect_checkbox = page.locator(protect_sel).first
            if await protect_checkbox.count() > 0 and await protect_checkbox.is_visible():
                if await protect_checkbox.is_checked():
                    await log_func("🛡️ กำลังยกเลิก Ticket Protect เพื่อประหยัดค่าใช้จ่าย", "INFO")
                    if behavior:
                        box = await protect_checkbox.bounding_box()
                        if box:
                            await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                        else:
                            await protect_checkbox.uncheck()
                    else:
                        await protect_checkbox.uncheck()
                    await asyncio.sleep(random.uniform(0.5, 1.0))
        except Exception:
            pass
            
        # 2. เลือกรับบัตรด้วยตนเอง (Self Pickup)
        try:
            pickup_sel = "label:has-text('รับบัตรด้วยตนเอง'), label:has-text('Pick up'), input[value*='pickup'], input[value*='self']"
            pickup_btn = page.locator(pickup_sel).first
            if await pickup_btn.count() > 0 and await pickup_btn.is_visible():
                if behavior:
                    box = await pickup_btn.bounding_box()
                    if box:
                        await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                    else:
                        await pickup_btn.click()
                else:
                    await pickup_btn.click()
                await asyncio.sleep(random.uniform(0.5, 1.0))
        except Exception:
            pass

        await log_func("💳 กำลังตรวจสอบและเลือกวิธีการชำระเงินแบบ PromptPay...", "INFO")
        
        body = (await page.inner_text("body"))[:4000].lower()
        if "qrcode" in body or "promptpay" in body or "พรอมต์เพย์" in body:
            selectors = [
                "label:has-text('PromptPay')", "label:has-text('Promptpay')", "label:has-text('พร้อมเพย์')",
                "input[value*='promptpay']", "input[value*='PromptPay']", "input[id*='promptpay']",
                "div:has-text('PromptPay')", "div:has-text('พร้อมเพย์')", ".payment-option-promptpay",
                "button:has-text('PromptPay')", "button:has-text('พร้อมเพย์')"
            ]
            
            selected = False
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        if behavior:
                            box = await el.bounding_box()
                            if box:
                                await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                            else:
                                await el.click()
                        else:
                            await el.click()
                        selected = True
                        await log_func("✅ คลิกเลือกวิธีชำระเงิน PromptPay แล้ว", "INFO")
                        await asyncio.sleep(random.uniform(0.5, 1.2))
                        break
                except Exception:
                    pass
            
            proceed_selectors = [
                "button:has-text('ชำระเงิน')", "button:has-text('ดำเนินการต่อ')", "button:has-text('ยืนยัน')",
                "button:has-text('Pay Now')", "button:has-text('Proceed')", "button[type='submit']",
                "input[type='submit']", "#btn-payment-submit"
            ]
            
            for p_sel in proceed_selectors:
                try:
                    p_el = page.locator(p_sel).first
                    if await p_el.count() > 0 and await p_el.is_visible():
                        if behavior:
                            box = await p_el.bounding_box()
                            if box:
                                await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                            else:
                                await p_el.click()
                        else:
                            await p_el.click()
                        await log_func("✅ คลิกปุ่มดำเนินการชำระเงินสำเร็จ (กำลังรอหน้า QR Code โหลด)", "INFO")
                        await asyncio.sleep(random.uniform(2.0, 3.5))
                        return True
                except Exception:
                    pass
                    
        return False
    except Exception as e:
        await log_func(f"⚠️ ไม่สามารถดำเนินการเลือก PromptPay อัตโนมัติ: {e}", "DEBUG")
        return False

async def notify_payment_ready(
    page,
    proxy: Optional[str],
    instance_id: str,
    qi_hold_seconds: int,
    r_client,
    config: dict,
    log_func
) -> None:
    url = ""
    shot_path = ""
    qr_shot_path = ""
    cookie_str = ""
    try:
        url = page.url
    except Exception:
        pass

    # 1. Wait for PromptPay QR code to become visible (up to 15 seconds)
    qr_selectors = [
        "img[src*='qr']", "img[class*='qr']", "img[id*='qr']", ".qr-image img", ".qrcode img", "canvas",
        "img[src*='promptpay']", "img[src*='PromptPay']", "img[src*='2c2p']", "div.qr-code img", 
        "[class*='qrcode'] img", "svg[class*='qr']", "svg[id*='qr']", ".qr-code-container img", 
        ".promptpay-qr img", ".promptpay-image", ".qr-payment img", "img[src*='payment']"
    ]
    
    await log_func("⏳ กำลังรอให้หน้าจอแสดง PromptPay QR Code...", "INFO")
    qr_found = False
    qr_shot_path = f"/app/qrcode_{instance_id}.png"
    
    for attempt in range(30):  # 30 * 0.5s = 15s max
        for frame in get_qi_frames(page):
            for sel in qr_selectors:
                try:
                    loc = frame.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        box = await loc.bounding_box()
                        if box and box["width"] > 20 and box["height"] > 20:
                            await loc.screenshot(path=qr_shot_path)
                            qr_found = True
                            await log_func("📸 บันทึกภาพตัดเฉพาะ QR Code PromptPay สำเร็จ", "INFO")
                            break
                except Exception:
                    pass
            if qr_found:
                break
        if qr_found:
            break
        await asyncio.sleep(0.5)
        
    if not qr_found:
        await log_func("⚠️ ตรวจไม่พบอิลิเมนต์ QR Code จาก Selector มาตรฐาน จะใช้การแคปหน้าจอเต็มเพื่อเป็นแผนสำรอง", "WARN")
        qr_shot_path = ""

    # 2. Capture full screen screenshot as fallback/additional detail
    try:
        shot_path = f"/app/payment_ready_{instance_id}.png"
        await page.screenshot(path=shot_path, full_page=True)
    except Exception as e:
        await log_func(f"⚠️ ไม่สามารถบันทึกสกรีนช็อตเต็มหน้าจอได้: {e}", "DEBUG")
        shot_path = ""

    # 3. Extract cookies for checkout session handoff
    try:
        ctx_cookies = await page.context.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in ctx_cookies)
    except Exception:
        pass

    handoff = {
        "worker": instance_id,
        "proxy": (proxy[-16:] if proxy else "direct"),
        "checkout_url": url,
        "cookies": cookie_str,
        "ts": datetime.now().isoformat(),
    }
    try:
        r_client.lpush("ttm:payment_ready", json.dumps(handoff))
        r_client.ltrim("ttm:payment_ready", 0, 50)
    except Exception:
        pass

    await log_func(
        f"🎟️ HOLD สำเร็จ! ล็อกที่นั่งได้แล้ว — เปิดลิงก์นี้เพื่อจ่าย (เหลือเวลา ~{qi_hold_seconds // 60} นาที):\n{url}",
        "SUCCESS",
    )
    try:
        bot_instances = get_tg_bot_instances(config)
        if bot_instances:
            # Send the QR code first if we found it
            if qr_shot_path:
                try:
                    with open(qr_shot_path, "rb") as fh:
                        qr_bytes = fh.read()
                        for bot, chat_id in bot_instances:
                            try:
                                await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=qr_bytes,
                                    caption=f"📲 สแกนจ่ายด้วยพร้อมเพย์ได้ทันที (PromptPay QR Code)\nบอท: {instance_id}\nรายละเอียดราคาและคิวอยู่ด้านล่าง",
                                )
                            except Exception as tg_err:
                                await log_func(f"⚠️ ไม่สามารถส่ง QR Code เข้า Telegram: {tg_err}", "DEBUG")
                except Exception as file_err:
                    await log_func(f"⚠️ อ่านไฟล์ QR Code ล้มเหลว: {file_err}", "DEBUG")
            
            # Send the full page screenshot next
            if shot_path:
                try:
                    with open(shot_path, "rb") as fh:
                        photo_bytes = fh.read()
                        for bot, chat_id in bot_instances:
                            try:
                                await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=photo_bytes,
                                    caption=f"🎟️ รายละเอียดการล็อกที่นั่งสำเร็จ\nลิงก์สำหรับเข้าดูคิว: {url}",
                                )
                            except Exception as tg_err:
                                await log_func(f"⚠️ ไม่สามารถส่งสกรีนช็อตเต็มเข้า Telegram: {tg_err}", "DEBUG")
                except Exception as file_err:
                    await log_func(f"⚠️ อ่านไฟล์สกรีนช็อตเต็มล้มเหลว: {file_err}", "DEBUG")
    except Exception as e:
        await log_func(f"⚠️ มีข้อผิดพลาดในขั้นตอนแจ้งเตือน Telegram: {e}", "DEBUG")
