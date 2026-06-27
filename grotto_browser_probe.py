#!/usr/bin/env python3
"""Browser probe v7: from inside the authenticated page (cart + WAF cookies),
replay the SPA's exact availability request with param variants to find one that
returns real availability JSON. Run: xvfb-run -a python3 ...
"""
import re
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

spa_avail_url = {"u": None}
def on_request(req):
    if "/api/availability/map" in req.url and spa_avail_url["u"] is None:
        spa_avail_url["u"] = req.url

def is_waf(page):
    try: return "waf" in (page.title() or "").lower()
    except Exception: return False

with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        locale="en-CA", timezone_id="America/Toronto", viewport={"width":1366,"height":1400})
    page = ctx.new_page()
    page.on("request", on_request)
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
    page.wait_for_timeout(16000)

    base = spa_avail_url["u"]
    print(f"SPA availability URL captured: {base}", flush=True)
    candidates = []
    if base:
        candidates.append(("spa-exact", base))
        candidates.append(("dailyTrue", re.sub(r"getDailyAvailability=\w+", "getDailyAvailability=true", base)))
        candidates.append(("resourcedaily", base.replace("/availability/map", "/availability/resourcedailyavailability")))
        candidates.append(("resourcedailyTrue", re.sub(r"getDailyAvailability=\w+","getDailyAvailability=true",
                            base.replace("/availability/map","/availability/resourcedailyavailability"))))

    js = """async (url) => {
        try {
            const r = await fetch(url, {headers: {'Accept':'application/json'}, credentials:'include'});
            const t = await r.text();
            return {status: r.status, body: t.slice(0, 2500)};
        } catch(e) { return {status:'ERR', body: String(e)}; }
    }"""
    for name, u in candidates:
        res = page.evaluate(js, u)
        print(f"\n=== {name} -> HTTP {res['status']}", flush=True)
        print(f"    URL: {u[:200]}", flush=True)
        print(f"    BODY: {res['body']}", flush=True)
    b.close()
