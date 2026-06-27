#!/usr/bin/env python3
"""Browser probe v6: render Grotto parking results, capture the live availability
call the SPA makes for the slots, AND dump the slot-row DOM so we can target the
'Sold Out' / 'Reserve' signal precisely. Run: xvfb-run -a python3 ...
"""
import re, json
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
calls = []
def on_response(resp):
    u = resp.url
    if "/api/" in u and any(k in u for k in ["availab", "resource", "booking", "cart", "slot", "permit"]):
        e = {"s": resp.status, "u": u}
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            try: e["b"] = resp.text()[:1500]
            except Exception: e["b"] = ""
        calls.append(e)

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
    page.wait_for_timeout(16000)
    try: page.wait_for_load_state("networkidle", timeout=15000)
    except Exception: pass
    page.screenshot(path="grotto.png", full_page=True)

    # Dump DOM of slot rows: any element whose text mentions a 4-hour time slot.
    print("\n==== slot-row elements (time-slot text) ====", flush=True)
    rx = re.compile(r"\d{1,2}:\d{2}\s*[ap]m", re.I)
    try:
        handles = page.query_selector_all("body *")
    except Exception:
        handles = []
    seen = set(); shown = 0
    for h in handles:
        if shown >= 14: break
        try:
            txt = (h.inner_text() or "").strip()
        except Exception:
            continue
        if not txt or not rx.search(txt) or len(txt) > 240:
            continue
        key = txt[:60]
        if key in seen: continue
        seen.add(key)
        try: html = h.evaluate("e => e.outerHTML")[:500]
        except Exception: html = ""
        print(f"  TEXT: {txt!r}", flush=True)
        print(f"  HTML: {html!r}\n", flush=True)
        shown += 1

    # Words that signal availability state anywhere on the page.
    print("==== availability words present ====", flush=True)
    body = page.locator("body").inner_text(timeout=3000)
    for w in ["Sold Out","Soldout","Unavailable","Available","Reserve","Add to","Full","No availability","Not Available"]:
        c = len(re.findall(re.escape(w), body, re.I))
        if c: print(f"  {w!r}: {c}", flush=True)
    b.close()

print(f"\n==== {len(calls)} api calls ====", flush=True)
for i,e in enumerate(calls,1):
    tag = e['u'].split('reservation.pc.gc.ca')[-1][:90]
    print(f"[{i}] {e['s']} {tag}", flush=True)
    if e.get("b") and ("availab" in e['u'] or "slot" in e['u'] or "permit" in e['u']):
        print(f"     {e['b']}", flush=True)
