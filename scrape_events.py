import re
from datetime import datetime, timedelta


def scrape_events(playwright):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://www.kyrktorget.se/pingstbohus/kalender/")
    page.wait_for_load_state("domcontentloaded")

    # Hitta panel-body (där all text ligger)
    container = page.query_selector("div.panel-body")

    if not container:
        print("❌ Kunde inte hitta kalendern")
        browser.close()
        return []

    text = container.inner_text()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    print("DEBUG lines:")
    for l in lines:
        print(l)

    events = []

    i = 0
    while i < len(lines):
        line = lines[i].lower()

        # Matcha datumrad
        match = re.match(r"(\w+)\s(\d{2})/(\d{2})\s+kl\s+(\d{2}:\d{2})", line)

        if not match:
            i += 1
            continue

        weekday, day, month, time_str = match.groups()

        day = int(day)
        month = int(month)
        year = datetime.now().year

        date = f"{month}/{day}/{year}"

        # Nästa rad = titel / talare
        title_line = lines[i + 1]

        # Kolla om det finns en extra rad (t.ex. Bukobahjälpen)
        extra_line = None
        if i + 2 < len(lines):
            next_line = lines[i + 2].lower()

            # Om nästa rad INTE är ett nytt datum → extra info
            if not re.match(r"\w+\s\d{2}/\d{2}", next_line):
                extra_line = lines[i + 2]

        start_dt = datetime.strptime(time_str, "%H:%M")
        end_time = (start_dt + timedelta(hours=2)).strftime("%H:%M")

        event = {
            "date": date,
            "time": time_str,
            "end_time": end_time,
            "title": title_line,
        }

        # 🔥 Special: söndag 11:00 → Gudstjänst + talare
        if weekday == "söndag" and time_str == "11:00":
            speaker = title_line

            if extra_line:
                speaker = f"{title_line} | {extra_line}"

            event["title"] = "Gudstjänst"
            event["excerpt"] = f"<strong>Talare:</strong> {speaker}."

        # Specialfall
        if title_line == "Evangelisation":
            event["excerpt"] = "Vi samlas på Bohus torg för att dela evangeliet."

        if title_line == "Administrationsmöte":
            i += 1
            continue

        events.append(event)

        # Hoppa fram rätt antal rader
        if extra_line:
            i += 3
        else:
            i += 2

    browser.close()

    print(f"✅ Hittade {len(events)} events")
    return events
