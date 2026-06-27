#!/usr/bin/env python3
"""
grotto_watch.py — watch Parks Canada for a Grotto / Cyprus Lake parking
cancellation and alert when one frees up.

Runs in GitHub Actions (cloud, open internet) because the host that wrote it is
firewalled off reservation.pc.gc.ca. Config comes from env vars (see CONFIG);
notifications go to ntfy.sh (phone push) and/or a GitHub issue.

Modes:
  --once -v   single verbose poll; prints the RAW response (use to verify the API)
  (default)   loop until STOP_AT, alerting on availability
"""

import argparse
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

# ─────────────────────────── CONFIG (env-overridable) ───────────────────────────
def envi(name, default):
    v = os.environ.get(name)
    return int(v) if v not in (None, "") else default

def envs(name, default):
    v = os.environ.get(name)
    return v if v not in (None, "") else default

MAP_ID               = envi("GROTTO_MAP_ID", -2147483160)
RESOURCE_LOCATION_ID = envi("GROTTO_RESLOC_ID", -2147483637)  # Grotto/Cyprus Lake parking
BOOKING_CATEGORY_ID  = envi("GROTTO_BOOKING_CAT", 8)          # day-use / parking
TARGET_DATE          = envs("GROTTO_DATE", "2026-06-28")
PARTY_SIZE           = envi("GROTTO_PARTY", 1)

# Stop time as UTC ISO (10am America/Toronto on 2026-06-28 == 14:00 UTC).
STOP_AT_UTC = envs("GROTTO_STOP_UTC", "2026-06-28T14:00:00")

POLL_MIN_SECONDS = envi("GROTTO_POLL_MIN", 60)
POLL_MAX_SECONDS = envi("GROTTO_POLL_MAX", 120)

# ntfy phone push: install the ntfy app, subscribe to this exact topic.
NTFY_SERVER = envs("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC  = envs("NTFY_TOPIC", "")        # set to enable phone push

# GitHub issue fallback (auto in Actions): needs GITHUB_TOKEN + GITHUB_REPOSITORY.
GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_REPO  = os.environ.get("GITHUB_REPOSITORY", "")   # "owner/name"
GH_MENTION = envs("GROTTO_MENTION", "")              # username to @-mention, no '@'

AVAIL_URL = envs("GROTTO_AVAIL_URL",
                 "https://reservation.pc.gc.ca/api/availability/resourcedailyavailability")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# ──────────────────────────────────────────────────────────────────────────────


def log(msg):
    print(f"[{dt.datetime.utcnow():%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def stop_at():
    return dt.datetime.fromisoformat(STOP_AT_UTC)


def notify_ntfy(title, message, priority="urgent"):
    if not NTFY_TOPIC:
        log("(ntfy topic not set — skipping phone push)")
        return
    try:
        req = urllib.request.Request(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=message.encode(),
            headers={"Title": title, "Priority": priority,
                     "Tags": "rotating_light,car", "User-Agent": UA},
            method="POST")
        urllib.request.urlopen(req, timeout=20).read()
        log(f"ntfy push sent → '{NTFY_TOPIC}'")
    except Exception as e:
        log(f"!! ntfy push failed: {e}")


def notify_github_issue(title, message):
    if not (GH_TOKEN and GH_REPO):
        return
    try:
        body = message
        if GH_MENTION:
            body = f"@{GH_MENTION} {body}"
        payload = json.dumps({"title": title, "body": body}).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{GH_REPO}/issues",
            data=payload,
            headers={"Authorization": f"Bearer {GH_TOKEN}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "grotto-watch", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            num = json.loads(r.read()).get("number")
        log(f"GitHub issue #{num} opened")
    except Exception as e:
        log(f"!! GitHub issue failed: {e}")


def notify(title, message, priority="urgent"):
    notify_ntfy(title, message, priority)
    notify_github_issue(title, message)


def fetch_availability(verbose=False):
    params = {
        "resourceLocationId": RESOURCE_LOCATION_ID, "mapId": MAP_ID,
        "bookingCategoryId": BOOKING_CATEGORY_ID, "startDate": TARGET_DATE,
        "endDate": TARGET_DATE, "getDailyAvailability": "true", "partySize": PARTY_SIZE,
    }
    url = AVAIL_URL + "?" + urllib.parse.urlencode(params)
    if verbose:
        log(f"GET {url}")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Referer": "https://reservation.pc.gc.ca/create-booking/results"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "replace")
    if verbose:
        log(f"HTTP 200, {len(raw)} bytes. RAW RESPONSE BELOW:")
        print("----8<---- RAW ----8<----", flush=True)
        print(raw[:4000], flush=True)
        print("----8<---- END ----8<----", flush=True)
    return parse_availability(json.loads(raw))


def parse_availability(data):
    found = []
    def scan(node, ctx=""):
        if isinstance(node, dict):
            avail = node.get("availability") or node.get("status")
            remaining = node.get("remainingQuota", node.get("remaining",
                         node.get("availableQuantity", node.get("quantity"))))
            date = node.get("date") or node.get("startDate") or ctx
            is_open = (
                (isinstance(avail, str) and avail.lower() in ("available", "a", "open"))
                or (isinstance(remaining, (int, float)) and remaining > 0)
                or node.get("isAvailable") is True)
            if is_open and (not date or str(date).startswith(TARGET_DATE)):
                found.append({"date": str(date) or TARGET_DATE, "remaining": remaining,
                              "label": node.get("name") or node.get("resourceName") or ctx})
            for k, v in node.items():
                scan(v, ctx=str(node.get("date", node.get("name", ctx))))
        elif isinstance(node, list):
            for item in node:
                scan(item, ctx)
    scan(data)
    seen, uniq = set(), []
    for f in found:
        key = (f["date"], str(f["label"]))
        if key not in seen:
            seen.add(key); uniq.append(f)
    return uniq


def run_loop(once, verbose):
    log(f"Watch Grotto parking {TARGET_DATE}; stop at {STOP_AT_UTC}Z. "
        f"ntfy='{NTFY_TOPIC or 'off'}' gh_issue={'on' if GH_TOKEN else 'off'}")
    polls = 0
    while True:
        if not once and dt.datetime.utcnow() >= stop_at():
            log("Reached cutoff — stopping.")
            return 0
        polls += 1
        try:
            slots = fetch_availability(verbose=verbose)
            if slots:
                summary = "; ".join(
                    f"{s['label'] or 'parking'} ({s['date']}"
                    + (f", {s['remaining']} left" if s['remaining'] not in (None, "") else "")
                    + ")" for s in slots[:5])
                log(f"AVAILABILITY FOUND: {summary}")
                notify("Grotto parking OPEN!",
                       f"Cancellation for {TARGET_DATE}: {summary}. "
                       f"Book now: https://reservation.pc.gc.ca/create-booking/results")
                if once:
                    return 0
                time.sleep(180)   # re-check soon but don't spam
                continue
            log(f"poll #{polls}: no parking yet")
        except Exception as e:
            ec = getattr(e, "code", "")
            log(f"poll #{polls}: {type(e).__name__} {ec}: {e}")
            if verbose and hasattr(e, "read"):
                try:
                    print(e.read().decode("utf-8", "replace")[:1000], flush=True)
                except Exception:
                    pass
        if once:
            return 0
        time.sleep(random.uniform(POLL_MIN_SECONDS, POLL_MAX_SECONDS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--test-notify", action="store_true")
    a = ap.parse_args()
    if a.test_notify:
        notify("Grotto watch — test", "Push works ✅", priority="default")
        return 0
    return run_loop(a.once, a.verbose)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
