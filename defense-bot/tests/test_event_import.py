import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gateway.event_import import analyze_event, parse_page, validate_source_url, MASTERZ_PATH

URL = "https://www.thaiticketmajor.com/concert/sample.html"


class EventImportTests(unittest.TestCase):
    def test_rejects_external_and_credential_urls(self):
        for url in ("http://www.thaiticketmajor.com/concert/sample.html",
                    "https://www.thaiticketmajor.com.evil.test/concert/sample.html",
                    "https://admin@www.thaiticketmajor.com/concert/sample.html",
                    "https://www.thaiticketmajor.com:444/concert/sample.html",
                    "https://127.0.0.1/concert/sample.html", "https://www.thaiticketmajor.com/"):
            with self.assertRaises(ValueError):
                validate_source_url(url)
        self.assertEqual(validate_source_url(URL + "?tracking=1#top"), URL)

    def test_structured_event_and_prices(self):
        event = {"@type": "MusicEvent", "name": "Sample concert",
                 "startDate": "2026-11-14T18:00:00+07:00", "location": {"name": "Stadium"},
                 "offers": [{"priceCurrency": "THB", "price": "7,900"},
                            {"priceCurrency": "USD", "price": 200}]}
        draft, evidence, prices = parse_page('<script type="application/ld+json">' + json.dumps(event) + '</script>', URL)
        self.assertEqual(draft["showDate"], "2026-11-14")
        self.assertEqual(draft["venue"], "Stadium")
        self.assertEqual(prices, [7900])
        self.assertNotIn("saleStartsAt", draft)
        self.assertNotIn("zones", draft)

    def test_pasted_thai_text_ignores_sale_date(self):
        result = asyncio.run(analyze_event(URL, "วันแสดง: 14 พฤศจิกายน 2569\nสถานที่แสดง: ธันเดอร์โดม\nราคาบัตร: 7,900 / 5,900 / 4,900 / 3,900 บาท\nเปิดขาย: 3 ตุลาคม 2569\nสูงสุด 4 ใบต่อบัญชี"))
        self.assertEqual(result["sourceMode"], "pasted")
        self.assertEqual(result["draft"]["showDate"], "2026-11-14")
        self.assertEqual(result["draft"]["maxTicketsPerAccount"], 4)
        self.assertEqual(result["ticketPrices"], [7900, 5900, 4900, 3900])
        self.assertNotIn("saleStartsAt", result["draft"])

    def test_multiple_events_are_not_selected_arbitrarily(self):
        html = '<script type="application/ld+json">' + json.dumps([{"@type": "Event", "name": "One"}, {"@type": "Event", "name": "Two"}]) + '</script>'
        self.assertNotIn("eventName", parse_page(html, URL)[0])

    def test_http_403_uses_labeled_reference_only_for_known_event(self):
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(403))
        with patch("gateway.event_import.httpx.AsyncClient", side_effect=lambda **kwargs: client_type(transport=transport, **kwargs)):
            result = asyncio.run(analyze_event("https://www.thaiticketmajor.com" + MASTERZ_PATH))
            self.assertEqual(result["sourceMode"], "reference")
            self.assertEqual(result["draft"]["showDate"], "2026-11-14")
            self.assertEqual(result["ticketPrices"], [])
            result = asyncio.run(analyze_event(URL))
            self.assertEqual(result["sourceMode"], "unavailable")
            self.assertNotIn("eventName", result["draft"])

    def test_redirect_is_not_followed(self):
        seen = []
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        client_type = httpx.AsyncClient
        with patch("gateway.event_import.httpx.AsyncClient", side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs)):
            result = asyncio.run(analyze_event(URL))
        self.assertEqual(seen, [URL])
        self.assertEqual(result["sourceMode"], "unavailable")


if __name__ == "__main__":
    unittest.main()
