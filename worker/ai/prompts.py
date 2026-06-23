from typing import Dict, Any, Optional, List

BASE_INSTRUCTION = (
    "You are an automated visual navigator agent analyzing a browser screenshot "
    "({w}x{h} pixels). Respond STRICTLY with a raw JSON object (no markdown, "
    "no ```json blocks).\n\n"
)

RESPONSE_SCHEMA = """
Response JSON Schema:
{
  "status": "action_required" | "no_action_needed" | "human_intervention_required",
  "action": "click" | "drag_slider" | "drag_to" | "wait" | "type" | "scroll_down",
  "coordinates": { "x": 0, "y": 0 },
  "drag_offset_x": 0,
  "scroll_amount": 400,
  "target_coordinates": { "x": 0, "y": 0 },
  "type_text": "",
  "steps": [
    {
      "action": "click" | "scroll_down",
      "coordinates": { "x": 0, "y": 0 },
      "scroll_amount": 400,
      "description": "Brief step description"
    }
  ],
  "explanation": "Brief description of what you decided to do",
  "detected_elements": {
    "buttons": ["list of visible button labels"],
    "inputs": ["list of visible input field descriptions"],
    "dynamic_selectors_hint": "CSS selector suggestion for key elements"
  }
}
"""

MULTI_STEP_INSTRUCTION = (
    "\nIMPORTANT: If you can identify 2-3 sequential actions needed to complete "
    "this phase, provide them in the 'steps' array. The first step's action and "
    "coordinates should also be set as the top-level action/coordinates. "
    "Also populate 'detected_elements' to help with future CSS selectors.\n"
)

PHASE_PROMPTS: Dict[str, str] = {
    "login": (
        "PHASE: LOGIN PAGE\n"
        "The bot needs to log in. Focus ONLY on:\n"
        "- Email/username and password input fields\n"
        "- Login/submit button\n"
        "- CAPTCHA checkbox or challenge\n"
        "- Error messages (wrong password, account locked, etc.)\n"
        "- 'Forgot password' or 'Register' links that may be blocking\n"
        "If login fields are already filled, find and click the submit button.\n"
        "If there's an error message, set status='human_intervention_required'.\n"
    ),
    "queue": (
        "PHASE: QUEUE / WAITING ROOM\n"
        "The user is in a Queue-it or similar waiting queue. Focus ONLY on:\n"
        "- 'Join the Queue' / 'เข้าคิว' button\n"
        "- 'Still here?' / 'Yes' / 'ยังอยู่' confirmation popup\n"
        "- Progress bar or queue position\n"
        "- Any popup or dialog that needs to be dismissed\n"
        "If the queue page is normal and waiting, set status='no_action_needed'.\n"
    ),
    "seat_selection": "",

    "registration": (
        "PHASE: TICKET REGISTRATION / NAME FORM\n"
        "The bot needs to fill registration names on tickets. Focus ONLY on:\n"
        "- Text input fields labeled ชื่อ-นามสกุล / Name / Ticket holder\n"
        "- The first empty input field that needs to be clicked/focused\n"
        "- 'บันทึก' / 'Save' / 'ยืนยัน' / 'Confirm' / 'ถัดไป' / 'Next' button\n"
        "If all name fields appear filled, find and click the save/submit button.\n"
    ),
    "add_to_cart": (
        "PHASE: ADD TO CART\n"
        "The bot has selected a seat and needs to add it to cart. Focus ONLY on:\n"
        "- 'ใส่ตะกร้า' / 'Add to Cart' / 'สั่งซื้อ' / 'ดำเนินการต่อ' button\n"
        "- 'Confirm' / 'ยืนยัน' button\n"
        "- Ticket quantity confirmation\n"
        "- Any checkbox for terms/conditions that needs to be checked\n"
        "- Ticket Protect opt-out checkbox\n"
    ),
    "checkout": (
        "PHASE: CHECKOUT / PAYMENT\n"
        "The bot is at the payment/checkout page. Focus ONLY on:\n"
        "- Payment method selection (PromptPay / QR Code / พร้อมเพย์ preferred)\n"
        "- 'ชำระเงิน' / 'Pay Now' / 'Proceed' / 'ดำเนินการต่อ' button\n"
        "- Ticket Protect uncheck option\n"
        "- Self-pickup / delivery method selection\n"
        "- QR Code image for PromptPay\n"
        "If a QR Code is visible, set status='no_action_needed' (payment ready).\n"
    ),
    "captcha": (
        "PHASE: CAPTCHA / CHALLENGE\n"
        "A CAPTCHA or visual challenge is blocking progress. Analyze carefully:\n"
        "- Trivia / Quiz Question:\n"
        "  - Read the question in the screenshot carefully (typically in Thai or English).\n"
        "  - If the question is about 'เวทีคอนเสิร์ตครั้งแรกของ BTS ในประเทศไทยคือเวทีคอนเสิร์ตใด' (What was BTS's first concert stage in Thailand?),\n"
        "    the correct answer is '7 สีคอนเสิร์ต' (7 See Concert).\n"
        "  - If the question is about other general or BTS facts, think logically and locate the correct option block.\n"
        "  - Click precisely on the button containing the correct answer.\n"
        "- Image / Lyric Sorting:\n"
        "  - Misplaced strips need to be sorted. Typically, it asks you to drag and drop pieces to assemble a complete picture or correct order.\n"
        "  - If it is a Thai Lyric Sorting CAPTCHA (เช่น เพลงชาติไทย - Thai National Anthem), the correct line sequence from top to bottom is:\n"
        "    1. 'ประเทศไทยรวมเลือดเนื้อชาติเชื้อไทย'\n"
        "    2. 'เป็นประชารัฐ ไผทของไทยทุกส่วน'\n"
        "    3. 'อยู่ดำรงคงไว้ได้ทั้งมวล ด้วยไทยล้วนหมาย'\n"
        "    4. 'รักสามัคคี ไทยนี้รักสงบ แต่ถึงรบไม่ขลาด'\n"
        "    5. 'เอกราชจะไม่ให้ใครข่มขี่'\n"
        "  - To sort these, plan sequence steps using action='drag_to' to move each strip to its correct relative position from top to bottom.\n"
        "  - You MUST include a final step in the 'steps' list to click the 'ยืนยัน / Verify' button below the list to submit it.\n"
        "- Puzzle slider: identify the slider thumb and missing piece gap. "
        "Set action='drag_slider', provide coordinates of the thumb and drag_offset_x. "
        "You MUST also include a second step in the 'steps' list to click the Verify button (usually named 'Verify' or similar) to submit it.\n"
        "- Trivia/color match: identify the correct answer and click it. "
        "For Color Match, you MUST first click the matching color, and then click the 'Verify' / 'btn-verify-color' button. "
        "Provide both actions in the 'steps' array (Step 1: click color, Step 2: click Verify button).\n"
        "- 'I'm not a robot' checkbox: click it.\n"
        "- Turnstile/reCAPTCHA iframe: click the checkbox inside it.\n"
    ),
    "generic": (
        "PHASE: UNKNOWN / GENERIC\n"
        "Analyze the entire screen and determine what needs to happen next to "
        "proceed toward purchasing tickets. Look for:\n"
        "- Any clickable button to proceed (Buy, Continue, Confirm, Next)\n"
        "- Unexpected popups or dialogs to dismiss\n"
        "- Terms & conditions acceptance\n"
        "- Error messages or blocking states\n"
        "- Custom CAPTCHAs or visual challenges\n"
        "- Dropdown menus for zone/showtime selection\n"
    ),
    "show_date_selection": "",
}

def build_seat_selection_prompt(
    seat_color_priorities: Optional[List[str]] = None,
    zone_name_priorities: Optional[List[str]] = None,
    scroll_info: Optional[Dict[str, Any]] = None,
) -> str:
    parts = [
        "PHASE: SEAT / ZONE SELECTION\n",
        "The bot passed the queue and is on the ticket purchase page. This is "
        "TIME-CRITICAL. Focus ONLY on:\n",
    ]

    if zone_name_priorities:
        priority_str = " > ".join(zone_name_priorities)
        parts.append(
            f"- Zone selection: if zones are shown, click the best AVAILABLE "
            f"zone in THIS priority order: {priority_str}.\n"
            f"  If the highest-priority zone is sold out or unavailable, "
            f"  try the next one in the list.\n"
        )
    else:
        parts.append(
            "- Zone selection: if zones are shown (VIP, GA, Standing), click the "
            "best available zone. Priority order: VIP > GA > Standing.\n"
        )

    if seat_color_priorities:
        color_str = ", ".join(seat_color_priorities)
        parts.append(
            f"- Seat map: identify AVAILABLE seats BY COLOR. The user wants "
            f"seats in this color priority order: [{color_str}].\n"
            f"  The FIRST color in the list is the most desired. If seats of "
            f"  that color are not available, try the next color.\n"
            f"  Sold/unavailable seats are typically: grey, dark grey, or "
            f"  crossed-out/striped.\n"
        )
    else:
        parts.append(
            "- Seat map: identify AVAILABLE seats (usually colored differently from "
            "sold/unavailable seats). Click the best available seat.\n"
            "Available seats are typically: green, blue, or white. "
            "Sold seats are: grey, red, or crossed out.\n"
        )

    parts.append(
        "- Ticket quantity dropdown or +/- buttons\n"
        "- 'เลือกที่นั่ง' / 'Select Seat' / similar buttons\n"
        "- Any popup blocking the seat map (terms, cookies) — dismiss it.\n"
    )

    if scroll_info:
        is_scrollable = scroll_info.get("is_scrollable", False)
        current_scroll_y = scroll_info.get("current_scroll_y", 0)
        page_height = scroll_info.get("page_height", 0)
        viewport_height = scroll_info.get("viewport_height", 0)
        if is_scrollable:
            remaining = page_height - current_scroll_y - viewport_height
            parts.append(
                f"\n⚠️ SCROLL AWARENESS: This page is scrollable. "
                f"Current scroll position: {current_scroll_y}px. "
                f"Page height: {page_height}px. "
                f"Remaining below: ~{max(0, remaining):.0f}px.\n"
                f"If you cannot find available seats or the target button in the "
                f"current viewport, set action='scroll_down' with "
                f"scroll_amount=300-500 to scroll down and look for more content. "
                f"Do NOT click blindly — scroll first if seats/buttons are not "
                f"visible in the screenshot.\n"
            )

    return "".join(parts)

def build_show_date_prompt(
    show_dates: Optional[List[str]] = None,
    show_date_preference: Optional[str] = None,
) -> str:
    parts = [
        "PHASE: SHOW DATE / ROUND SELECTION\n",
        "The bot is on the ticket purchase page and needs to select a SHOW DATE "
        "(รอบการแสดง) BEFORE selecting seats. This is TIME-CRITICAL.\n\n",
        "Focus ONLY on:\n",
        "- Radio buttons or clickable options for show dates/rounds\n",
        "- Labels containing dates like 'วันพฤหัสบดี', 'วันเสาร์', 'วันอาทิตย์' or "
        "'รอบที่ 1', 'รอบที่ 2', 'รอบที่ 3'\n",
    ]

    if show_dates:
        dates_str = ", ".join(show_dates)
        parts.append(
            f"\nAvailable show dates on this page: [{dates_str}]\n"
        )

    if show_date_preference:
        parts.append(
            f"\n⭐ PREFERRED DATE: The user wants date/round matching '{show_date_preference}'. "
            f"If it's available, you MUST select it. Otherwise, select the first available.\n"
        )

    return "".join(parts)
