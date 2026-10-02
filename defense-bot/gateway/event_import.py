"""Read public event details into a draft; never change booking or lab state."""

import json
import re
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

import httpx

MAX_BYTES = 2_000_000
MASTERZ_PATH = "/concert/2026-k-pop-masterz-special-live-in-bangkok-bambam-mark-jayb.html"
REFERENCE_URL = "https://event.thaiticketmajor.com/index.php?la=en"


def validate_source_url(value):
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError("กรุณาใส่ลิงก์หน้าอีเวนต์ ThaiTicketMajor")
    try:
        parsed = urlsplit(value.strip())
        valid = (parsed.scheme == "https" and parsed.hostname in
                 {"www.thaiticketmajor.com", "thaiticketmajor.com", "event.thaiticketmajor.com"}
                 and not parsed.username and not parsed.password and parsed.port in {None, 443}
                 and re.fullmatch(r"/(concert|performance|sport|exhibition)/[a-zA-Z0-9_-]+\.html", parsed.path))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("รองรับเฉพาะลิงก์หน้าอีเวนต์ HTTPS ของ ThaiTicketMajor")
    return urlunsplit(("https", parsed.hostname, parsed.path, "", ""))


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.blocks = []
        self.script = None
        self.hidden = 0
        self.title = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.script = [] if attrs.get("type", "").lower() == "application/ld+json" else None
            self.hidden += 1
        elif tag == "style":
            self.hidden += 1
        elif tag == "meta" and attrs.get("property") == "og:title":
            self.title = attrs.get("content", "")
        elif tag in {"br", "p", "div", "li", "tr", "h1", "h2"}:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag == "script":
            if self.script is not None:
                try:
                    self.blocks.append(json.loads("".join(self.script)))
                except (ValueError, RecursionError):
                    pass
            self.script = None
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "tr", "h1", "h2"}:
            self.text.append("\n")

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if not self.hidden:
            self.text.append(data)


def event_nodes(value, depth=0):
    if depth > 15:
        return
    if isinstance(value, list):
        for node in value:
            yield from event_nodes(node, depth + 1)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if isinstance(types, list) and any(t in {"Event", "MusicEvent", "TheaterEvent", "SportsEvent"} for t in types):
            yield value
        if "@graph" in value:
            yield from event_nodes(value["@graph"], depth + 1)


def parse_page(html, url):
    parser = PageParser()
    parser.feed(html)
    draft = {"officialEventUrl": url}
    evidence = {}
    prices = set()
    nodes = [node for block in parser.blocks for node in event_nodes(block)]
    # Multiple events may be recommendations, so do not guess which one to import.
    if len(nodes) == 1:
        node = nodes[0]
        if isinstance(node.get("name"), str) and 1 <= len(node["name"].strip()) <= 120:
            draft["eventName"] = node["name"].strip()
            evidence["eventName"] = "JSON-LD Event.name"
        location = node.get("location")
        if isinstance(location, dict) and isinstance(location.get("name"), str):
            draft["venue"] = location["name"].strip()[:500]
            evidence["venue"] = "JSON-LD Event.location.name"
        start = node.get("startDate")
        if isinstance(start, str):
            try:
                draft["showDate"] = date.fromisoformat(start[:10]).isoformat()
                evidence["showDate"] = "JSON-LD Event.startDate"
            except ValueError:
                pass
        offers = node.get("offers", [])
        if isinstance(offers, dict):
            offers = [offers]
        if isinstance(offers, list):
            for offer in offers:
                if not isinstance(offer, dict) or offer.get("priceCurrency") != "THB":
                    continue
                for key in ("price", "lowPrice", "highPrice"):
                    try:
                        price = float(str(offer.get(key, "")).replace(",", ""))
                        if 0 < price <= 1_000_000 and price.is_integer():
                            prices.add(int(price))
                    except ValueError:
                        pass
    if "eventName" not in draft and 1 <= len(parser.title.strip()) <= 120:
        draft["eventName"] = parser.title.strip()
        evidence["eventName"] = "og:title (ตรวจสอบชื่อก่อนบันทึก)"
    text = "\n".join(" ".join(line.split()) for line in "".join(parser.text).splitlines() if line.strip())
    for field, label in (("venue", r"(?:สถานที่แสดง|สถานที่จัดงาน|Venue)"),):
        match = re.search(label + r"\s*[:：]?\s*([^\n]{1,150})", text, re.I)
        if field not in draft and match:
            draft[field] = match[1].strip()
            evidence[field] = match[0]
    match = re.search(r"(?:ราคาบัตร|Ticket prices?)\s*[:：]?\s*([\d, /]+)\s*(?:บาท|THB)", text, re.I)
    if match:
        prices.update(int(p.replace(",", "")) for p in re.findall(r"\d[\d,]*", match[1]) if 0 < int(p.replace(",", "")) <= 1_000_000)
    if "showDate" not in draft:
        match = re.search(r"(?:วันแสดง|วันที่แสดง|Show date)\s*[:：]?\s*([^\n]{1,100})", text, re.I)
        if match:
            value = match[1]
            iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", value)
            thai = re.search(r"(\d{1,2})\s+(มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม)\s+(\d{4})", value)
            try:
                if iso:
                    draft["showDate"] = date.fromisoformat(iso[1]).isoformat()
                elif thai:
                    months = "มกราคม กุมภาพันธ์ มีนาคม เมษายน พฤษภาคม มิถุนายน กรกฎาคม สิงหาคม กันยายน ตุลาคม พฤศจิกายน ธันวาคม".split()
                    year = int(thai[3])
                    draft["showDate"] = date(year - 543 if year > 2400 else year, months.index(thai[2]) + 1, int(thai[1])).isoformat()
                if "showDate" in draft:
                    evidence["showDate"] = match[0]
            except ValueError:
                pass
    match = re.search(r"(?:ไม่เกิน|สูงสุด|จำกัด)\s*(\d{1,2})\s*(?:ใบ|บัตร)\s*(?:ต่อ|/)\s*(?:บัญชี|คน|ท่าน)", text)
    if match and 1 <= int(match[1]) <= 10:
        draft["maxTicketsPerAccount"] = int(match[1])
        evidence["maxTicketsPerAccount"] = match[0]
    return draft, evidence, sorted(prices, reverse=True)


async def analyze_event(url, pasted_text=""):
    url = validate_source_url(url)
    warnings = []
    mode = "live"
    html = ""
    if pasted_text:
        mode = "pasted"
        html = pasted_text
        warnings.append("วิเคราะห์ข้อความที่คุณวาง กรุณาเทียบกับหน้าอีเวนต์จริง")
    else:
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=False, trust_env=False) as client:
                async with client.stream("GET", url, headers={"User-Agent": "TicketingLab-EventDetails/1.0", "Accept": "text/html"}) as response:
                    response.raise_for_status()
                    if "text/html" not in response.headers.get("content-type", "").lower():
                        raise ValueError("หน้าเว็บไม่ได้ส่งข้อมูล HTML")
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            raise ValueError("หน้าเว็บมีขนาดเกินขีดจำกัด")
                    html = content.decode("utf-8", errors="replace")
        except (httpx.HTTPError, ValueError) as exc:
            mode = "unavailable"
            status = getattr(getattr(exc, "response", None), "status_code", None)
            warnings.append(f"อ่านหน้าเว็บไม่ได้{(' (HTTP ' + str(status) + ')') if status else ''} ให้คัดลอกข้อความรายละเอียดมาวางแทน")
    draft, evidence, prices = parse_page(html, url)
    if mode == "unavailable" and urlsplit(url).path == MASTERZ_PATH:
        mode = "reference"
        draft.update(eventName="2026 K-POP MASTERZ SPECIAL LIVE IN BANGKOK BAMBAM × JAY B × MARK",
                     venue="ธันเดอร์โดม สเตเดียม", showDate="2026-11-14")
        evidence.update({field: REFERENCE_URL for field in ("eventName", "venue", "showDate")})
        warnings.append("ใช้ข้อมูลอ้างอิงที่ตรวจสอบไว้เมื่อ 2 ต.ค. 2569 ไม่ใช่การอ่านหน้าเว็บล่าสุด")
    missing = [field for field in ("eventName", "venue", "showDate", "maxTicketsPerAccount") if field not in draft]
    warnings.append("ไม่สามารถอนุมานผังโซน จำนวนที่นั่ง สถานะขาย และระบบป้องกันจากรายละเอียดงานได้ คงค่าจำลองเดิมไว้")
    return {"draft": draft, "evidence": evidence, "ticketPrices": prices,
            "missingFields": missing, "warnings": warnings, "sourceMode": mode}
