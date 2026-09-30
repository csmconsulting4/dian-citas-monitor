import os
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = "https://agendamiento.dian.gov.co/"
NO_DISPONIBLE = (
    "No se encontraron especialidades relacionadas según los filtros seleccionados."
)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CHECKS_PER_RUN = int(os.environ.get("CHECKS_PER_RUN", "5"))
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "60"))

SCREENSHOT_PATH = Path("dian_posible_disponibilidad.png")
SCREENSHOT_FULL_PATH = Path("dian_posible_disponibilidad_full.png")
HTML_PATH = Path("dian_posible_disponibilidad.html")
TEXT_PATH = Path("dian_posible_disponibilidad.txt")


def send_telegram_text(message: str) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": message},
        timeout=20,
    )
    response.raise_for_status()


def send_telegram_photo(path: Path, caption: str) -> None:
    with path.open("rb") as photo:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
            data={"chat_id": CHAT_ID, "caption": caption},
            files={"photo": photo},
            timeout=30,
        )
    response.raise_for_status()


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


def check_once(browser, check_number: int) -> str:
    page = browser.new_page(viewport={"width": 1400, "height": 1000})

    try:
        print(f"CHECK {check_number}: opening DIAN")
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)

        if not click_visible_text(page, "Agendar cita"):
            raise RuntimeError("Could not find a visible 'Agendar cita'")

        page.wait_for_timeout(1800)

        if not click_card_by_normalized_text(page, "Persona Natural"):
            raise RuntimeError("Could not find 'Persona Natural'")

        page.wait_for_timeout(1000)

        if not click_card_by_normalized_text(page, "Videoatención"):
            raise RuntimeError("Could not find 'Videoatención'")

        page.wait_for_timeout(1000)

        if not click_card_by_normalized_text(page, "Devoluciones."):
            raise RuntimeError("Could not find 'Devoluciones.'")

        page.wait_for_timeout(2500)

        body_text = page.locator("body").inner_text()

        if NO_DISPONIBLE in body_text:
            print(f"CHECK {check_number}: no availability")
            return "no_availability"

        # Confirm the changed state a second time before alerting, to reduce
        # false positives caused by slow or partial page rendering.
        print(f"CHECK {check_number}: availability signal detected; confirming...")
        page.wait_for_timeout(8000)
        body_text_confirm = page.locator("body").inner_text()

        if NO_DISPONIBLE in body_text_confirm:
            print(f"CHECK {check_number}: transient change; no availability after confirmation")
            return "no_availability"

        print(f"CHECK {check_number}: POSSIBLE AVAILABILITY CONFIRMED")

        # Capture multiple forms of evidence. A viewport screenshot is usually
        # more reliable than full_page on dynamic SPA/modal layouts.
        page.screenshot(path=str(SCREENSHOT_PATH), full_page=False)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(SCREENSHOT_FULL_PATH), full_page=True)

        TEXT_PATH.write_text(body_text_confirm, encoding="utf-8")
        HTML_PATH.write_text(page.content(), encoding="utf-8")

        return "possible_availability"

    finally:
        page.close()


def alert_possible_availability() -> None:
    caption = (
        "🚨 DIAN: posible disponibilidad\n\n"
        "Persona Natural > Videoatención > Devoluciones\n"
        "El mensaje de 'sin disponibilidad' desapareció y se confirmó nuevamente.\n"
        "Revisa el portal de la DIAN ahora."
    )

    try:
        send_telegram_photo(SCREENSHOT_PATH, caption)
        print("Telegram alert + viewport screenshot sent")
    except Exception as exc:
        print(f"Could not send viewport screenshot to Telegram: {exc}", file=sys.stderr)
        send_telegram_text(caption)
        print("Telegram text fallback sent")

    # Send the visible page text too. This is useful even if a screenshot
    # renders blank because the DIAN page is mid-transition.
    try:
        visible_text = TEXT_PATH.read_text(encoding="utf-8")
        excerpt = visible_text[:3500]
        send_telegram_text(
            "📄 Texto visible detectado en la DIAN:\n\n" + excerpt
        )
        print("Telegram page-text evidence sent")
    except Exception as exc:
        print(f"Could not send page text to Telegram: {exc}", file=sys.stderr)


def main() -> int:
    print(
        f"DIAN monitor: {CHECKS_PER_RUN} checks, "
        f"{INTERVAL_SECONDS}s apart"
    )

    successful_checks = 0
    errors = 0
    alerted_this_run = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            for check_number in range(1, CHECKS_PER_RUN + 1):
                try:
                    status = check_once(browser, check_number)
                    successful_checks += 1

                    if status == "possible_availability" and not alerted_this_run:
                        alert_possible_availability()
                        alerted_this_run = True

                except Exception as exc:
                    errors += 1
                    print(f"CHECK {check_number} ERROR: {exc}", file=sys.stderr)

                if check_number < CHECKS_PER_RUN:
                    print(f"Waiting {INTERVAL_SECONDS}s for next check...")
                    time.sleep(INTERVAL_SECONDS)

        finally:
            browser.close()

    print(
        f"Run complete: successful_checks={successful_checks}, errors={errors}"
    )

    if successful_checks == 0:
        try:
            send_telegram_text(
                "⚠️ DIAN monitor: no se pudo completar ninguna revisión "
                "en la última ejecución de GitHub Actions. Revisa el workflow."
            )
        except Exception as exc:
            print(f"Could not send monitor-error Telegram: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
