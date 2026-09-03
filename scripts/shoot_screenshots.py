"""Recapture the README's web pharmacy screenshots.

The five shots have to agree with each other, so they all come from one seeded
database and one run of this script.

Usage:
    python manage.py seed_pharmacy --reset
    python manage.py runserver 8000
    (cd web && python -m http.server 5500)
    pip install playwright        # drives the installed Edge; no browser download
    python scripts/shoot_screenshots.py docs/screenshots
"""
import sys
from playwright.sync_api import sync_playwright

WEB = "http://127.0.0.1:5500/index.html"
OUT = sys.argv[1]
SCALE = 2 / 3


def page(b, width, height, scale=SCALE):
    return b.new_page(viewport={"width": round(width / scale),
                                "height": round(height / scale)},
                      device_scale_factor=scale)


def login(pg, who="110001"):
    """Counter by default; the manager sees the admin-only claim actions."""
    pg.goto(WEB)
    pg.evaluate("localStorage.setItem('tenant_slug','demo')")
    pg.goto(WEB + "#/login")
    pg.wait_for_selector("#f input[name=identifier]")
    pg.fill("#f input[name=identifier]", who)
    pg.fill("#f input[name=password]", "devpass123")
    pg.click("#f button[type=submit]")
    pg.wait_for_function("() => !!localStorage.getItem('access')", timeout=20000)
    pg.wait_for_timeout(1500)


def route(pg, hash_, wait=3000):
    pg.evaluate(f"location.hash = '{hash_}'")
    pg.wait_for_timeout(wait)


with sync_playwright() as b_p:
    b = b_p.chromium.launch(channel="msedge")

    # Counter.
    pg = page(b, 1000, 747)
    login(pg)
    route(pg, "#/pharmacy")
    pg.screenshot(path=OUT + "/web-pharmacy-counter.png")
    pg.close()

    # Dispense — the card-less insured sale.
    pg = page(b, 1000, 610)
    login(pg)
    route(pg, "#/pharmacy/sell", 1000)
    pg.wait_for_selector("#add select[name=stock_item]", timeout=20000)
    opts = pg.eval_on_selector_all(
        "#add select[name=stock_item] option",
        "els => els.map(e => ({v: e.value, t: e.textContent.trim()}))")
    para = next(o for o in opts if "Paracetamol" in o["t"])
    pg.select_option("#add select[name=stock_item]", para["v"])
    pg.fill("#add input[name=quantity]", "10")
    pg.click("#add button")
    pg.wait_for_timeout(400)
    pg.fill("#checkout input[name=patient_search]", "Bola")
    pg.dispatch_event("#checkout input[name=patient_search]", "change")
    pg.wait_for_function(
        "() => document.querySelector('#checkout select[name=enrollment]').options.length > 1",
        timeout=20000)
    pg.select_option("#checkout select[name=payment_method]", "hmo")
    pg.wait_for_timeout(600)
    picked = pg.eval_on_selector(
        "#checkout select[name=enrollment]",
        "el => el.selectedOptions[0] && el.selectedOptions[0].textContent.trim()")
    assert picked and picked != "\u2014", "enrollment was not preselected"
    print("scheme preselected:", picked)
    pg.evaluate("document.querySelector('#checkout').scrollIntoView({block:'end'})")
    pg.wait_for_timeout(400)
    pg.screenshot(path=OUT + "/web-pharmacy-dispense.png")
    pg.close()

    # The part-delivered order — found, not hardcoded: references change with
    # every reseed.
    pg = page(b, 1000, 787)
    login(pg)
    order_id = pg.evaluate(
        "Api.list('/api/pharmacy/purchase-orders/', {status: 'partial'})"
        ".then(r => r.rows[0].id)")
    route(pg, f"#/r/pharmacy-orders/{order_id}")
    pg.screenshot(path=OUT + "/web-pharmacy-order.png")
    pg.close()

    # The part-paid approved claim, as the manager: Record payment is
    # admin-only, and the picture is about the one action the state allows.
    pg = page(b, 1000, 520)
    login(pg, "08031110002")
    # A part-paid claim if there is one — claimed, approved and paid differ on
    # it — otherwise any decided claim will do.
    claim_id = pg.evaluate(
        "Api.list('/api/pharmacy/claims/').then(r => {"
        "  const paid = r.rows.filter(c => Number(c.amount_paid) > 0);"
        "  const part = paid.find(c => Number(c.amount_paid) < Number(c.amount));"
        "  return (part || paid[0] || r.rows[0]).id; })")
    route(pg, f"#/r/pharmacy-claims/{claim_id}")
    pg.screenshot(path=OUT + "/web-pharmacy-claim.png")

    # The receipt of the insured sale, fetched with the JWT the way the app's
    # print button does.
    sale_id = pg.evaluate(
        "Api.list('/api/pharmacy/sales/', {payment_method: 'hmo'})"
        ".then(r => r.rows[0].id)")
    html = pg.evaluate(f"Api.text('/api/pharmacy/sales/{sale_id}/receipt/')")
    pg.close()

    pg = b.new_page(viewport={"width": 620, "height": 469})
    pg.set_content(html)
    pg.wait_for_timeout(500)
    pg.screenshot(path=OUT + "/web-pharmacy-receipt.png")
    pg.close()
    b.close()
print("captured 5 web screenshots")
