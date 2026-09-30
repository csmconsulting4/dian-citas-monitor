import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://agendamiento.dian.gov.co/"
NO_DISPONIBLE = (
    "No se encontraron especialidades relacionadas según los filtros seleccionados."
)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SCREENSHOT_PATH = Path("dian_posible_disponibilidad.png")


def send_telegram(message: str) -> None:
    endpoint = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": CHAT_ID, "text": message}
    ).encode("utf-8")

    with urllib.request.urlopen(endpoint, data=data, timeout=20) as response:
        response.read()


def click_visible_text(page, text: str) -> bool:
    matches = page.get_by_text(text, exact=True)
    for i in range(matches.count()):
        el = matches.nth(i)
        if el.is_visible():
            el.click()
            return True
    return False


def click_card_by_normalized_text(page, target: str) -> bool:
    result = page.evaluate(
        """
        (target) => {
          const norm = s => (s || '').replace(/\\s+/g, ' ').trim();

          const visible = el => {
            const r = el.getBoundingClientRect();
            const st = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   st.visibility !== 'hidden' &&
                   st.display !== 'none';
          };

          const matches = [...document.querySelectorAll('body *')]
            .filter(visible)
            .filter(el => norm(el.innerText) === target);

          if (!matches.length) return false;

          matches.sort((a, b) => {
            const ra = a.getBoundingClientRect();
            const rb = b.getBoundingClientRect();
            return (ra.width * ra.height) - (rb.width * rb.height);
          });

          matches[0].click();
          return true;
        }
        """,
        target,
    )
    return bool(result)


def main() -> int:
    print("DIAN monitor: starting one check")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})

        try:
            print("1. Opening DIAN")
            page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)

            print("2. Agendar cita")
            if not click_visible_text(page, "Agendar cita"):
                raise RuntimeError("Could not find a visible 'Agendar cita'")

            page.wait_for_timeout(1800)

            print("3. Persona Natural")
            if not click_card_by_normalized_text(page, "Persona Natural"):
                raise RuntimeError("Could not find 'Persona Natural'")

            page.wait_for_timeout(1000)

            print("4. Videoatención")
            if not click_card_by_normalized_text(page, "Videoatención"):
                raise RuntimeError("Could not find 'Videoatención'")

            page.wait_for_timeout(1000)

            print("5. Devoluciones")
            if not click_card_by_normalized_text(page, "Devoluciones."):
                raise RuntimeError("Could not find 'Devoluciones.'")

            page.wait_for_timeout(2500)

            body_text = page.locator("body").inner_text()

            if NO_DISPONIBLE in body_text:
                print("RESULT: no availability")
                return 0

            print("RESULT: possible availability")
            page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)

            send_telegram(
                "🚨 DIAN: posible disponibilidad\n\n"
                "Persona Natural > Videoatención > Devoluciones\n"
                "El mensaje de sin disponibilidad desapareció.\n"
                "Revisa el portal de la DIAN ahora."
            )
            print("Telegram alert sent")
            return 0

        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        finally:
            browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
