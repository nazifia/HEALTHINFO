"""Recapture the README's Flutter client screenshots.

The app is driven as a web build, which is how these shots have always been
framed: a browser at 1000px, not a phone. Its UI is a canvas, so there is
nothing to click by selector — the tokens are written straight into the
storage `shared_preferences` uses, and the nav rail is clicked by coordinate.

Usage:
    python manage.py seed_pharmacy --reset
    python manage.py runserver 8000
    cd mobile && flutter build web
    (cd mobile/build/web && python -m http.server 5501)
    pip install playwright        # drives the installed Edge; no browser download
    python scripts/shoot_mobile_screenshots.py docs/screenshots
"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

APP = "http://localhost:5501/"
API = "http://localhost:8000"
TENANT = "demo"
PASSWORD = "devpass123"
COUNTER = "110001"        # the pharmacist's short login
MANAGER = "08031110002"   # tenant_admin: sees the claim decisions
OUT = sys.argv[1]

# Shots are taken at 1.5x and scaled down, which is what fits a whole screen
# into 1000px and still reads.
SCALE = 2 / 3

# Nav rail positions, in the coordinates of the finished 1000px-wide image.
# The manager's rail carries one extra entry, so its rows sit lower.
NAV_ORDERS = (79, 309)
NAV_CLAIMS_MANAGER = (69, 271)
ORDER_CARD = (403, 388)   # the one seeded purchase order, in the list


def token(identifier):
    """A JWT pair, fetched the way the app's own login does."""
    request = urllib.request.Request(
        f"{API}/api/auth/token/",
        data=json.dumps({"phone": identifier, "password": PASSWORD}).encode(),
        headers={"Content-Type": "application/json", "X-Tenant-ID": TENANT},
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def page(browser, height):
    return browser.new_page(
        viewport={"width": round(1000 / SCALE), "height": round(height / SCALE)},
        device_scale_factor=SCALE,
    )


def boot(pg, tokens):
    """Start the app already signed in — its login field takes no synthetic
    typing, and the tokens are all the app reads back on startup."""
    pg.goto(APP)
    pg.wait_for_timeout(2500)
    pg.evaluate(
        """([access, refresh, tenant]) => {
            localStorage.setItem('flutter.access', JSON.stringify(access));
            localStorage.setItem('flutter.refresh', JSON.stringify(refresh));
            localStorage.setItem('flutter.tenant_slug', JSON.stringify(tenant));
        }""",
        [tokens["access"], tokens["refresh"], TENANT],
    )
    pg.reload()
    pg.wait_for_timeout(14000)


def tap(pg, point, wait=5000):
    x, y = point
    pg.mouse.click(x / SCALE, y / SCALE)
    pg.wait_for_timeout(wait)


counter, manager = token(COUNTER), token(MANAGER)

with sync_playwright() as driver:
    browser = driver.chromium.launch(channel="msedge", headless=False)

    # The counter's own screen is where the pharmacist lands.
    pg = page(browser, 969)
    boot(pg, counter)
    pg.screenshot(path=OUT + "/pharmacy-counter.png")
    pg.close()

    # Orders, then the part-delivered one in its sheet.
    pg = page(browser, 945)
    boot(pg, counter)
    tap(pg, NAV_ORDERS)
    pg.screenshot(path=OUT + "/pharmacy-orders.png")
    tap(pg, ORDER_CARD)
    pg.screenshot(path=OUT + "/pharmacy-order.png")
    pg.close()

    # Claims as the manager: approving and paying are admin-only, and the
    # picture is about each claim offering the one action its state allows.
    pg = page(browser, 727)
    boot(pg, manager)
    tap(pg, NAV_CLAIMS_MANAGER, wait=6000)
    pg.screenshot(path=OUT + "/pharmacy-claims.png")
    pg.close()
    browser.close()

print("captured 4 mobile screenshots")
