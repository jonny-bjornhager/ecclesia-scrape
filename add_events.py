import os
import re
from typing import Optional, TypedDict
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Playwright, Page, TimeoutError as PlaywrightTimeoutError

from scrape_events import scrape_events

load_dotenv()

EMAIL = os.getenv("SQUARESPACE_EMAIL", "")
PASSWORD = os.getenv("SQUARESPACE_PASSWORD", "")
BASE_URL = os.getenv(
    "SQUARESPACE_BASE_URL",
    "https://begonia-pineapple-536e.squarespace.com/config/pages/677aced393c3e24244669324",
)


class Event(TypedDict, total=False):
    date: str
    start_time: str
    end_time: str
    title: str
    slug: str
    body: Optional[str]
    excerpt: Optional[str]
    image: Optional[str]


TIME_12H_REGEX = re.compile(r"^\d{1,2}:\d{2}\s?(AM|PM)$", re.IGNORECASE)
TIME_24H_REGEX = re.compile(r"^\d{1,2}:\d{2}$")


def ensure_env():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("Sätt env vars först")


# -------------------------
# TIME FORMAT
# -------------------------
def to_12h_time(value: str) -> str:
    value = value.strip().upper()

    if TIME_12H_REGEX.match(value):
        return value

    if TIME_24H_REGEX.match(value):
        hours, minutes = map(int, value.split(":"))

        suffix = "AM"
        if hours == 0:
            hours = 12
        elif hours == 12:
            suffix = "PM"
        elif hours > 12:
            hours -= 12
            suffix = "PM"

        return f"{hours}:{minutes:02d} {suffix}"

    raise ValueError(f"Fel tid: {value}")


# -------------------------
# LOGIN + 2FA
# -------------------------
def login(page: Page):
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    try:
        page.fill('input[type="email"]', EMAIL, timeout=3000)
        page.fill('input[type="password"]', PASSWORD)
        page.click("button[data-test='login-button']")
        print("Loggar in...")
    except PlaywrightTimeoutError:
        print("Redan inloggad")

    # 2FA
    try:
        page.wait_for_selector(
            'input[placeholder="Verification code"]',
            state="visible",
            timeout=5000,
        )
        print("2FA upptäckt – väntar 7 sek")
        page.wait_for_timeout(7000)

    except PlaywrightTimeoutError:
        print("Ingen 2FA")

    # Vänta på att events UI är redo
    page.locator("button[data-test='header-add-icon']").wait_for(
        state="visible", timeout=15000
    )

    print("Events-sidan redo")


# -------------------------
# UI HELPERS
# -------------------------
def click_add_event(page: Page):
    page.locator("button[data-test='header-add-icon']").click()
    page.wait_for_timeout(1000)


def fill_title(page: Page, title: str):
    page.locator('input[aria-label="Event Title"]').fill(title)


def open_date_modal(page: Page):
    page.locator('button[aria-label="Navigate to Date and Time"]').click()
    page.wait_for_timeout(1000)


def select_tab(page: Page, name: str):
    page.locator(f'button[aria-label="{name}"]').click()
    page.wait_for_timeout(500)


def select_date(page: Page, date_value: str):
    month, day, year = date_value.split("/")

    padded = f"{int(month):02d}/{int(day):02d}/{year}"
    unpadded = f"{int(month)}/{int(day)}/{year}"

    try:
        page.locator(f'[aria-label="{padded}"]').click(timeout=3000)
    except:
        page.locator(f'[aria-label="{unpadded}"]').click(timeout=3000)

    page.wait_for_timeout(500)


# -------------------------
# FIXED TIME INPUT 🔥
# -------------------------
def set_time(page: Page, value: str):
    normalized = to_12h_time(value)

    dialog = page.get_by_role("dialog").last
    inputs = dialog.locator("input[type='text']")

    found = False

    for i in range(inputs.count()):
        inp = inputs.nth(i)

        try:
            if not inp.is_visible():
                continue

            current = inp.input_value().strip()

            if TIME_12H_REGEX.match(current):
                print(f"Fyller tid: {normalized}")

                inp.click()

                try:
                    inp.press("Control+A")
                except:
                    inp.press("Meta+A")

                inp.fill(normalized)
                inp.press("Enter")

                page.wait_for_timeout(700)

                found = True
                break

        except:
            continue

    if not found:
        raise RuntimeError(f"Kunde inte hitta tidsfält för {normalized}")


# -------------------------
# SAVE
# -------------------------
def save_date(page: Page):
    page.locator('button:has-text("Save")').click()
    page.wait_for_timeout(1500)


def save_event(page: Page):
    page.locator('button[data-test="jsf-modal-save-button"]').click(force=True)
    page.wait_for_timeout(2500)


# -------------------------
# CREATE EVENT
# -------------------------
def add_event(page: Page, event: Event):
    print(f"Skapar: {event['title']}")

    click_add_event(page)
    fill_title(page, event["title"])

    open_date_modal(page)

    # START
    select_tab(page, "Event Start")
    select_date(page, event["date"])
    set_time(page, event["start_time"])

    # END
    select_tab(page, "Event End")
    select_date(page, event["date"])
    set_time(page, event["end_time"])

    save_date(page)
    save_event(page)


def normalize(event: dict) -> Event:
    return {
        "date": event["date"],
        "start_time": event["time"],
        "end_time": event["end_time"],
        "title": event["title"],
        "excerpt": event.get("excerpt"),
    }


# -------------------------
# RUN
# -------------------------
def run(playwright: Playwright, events):
    browser = playwright.chromium.launch(headless=False, slow_mo=100)
    context = browser.new_context()
    page = context.new_page()

    try:
        login(page)

        if not events:
            print("❌ Inga events hittades")
            return

        for event in events:
            add_event(page, event)

        print("✅ Klart")
        page.wait_for_timeout(5000)

    finally:
        context.close()
        browser.close()


# -------------------------
# MAIN
# -------------------------
if __name__ == "__main__":
    ensure_env()

    with sync_playwright() as p:
        print("Hämtar events...")
        scraped = scrape_events(p)

        print(f"Hittade {len(scraped)} events")

        events = [normalize(e) for e in scraped]

        run(p, events)
