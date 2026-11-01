"""
Weekly reset-herinnering
------------------------
Post elke week in Discord dat de weekly reset (raid-lockouts, weeklies) geweest is.
Draait via .github/workflows/weekly-reset.yml (woensdagochtend, EU-reset).

Geheim: DISCORD_WEBHOOK (zelfde webhook als het nieuwskanaal),
        of DISCORD_WEBHOOK_RESET als je hem in een ander kanaal wilt.
"""

import datetime as dt
import os
import sys
import time

import requests

KLEUR = 0xF1C40F


def volgende_reset(nu: dt.datetime) -> int:
    """Unix-tijd van de volgende EU-reset: woensdag 04:00 UTC."""
    reset = (nu + dt.timedelta(days=(2 - nu.weekday()) % 7)).replace(hour=4, minute=0, second=0, microsecond=0)
    if reset <= nu:
        reset += dt.timedelta(days=7)
    return int(reset.timestamp())


def main() -> None:
    webhook = (os.environ.get("DISCORD_WEBHOOK_RESET") or os.environ.get("DISCORD_WEBHOOK") or "").strip()
    if "/api/webhooks/" not in webhook:
        print("Geen geldige webhook ingesteld (DISCORD_WEBHOOK_RESET of DISCORD_WEBHOOK). Er gebeurt niets.")
        return

    nu = dt.datetime.now(dt.timezone.utc)
    bericht = {
        "username": "Weekly Reset",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": "🔄 Weekly reset!",
            "description": (
                "De raid-lockouts en weekly quests van **WoW Forever** zijn gereset.\n"
                "Tijd om een speelavond te plannen! 🐉\n\n"
                f"-# Volgende reset: <t:{volgende_reset(nu)}:F>"
            ),
            "color": KLEUR,
            "timestamp": nu.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }],
    }
    for _ in range(4):
        r = requests.post(webhook, json=bericht, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
            continue
        r.raise_for_status()
        print("Reset-herinnering gepost.")
        return
    sys.exit("Discord bleef 'rate limited' antwoorden")


if __name__ == "__main__":
    main()
