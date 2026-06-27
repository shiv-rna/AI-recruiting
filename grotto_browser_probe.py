#!/usr/bin/env python3
"""Browser probe v3: render the Grotto results, switch to List view, and extract
the availability signal from the DOM (+ screenshot), so the watcher can read
availability the way a human does — no fragile cart-handshake API replication."""
from playwright.sync_api import sync_playwright

DATE = "2026-06-28"
URL = (
    "https://reservation.pc.gc.ca/create-booking/results"
    "?mapId=-2147483160&searchTabGroupId=3&bookingCategoryId=8"
    f"&startDate={DATE}&endDate={DATE}&nights=1&isReserving=true&partySize=1"
    "&equipmentId=-32768&subEquipmentId=-32768&equipmentCapacity=1"
    "&filterData=%7B%7D&resourceLocationId=-2147483637"
)

def accept_cookies(page):
    for label in ["I Consent", "I consent", "Accept", "I Accept"]:
        try:
            b = page.get_by_text(label, exact=False)
            if b.count() > 0:
                b.first.click(timeout=3000); print(f"consent: {label}", flush=True); return
        except Exception:
            pass

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    ctx = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        locale="en-CA", viewport={"width": 1366, "height": 1200})
    page = ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    accept_cookies(page)
    page.wait_for_timeout(10000)

    # Switch to List view to get textual availability per resource/slot.
    for sel in ["button:has-text('List')", "text=List"]:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(timeout=3000); print(f"clicked List via {sel}", flush=True); break
        except Exception:
            pass
    page.wait_for_timeout(8000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    page.screenshot(path="grotto.png", full_page=True)
    print(f"title: {page.title()!r}", flush=True)

    # 1) Any element whose accessible name mentions availability state.
    print("\n==== availability-labelled elements ====", flush=True)
    for sel in ["[aria-label*='vailable' i]", "[title*='vailable' i]",
                "[class*='availab' i]", "[aria-label*='slot' i]"]:
        loc = page.locator(sel)
        n = min(loc.count(), 25)
        for i in range(n):
            try:
                al = loc.nth(i).get_attribute("aria-label") or loc.nth(i).get_attribute("title") or ""
                txt = (loc.nth(i).inner_text(timeout=500) or "").strip().replace("\n", " ")[:80]
                if al or txt:
                    print(f"  [{sel}] aria={al!r} text={txt!r}", flush=True)
            except Exception:
                pass

    # 2) Full visible text of the results region (fallback signal).
    print("\n==== results region text ====", flush=True)
    for sel in ["main", "[class*='results' i]", "body"]:
        try:
            t = page.locator(sel).first.inner_text(timeout=2000)
            if t and len(t) > 50:
                print(t[:2500], flush=True); break
        except Exception:
            pass
    browser.close()
