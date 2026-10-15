#!/usr/bin/env python3
"""Read-only Munich availability for ElevenAgents; no credentials or call access."""
import json
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Berlin")


def holidays(year):
    # Gregorian Easter (Meeus/Jones/Butcher), then statutory offsets.
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    easter = date(year, n // 31, n % 31 + 1)
    # Source, checked 2026-10-15:
    # https://www.stmi.bayern.de/staat-und-verfassung/feiertage/
    # Munich observes Assumption; Augsburg's local Peace Festival does not apply.
    # https://www.muenchen.de/aktuell/feiertage-bayern-2026-und-2027
    result = {date(year, month, day): name for month, day, name in (
        (1, 1, "Neujahr"), (1, 6, "Heilige Drei Könige"),
        (5, 1, "Tag der Arbeit"), (8, 15, "Mariä Himmelfahrt"),
        (10, 3, "Tag der Deutschen Einheit"), (11, 1, "Allerheiligen"),
        (12, 25, "Erster Weihnachtstag"), (12, 26, "Zweiter Weihnachtstag"),
    )}
    result.update({easter + timedelta(days=offset): name for offset, name in (
        (-2, "Karfreitag"), (1, "Ostermontag"), (39, "Christi Himmelfahrt"),
        (50, "Pfingstmontag"), (60, "Fronleichnam"),
    )})
    return result


def availability(now=None):
    now = now or datetime.now(ZONE)
    if now.tzinfo is None:
        raise ValueError("An aware datetime is required")
    local = now.astimezone(ZONE)
    holiday = holidays(local.year).get(local.date())
    reason = ("public_holiday" if holiday else "weekend" if local.weekday() >= 5
              else "outside_hours" if not 9 <= local.hour < 17 else "open")
    next_open = None
    if reason != "open":
        candidate = local.replace(hour=9, minute=0, second=0, microsecond=0)
        for _ in range(370):
            if (candidate > local and candidate.weekday() < 5
                    and candidate.date() not in holidays(candidate.year)):
                next_open = candidate.isoformat()
                break
            candidate += timedelta(days=1)
    return {"can_transfer": reason == "open", "reason": reason,
            "local_time": local.isoformat(), "timezone": "Europe/Berlin",
            "holiday": holiday, "next_open": next_open,
            "schedule": "Monday-Friday 09:00 inclusive to 17:00 exclusive; Munich public holidays excluded"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # No caller-controlled date, telephone number or arbitrary URL accepted.
        if self.path != "/business-hours":
            self.send_error(404)
            return
        body = json.dumps(availability(), ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 18092), Handler).serve_forever()
