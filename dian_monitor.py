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
TARGET_TRAMITE = (
    "Bogotá - Solicitud de devolución y/o compensación "
    "Vehículos eléctricos o Híbridos persona natural"
)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

CHECKS_PER_RUN = int(os.environ.get("CHECKS_PER_RUN", "300"))
INTERVAL_SECONDS = int(os.environ.get("INTERVAL_SECONDS", "20"))

SCREENSHOT_PATH = Path("dian_posible_disponibilidad.png")
SCREENSHOT_FULL_PATH = Path("dian_posible_disponibilidad_full.png")
HTML_PATH = Path("dian_posible_disponibilidad.html")
TEXT_PATH = Path("dian_posible_disponibilidad.txt")
CONTROLS_PATH = Path("dian_controles_visibles.txt")


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


def click_card_by_normalized_text(page, target: str, contains: bool = False) -> bool:
    result = page.evaluate(
        """
        ({target, contains}) => {
          const norm = s => (s || '').replace(/\\s+/g, ' ').trim();

          const visible = el => {
            const r = el.getBoundingClientRect();
            const st = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   st.visibility !== 'hidden' &&
                   st.display !== 'none';
          };

          const wanted = norm(target);
          const matches = [...document.querySelectorAll('body *')]
            .filter(visible)
            .filter(el => {
              const text = norm(el.innerText);
              return contains ? text.includes(wanted) : text === wanted;
            });

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
        {"target": target, "contains": contains},
    )
    return bool(result)


def capture_evidence(page) -> str:
    body_text = page.locator("body").inner_text()

    # Viewport first because dynamic SPA/modal layouts can produce blank
    # full-page captures.
    page.screenshot(path=str(SCREENSHOT_PATH), full_page=False)
    page.wait_for_timeout(500)
    page.screenshot(path=str(SCREENSHOT_FULL_PATH), full_page=True)

    TEXT_PATH.write_text(body_text, encoding="utf-8")
    HTML_PATH.write_text(page.content(), encoding="utf-8")

    controls = page.evaluate(
        """
        () => {
          const visible = el => {
            const r = el.getBoundingClientRect();
            const st = getComputedStyle(el);
            return r.width > 0 && r.height > 0 &&
                   st.visibility !== 'hidden' &&
                   st.display !== 'none';
          };
          const norm = s => (s || '').replace(/\\s+/g, ' ').trim();

          return [...document.querySelectorAll(
            'button, input, select, option, textarea, [role="button"], [role="radio"], [role="option"]'
          )]
          .filter(visible)
          .map((el, i) => ({
            i,
            tag: el.tagName,
            type: el.getAttribute('type') || '',
            role: el.getAttribute('role') || '',
            name: el.getAttribute('name') || '',
            value: el.value || '',
            text: norm(el.innerText || el.getAttribute('aria-label') || ''),
            disabled: !!el.disabled
          }));
        }
        """
    )

    CONTROLS_PATH.write_text(
        "\n".join(str(item) for item in controls),
        encoding="utf-8",
    )

    return body_text


def captcha_present(page, body_text: str) -> bool:
    text = body_text.lower()
    if "captcha" in text or "recaptcha" in text or "hcaptcha" in text:
        return True

    frames = page.locator("iframe")
    for i in range(frames.count()):
        frame = frames.nth(i)
        src = (frame.get_attribute("src") or "").lower()
        title = (frame.get_attribute("title") or "").lower()
        if "captcha" in src or "captcha" in title:
            return True

    return False


def send_evidence_to_telegram(body_text: str, stage: str) -> None:
    caption = (
        f"📸 DIAN - {stage}\n"
        "Trámite: Vehículos eléctricos o Híbridos persona natural"
    )

    try:
        send_telegram_photo(SCREENSHOT_PATH, caption)
        print("Telegram screenshot sent")
    except Exception as exc:
        print(f"Could not send screenshot: {exc}", file=sys.stderr)

    try:
        excerpt = body_text[:3500]
        send_telegram_text(
            f"📄 DIAN - {stage}\n\n" + excerpt
        )
        print("Telegram page text sent")
    except Exception as exc:
        print(f"Could not send page text: {exc}", file=sys.stderr)


def advance_after_availability(page) -> None:
    # Tell the user immediately. Do not wait for screenshots or a second
    # confirmation before sending the urgent alert.
    send_telegram_text(
        "🚨 DIAN: DISPONIBILIDAD DETECTADA\n\n"
        "Persona Natural > Videoatención > Devoluciones\n"
        "Voy a avanzar automáticamente hasta donde permita el portal.\n"
        "Entra a la DIAN AHORA por si necesitas completar el CAPTCHA."
    )
    print("Immediate Telegram availability alert sent")

    # Select the exact hybrid/electric-vehicle refund procedure.
    if not click_card_by_normalized_text(page, TARGET_TRAMITE):
        # Some renderings include quotes or extra surrounding text.
        if not click_card_by_normalized_text(
            page,
            "Solicitud de devolución y/o compensación Vehículos eléctricos o Híbridos persona natural",
            contains=True,
        ):
            body_text = capture_evidence(page)
            send_evidence_to_telegram(body_text, "trámite disponible, no pude seleccionarlo")
            return

    page.wait_for_timeout(500)

    if not click_visible_text(page, "Siguiente"):
        body_text = capture_evidence(page)
        send_evidence_to_telegram(body_text, "trámite seleccionado, no encontré Siguiente")
        return

    page.wait_for_timeout(1800)

    body_text = capture_evidence(page)
    stage = "pantalla posterior al trámite"

    if captcha_present(page, body_text):
        stage = "CAPTCHA detectado"
        send_telegram_text(
            "⚠️ CAPTCHA DETECTADO EN DIAN\n\n"
            "El bot ya seleccionó el trámite y avanzó hasta la pantalla protegida. "
            "El CAPTCHA requiere intervención humana."
        )

    send_evidence_to_telegram(body_text, stage)


def check_once(browser, check_number: int, alert_allowed: bool) -> str:
    page = browser.new_page(viewport={"width": 1400, "height": 1000})

    try:
        print(f"CHECK {check_number}: opening DIAN")
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2200)

        if not click_visible_text(page, "Agendar cita"):
            raise RuntimeError("Could not find a visible 'Agendar cita'")

        page.wait_for_timeout(1300)

        if not click_card_by_normalized_text(page, "Persona Natural"):
            raise RuntimeError("Could not find 'Persona Natural'")

        page.wait_for_timeout(700)

        if not click_card_by_normalized_text(page, "Videoatención"):
            raise RuntimeError("Could not find 'Videoatención'")

        page.wait_for_timeout(700)

        if not click_card_by_normalized_text(page, "Devoluciones."):
            raise RuntimeError("Could not find 'Devoluciones.'")

        page.wait_for_timeout(1600)

        body_text = page.locator("body").inner_text()

        if NO_DISPONIBLE in body_text:
            print(f"CHECK {check_number}: no availability")
            return "no_availability"

        print(f"CHECK {check_number}: AVAILABILITY SIGNAL")

        if alert_allowed:
            try:
                advance_after_availability(page)
            except Exception as exc:
                print(f"Advance/alert error: {exc}", file=sys.stderr)
                try:
                    body_text = capture_evidence(page)
                    send_evidence_to_telegram(body_text, "disponibilidad detectada")
                except Exception as evidence_exc:
                    print(f"Evidence error: {evidence_exc}", file=sys.stderr)

        return "possible_availability"

    finally:
        page.close()


def main() -> int:
    print(
        f"DIAN monitor: {CHECKS_PER_RUN} checks, "
        f"{INTERVAL_SECONDS}s between checks"
    )

    successful_checks = 0
    errors = 0
    availability_active = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            for check_number in range(1, CHECKS_PER_RUN + 1):
                try:
                    status = check_once(
                        browser,
                        check_number,
                        alert_allowed=not availability_active,
                    )
                    successful_checks += 1

                    if status == "possible_availability":
                        availability_active = True
                    else:
                        availability_active = False

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
