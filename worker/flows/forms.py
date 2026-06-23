import asyncio
import random
from typing import List
from browser.challenge import get_qi_frames

async def fill_registration_names(
    page,
    behavior,
    ticket_buyers: List[str],
    log_func
) -> bool:
    if not ticket_buyers:
        await log_func("⚠️ ไม่มีชื่อ-นามสกุลผู้ใช้บัตรสำหรับกรอกฟอร์มลงทะเบียน", "WARN")
        return False

    filled_count = 0
    try:
        for frame in get_qi_frames(page):
            name_selectors = [
                "input[name*='name']", "input[name*='Name']",
                "input[placeholder*='ชื่อ']", "input[placeholder*='นามสกุล']",
                "input[placeholder*='Ticket']", "input[placeholder*='ticket']",
                "input[placeholder*='Name']", "input[placeholder*='name']",
            ]

            name_inputs = []
            for sel in name_selectors:
                try:
                    locs = await frame.locator(sel).all()
                    for loc in locs:
                        try:
                            if await loc.is_visible():
                                box = await loc.bounding_box()
                                is_dup = False
                                for existing in name_inputs:
                                    ebox = await existing.bounding_box()
                                    if ebox and box and abs(ebox["y"] - box["y"]) < 5:
                                        is_dup = True
                                        break
                                if not is_dup:
                                    name_inputs.append(loc)
                        except Exception:
                            pass
                except Exception:
                    pass

            if not name_inputs:
                try:
                    all_inputs = await frame.locator(
                        "input[type='text'], input:not([type])"
                    ).all()
                    for inp in all_inputs:
                        try:
                            if not await inp.is_visible():
                                continue
                            ph = (await inp.get_attribute("placeholder") or "").lower()
                            nm = (await inp.get_attribute("name") or "").lower()
                            aid = (await inp.get_attribute("id") or "").lower()
                            if any(k in ph + nm + aid for k in (
                                "ชื่อ", "นามสกุล", "name", "ticket", "fullname",
                                "register", "ลงทะเบียน",
                            )):
                                name_inputs.append(inp)
                        except Exception:
                            pass
                except Exception:
                    pass

            if not name_inputs:
                continue

            positioned = []
            for inp in name_inputs:
                try:
                    box = await inp.bounding_box()
                    if box:
                        positioned.append((box["y"], inp))
                except Exception:
                    positioned.append((9999, inp))
            positioned.sort(key=lambda x: x[0])
            sorted_inputs = [inp for _, inp in positioned]

            for i, inp in enumerate(sorted_inputs):
                if i >= len(ticket_buyers):
                    break
                buyer_name = ticket_buyers[i].strip()
                if not buyer_name:
                    continue
                try:
                    if behavior:
                        box = await inp.bounding_box()
                        if box:
                            await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                        else:
                            await inp.click()
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        await inp.fill("")
                        await behavior.type_text(page, buyer_name, mistake_prob=0.02)
                    else:
                        await inp.click()
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        await inp.fill("")
                        await inp.press_sequentially(buyer_name, delay=random.randint(40, 120))
                        
                    filled_count += 1
                    await log_func(f"📝 ลงทะเบียนลำดับที่ {i + 1}: {buyer_name}", "INFO")
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                except Exception as e:
                    await log_func(f"⚠️ กรอกชื่อลำดับที่ {i + 1} ไม่สำเร็จ: {e}", "WARN")

            if filled_count > 0:
                break

        if filled_count > 0:
            save_clicked = False
            save_texts = ["บันทึก", "Save", "ยืนยัน", "Confirm", "ดำเนินการต่อ", "Continue", "ถัดไป", "Next"]
            for frame in get_qi_frames(page):
                for txt in save_texts:
                    for sel in (
                        f"button:has-text('{txt}')",
                        f"input[type='submit'][value='{txt}']",
                        f"a:has-text('{txt}')",
                    ):
                        try:
                            loc = frame.locator(sel).first
                            if await loc.count() > 0 and await loc.is_visible():
                                if behavior:
                                    box = await loc.bounding_box()
                                    if box:
                                        await behavior.click(
                                            page,
                                            box["x"] + box["width"] / 2,
                                            box["y"] + box["height"] / 2,
                                        )
                                        save_clicked = True
                                        break
                                await loc.click(timeout=3000)
                                save_clicked = True
                                break
                        except Exception:
                            continue
                    if save_clicked:
                        break
                if save_clicked:
                    break

            if save_clicked:
                await log_func(f"✅ กรอกชื่อ-นามสกุลผู้ใช้บัตร {filled_count} คน + กดบันทึกแล้ว", "SUCCESS")
            else:
                await log_func(f"✅ กรอกชื่อ-นามสกุลผู้ใช้บัตร {filled_count} คนแล้ว (ไม่พบปุ่มบันทึก)", "SUCCESS")
            return True

        await log_func("⚠️ ไม่พบฟอร์มลงทะเบียนชื่อ-นามสกุลบนหน้านี้", "WARN")
        return False
    except Exception as e:
        await log_func(f"❌ กรอกชื่อผู้ใช้บัตรผิดพลาด: {e}", "ERROR")
        return False
