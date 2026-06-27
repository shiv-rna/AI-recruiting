#!/usr/bin/env python3
"""Browser probe v2: pass Azure WAF, accept the cookie consent, then capture
EVERY JSON network call so we find the real availability endpoint + response."""
import re
from playwright.sync_api import sync_playwright

DATE = "2026-06-28"
URL = (
    "https://reservation.pc.gc.ca/create-booking/results"
    "?mapId=-2147483160&searchTabGroupId=3&bookingCategoryId=8"
    f"&startDate={DATE}&endDate={DATE}&nights=1&isReserving=true&partySize=1"
    "&equipmentId=-32768&subEquipmentId=-32768&equipmentCapacity=1"
    "&filterData=%7B%7D&resourceLocationId=-2147483637"
)
STATIC = re.compile(r"\.(png|jpe?g|gif|svg|webp|woff2?|ttf|css|js|ico|map)(\?|$)", re.I)
captured = []

def on_response(resp):
    u = resp.url
    if STATIC.search(u):
        return
    ct = resp.headers.get("content-type", "")
    if "json" not in ct:
        return
    entry = {"status": resp.status, "method": resp.request.method, "url": u}
    try:
        entry["req_body"] = resp.request.post_data
    except Exception:
        entry["req_body"] = None
    try:
        entry["body"] = resp.text()[:3000]
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
    page.on("response", on_response)
    print(f"Navigating for {DATE} ...", flush=True)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    # Accept cookie consent so the SPA loads availability.
    for label in ["I Consent", "I consent", "Accept", "J'accepte", "I Accept"]:
        try:
            btn = page.get_by_text(label, exact=False)
            if btn.count() > 0:
                btn.first.click(timeout=3000)
                print(f"Clicked consent: {label!r}", flush=True)
                break
        except Exception:
            pass
    page.wait_for_timeout(12000)
    try:
        page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    # Try switching to List view to force availability rendering, then wait again.
    try:
        lst = page.get_by_text("List", exact=True)
        if lst.count() > 0:
            lst.first.click(timeout=3000)
            print("Clicked 'List' tab", flush=True)
            page.wait_for_timeout(6000)
    except Exception:
        pass
    print(f"Page title: {page.title()!r}", flush=True)
    browser.close()

print(f"\n==== captured {len(captured)} JSON calls ====", flush=True)
for i, e in enumerate(captured, 1):
    print(f"\n--- [{i}] {e['method']} {e['status']} {e['url']}", flush=True)
    if e.get("req_body"):
        print(f"    req_body: {e['req_body'][:600]}", flush=True)
    if e.get("body"):
        print(f"    resp: {e['body']}", flush=True)
