#!/usr/bin/env python3
"""Browser probe: load the Grotto booking results page in real Chromium (passes
the Azure WAF JS challenge) and capture every reservation.pc.gc.ca /api/ request
+ response, so we learn the EXACT availability call (URL, method, body, shape)."""
import json
from playwright.sync_api import sync_playwright

DATE = "2026-06-28"
URL = (
    "https://reservation.pc.gc.ca/create-booking/results"
    "?mapId=-2147483160&searchTabGroupId=3&bookingCategoryId=8"
    f"&startDate={DATE}&endDate={DATE}&nights=1&isReserving=true&partySize=1"
    "&equipmentId=-32768&subEquipmentId=-32768&equipmentCapacity=1"
    "&filterData=%7B%7D&resourceLocationId=-2147483637"
)

captured = []

def on_response(resp):
    u = resp.url
    if "reservation.pc.gc.ca/api/" in u:
        entry = {"status": resp.status, "method": resp.request.method, "url": u}
        try:
            entry["req_body"] = resp.request.post_data
        except Exception:
            entry["req_body"] = None
        ct = resp.headers.get("content-type", "")
        if "json" in ct or "text" in ct:
            try:
                entry["body"] = resp.text()[:2500]
            except Exception as e:
                entry["body"] = f"<{e}>"
        captured.append(entry)

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        locale="en-CA", viewport={"width": 1366, "height": 900})
    page = ctx.new_page()
    print(f"Navigating to results page for {DATE} ...", flush=True)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    # Give the SPA + WAF challenge + availability XHRs time to complete.
    page.wait_for_timeout(15000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    print(f"Page title: {page.title()!r}", flush=True)
    # Dump any visible availability-ish text as a fallback signal.
    body_text = page.inner_text("body")[:1500]
    print("---- VISIBLE TEXT (first 1500) ----", flush=True)
    print(body_text, flush=True)
    browser.close()

print(f"\n==== captured {len(captured)} /api/ calls ====", flush=True)
for i, e in enumerate(captured, 1):
    print(f"\n--- [{i}] {e['method']} {e['status']} {e['url']}", flush=True)
    if e.get("req_body"):
        print(f"    req_body: {e['req_body'][:500]}", flush=True)
    if e.get("body"):
        print(f"    resp: {e['body']}", flush=True)
