#!/usr/bin/env python3
"""Browser probe v5: pass WAF (headed+stealth), consent, let the SPA drive its
own cart+availability calls, and intercept EVERY availability response over a
long settle window — so we capture the successful (200) availability JSON shape.
Run: xvfb-run -a python3 grotto_browser_probe.py
"""
from playwright.sync_api import sync_playwright
try:
    from playwright_stealth import stealth_sync
except Exception:
    stealth_sync = None

DATE = "2026-06-28"
URL = (
    "https://reservation.pc.gc.ca/create-booking/results"
    "?mapId=-2147483160&searchTabGroupId=3&bookingCategoryId=8"
    f"&startDate={DATE}&endDate={DATE}&nights=1&isReserving=true&partySize=1"
    "&equipmentId=-32768&subEquipmentId=-32768&equipmentCapacity=1"
    "&filterData=%7B%7D&resourceLocationId=-2147483637"
)
avail = []

def on_response(resp):
    u = resp.url
    if "/api/availability" in u or "/api/resource" in u:
        e = {"status": resp.status, "url": u}
        try: e["body"] = resp.text()[:3500]
        except Exception as ex: e["body"] = f"<{ex}>"
        avail.append(e)

def is_waf(page):
    try: return "waf" in (page.title() or "").lower()
    except Exception: return False

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--no-sandbox",
        "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        locale="en-CA", timezone_id="America/Toronto",
        viewport={"width": 1366, "height": 1200})
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
    for label in ["I Consent", "Accept", "I Accept"]:
        try:
            b = page.get_by_text(label, exact=False)
            if b.count() > 0: b.first.click(timeout=3000); print(f"consent {label}", flush=True); break
        except Exception: pass
    # Let the SPA fully settle and fire its cart + availability calls; click the
    # Grotto location/marker to force slot-level availability if needed.
    page.wait_for_timeout(15000)
    for sel in ["text=Grotto Parking", "[aria-label*='Grotto' i]"]:
        try:
            el = page.locator(sel)
            if el.count() > 0: el.first.click(timeout=3000); print(f"clicked {sel}", flush=True); break
        except Exception: pass
    page.wait_for_timeout(12000)
    try: page.wait_for_load_state("networkidle", timeout=15000)
    except Exception: pass
    page.screenshot(path="grotto.png", full_page=True)

print(f"\n==== {len(avail)} availability/resource responses ====", flush=True)
for i, e in enumerate(avail, 1):
    print(f"\n--- [{i}] {e['status']} {e['url'][:160]}", flush=True)
    print(f"    {e.get('body','')}", flush=True)
