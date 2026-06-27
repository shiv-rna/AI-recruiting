#!/usr/bin/env python3
"""Browser probe v4: beat the intermittent Azure WAF JS-challenge with a HEADED
browser (xvfb) + stealth + challenge-retry, then read the Grotto availability
from the rendered List view. Run via: xvfb-run -a python3 grotto_browser_probe.py
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

def is_waf(page):
    try:
        t = (page.title() or "")
    except Exception:
        t = ""
    return "azure waf" in t.lower() or "waf" == t.strip().lower()

def pass_waf(page, tries=6):
    for i in range(tries):
        if not is_waf(page):
            return True
        print(f"  WAF challenge present (attempt {i+1}); waiting…", flush=True)
        page.wait_for_timeout(6000)
        if is_waf(page):
            try:
                page.reload(wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
    return not is_waf(page)

def accept_cookies(page):
    for label in ["I Consent", "I consent", "Accept", "I Accept"]:
        try:
            b = page.get_by_text(label, exact=False)
            if b.count() > 0:
                b.first.click(timeout=3000); print(f"consent: {label}", flush=True); return
        except Exception:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--no-sandbox",
        "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        locale="en-CA", timezone_id="America/Toronto",
        viewport={"width": 1366, "height": 1200})
    page = ctx.new_page()
    if stealth_sync:
        try: stealth_sync(page); print("stealth applied", flush=True)
        except Exception as e: print(f"stealth err {e}", flush=True)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    ok = pass_waf(page)
    print(f"passed WAF: {ok}; title now: {page.title()!r}", flush=True)
    accept_cookies(page)
    page.wait_for_timeout(10000)
    for sel in ["button:has-text('List')", "text=List"]:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(timeout=3000); print(f"clicked List", flush=True); break
        except Exception:
            pass
    page.wait_for_timeout(9000)
    try: page.wait_for_load_state("networkidle", timeout=15000)
    except Exception: pass

    page.screenshot(path="grotto.png", full_page=True)
    print(f"final title: {page.title()!r}", flush=True)

    print("\n==== availability-labelled elements ====", flush=True)
    for sel in ["[aria-label*='vailable' i]", "[class*='availab' i]",
                "[aria-label*='slot' i]", "[class*='legend' i] ~ * [aria-label]"]:
        loc = page.locator(sel)
        for i in range(min(loc.count(), 30)):
            try:
                al = loc.nth(i).get_attribute("aria-label") or ""
                txt = (loc.nth(i).inner_text(timeout=400) or "").strip().replace("\n"," ")[:70]
                if al or txt:
                    print(f"  {sel} | aria={al!r} text={txt!r}", flush=True)
            except Exception:
                pass

    print("\n==== results region text ====", flush=True)
    for sel in ["main", "[class*='results' i]", "body"]:
        try:
            t = page.locator(sel).first.inner_text(timeout=2000)
            if t and len(t) > 50:
                print(t[:2500], flush=True); break
        except Exception:
            pass
    browser.close()
