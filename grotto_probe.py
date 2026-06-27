#!/usr/bin/env python3
"""Throwaway probe: try several reservation.pc.gc.ca availability endpoint/param
combos and report status + a slice of each body, so we can identify the correct
request shape. Deleted once the real call is confirmed."""
import json, urllib.parse, urllib.request

BASE = "https://reservation.pc.gc.ca"
MAP = -2147483160
RES = -2147483637
DATE = "2026-06-28"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

common = {
    "mapId": MAP, "searchTabGroupId": 3, "bookingCategoryId": 8,
    "startDate": DATE, "endDate": DATE, "nights": 1, "isReserving": "true",
    "partySize": 1, "equipmentId": -32768, "subEquipmentId": -32768,
    "equipmentCapacity": 1, "filterData": "{}",
    "flexibleSearch": "[false,false,null,1]",
}

candidates = [
    ("GET", "/api/availability/map", {**common, "getDailyAvailability": "false"}),
    ("GET", "/api/availability/map", {**common, "resourceLocationId": RES, "getDailyAvailability": "true"}),
    ("GET", "/api/availability/resourcedailyavailability",
        {**common, "resourceLocationId": RES, "getDailyAvailability": "true"}),
    ("GET", "/api/availability/resourcelocationdailyavailability",
        {**common, "resourceLocationId": RES, "getDailyAvailability": "true"}),
    ("GET", f"/api/maps/{MAP}", {}),
    ("GET", "/api/resourcelocation/details", {"resourceLocationId": RES}),
    ("GET", "/api/search/places", {**common}),
]

def hit(method, path, params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Referer": BASE + "/create-booking/results",
        "X-Requested-With": "XMLHttpRequest"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERR", f"{type(e).__name__}: {e}"

for i, (m, p, params) in enumerate(candidates, 1):
    status, body = hit(m, p, params)
    print(f"\n=== [{i}] {m} {p}  ->  HTTP {status} ===", flush=True)
    print(body[:1200], flush=True)
