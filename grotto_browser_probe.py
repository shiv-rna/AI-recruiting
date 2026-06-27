#!/usr/bin/env python3
"""Browser probe v8: dump the FULL bodies of the 200 calls most likely to carry
availability (/api/maps, resources), to find the signal the map paints.
Run: xvfb-run -a python3 ...
"""
from playwright.sync_api import sync_playwright
try:
    from playwright_stealth import stealth_sync
except Exception:
    stealth_sync = None

DATE = "2026-06-28"
URL = ("https://reservation.pc.gc.ca/create-booking/results"
    "?mapId=-2147483160&searchTabGroupId=3&bookingCategoryId=8"
    f"&startDate={DATE}&endDate={DATE}&nights=1&isReserving=true&partySize=1"
    "&equipmentId=-32768&subEquipmentId=-32768&equipmentCapacity=1"
    "&filterData=%7B%7D&resourceLocationId=-2147483637")

bodies = {}
def on_response(resp):
    u = resp.url
    if "/api/maps" in u or "/api/availability" in u or "/api/cart" == u.split("?")[0][-9:]:
        try: bodies.setdefault(u, (resp.status, resp.text()[:6000]))
        except Exception: pass

def is_waf(page):
    try: return "waf" in (page.title() or "").lower()
    except Exception: return False

with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        locale="en-CA", timezone_id="America/Toronto", viewport={"width":1366,"height":1400})
    page = ctx.new_page()
    page.on("response", on_response)
    if stealth_sync:
        try: stealth_sync(page)
        except Exception: pass
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    for _ in range(6):
        if not is_waf(page): break
        page.wait_for_timeout(6000)
        try: page.reload(wait_until="domcontentloaded", timeout=45000)
        except Exception: pass
    print(f"passed WAF: {not is_waf(page)}", flush=True)
    for label in ["I Consent","Accept","I Accept"]:
        try:
            el = page.get_by_text(label, exact=False)
            if el.count() > 0: el.first.click(timeout=3000); break
        except Exception: pass
    page.wait_for_timeout(18000)

for u,(s,bd) in bodies.items():
    tag = u.split("reservation.pc.gc.ca")[-1]
    print(f"\n===== {s} {tag[:120]}", flush=True)
    print(bd, flush=True)
