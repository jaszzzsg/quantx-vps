import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

def check_forexfactory():
    """
    Scrapes ForexFactory calendar for today.
    Returns 2 booleans:
      - red_event_after_129: True/False
      - trump_speaks_today: True/False
    """

    url = "https://www.forexfactory.com/calendar?day=today"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Unable to load ForexFactory: {e}")
        return False, False

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.find_all("tr", {"class": "calendar__row"})

    now = datetime.now()
    cutoff = now.replace(hour=13, minute=29, second=0, microsecond=0)

    red_event_after_129 = False
    trump_speaks_today = False

    for row in rows:
        # Event name
        event_tag = row.find("td", {"class": "calendar__event"})
        if not event_tag:
            continue
        event_name = event_tag.get_text(strip=True).lower()

        # Detect Trump speech
        if "trump" in event_name and ("speech" in event_name or "speaks" in event_name):
            trump_speaks_today = True

        # Impact (Low/Medium/High)
        impact_tag = row.find("td", {"class": "calendar__impact"})
        impact = impact_tag.get("title", "").lower() if impact_tag else ""

        # Time
        time_tag = row.find("td", {"class": "calendar__time"})
        if not time_tag:
            continue
        event_time_str = time_tag.get_text(strip=True)

        # Skip "All Day", "—", "0:00", etc.
        if event_time_str.lower() in ["all day", "—", "0:00", "12am"]:
            continue

        # Convert time → datetime today
        try:
            event_dt = datetime.strptime(event_time_str, "%I:%M%p")
            event_dt = now.replace(hour=event_dt.hour, minute=event_dt.minute)
        except:
            continue

        # Check red events after 1:29pm
        if "high" in impact and event_dt > cutoff:
            red_event_after_129 = True

    return red_event_after_129, trump_speaks_today


if __name__ == "__main__":
    red_after_129, trump_today = check_forexfactory()

    print("=== EVENT GUARD REPORT ===")
    print(f"Red event after 1:29pm: {red_after_129}")
    print(f"Trump speaks today: {trump_today}")

    # FINAL DECISION
    if trump_today:
        print("❌ SKIP – Trump speech today. No trading.")
    elif red_after_129:
        print("❌ SKIP – Red event after 1:29pm.")
    else:
        print("✅ SAFE – Market clear. Proceed with ODTE entry at 1:30pm.")
