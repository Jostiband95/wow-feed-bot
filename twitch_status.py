"""
Twitch Live Status
------------------
Houdt in Discord één statusbericht bij met welke streamers live zijn.
Het bericht wordt bij elke run bijgewerkt (niet opnieuw geplaatst).

Instellingen:   streamers.json
Geheimen (omgevingsvariabelen / GitHub Secrets):
  TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, DISCORD_WEBHOOK_LIVE
Onthoudt het Discord-bericht in: twitch_status.json
"""

import calendar
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "streamers.json"
STATE_FILE = BASE / "twitch_status.json"
TWITCH_AUTH = os.environ.get("TWITCH_AUTH_URL", "https://id.twitch.tv/oauth2/token")
TWITCH_API = os.environ.get("TWITCH_API_URL", "https://api.twitch.tv/helix")
PAARS = 0x9146FF
GRIJS = 0x4F545C


def log(msg: str) -> None:
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def omgeving(naam: str) -> str:
    waarde = os.environ.get(naam, "").strip()
    if not waarde:
        sys.exit(f"Geheim '{naam}' ontbreekt. Voeg het toe bij GitHub → Settings → Secrets and variables → Actions.")
    return waarde


# ---------- Twitch ----------

def twitch_token(client_id: str, secret: str) -> str:
    r = requests.post(TWITCH_AUTH, data={
        "client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"}, timeout=30)
    if r.status_code in (400, 401, 403):
        sys.exit("Twitch weigert de Client ID / Client Secret. Controleer de geheimen TWITCH_CLIENT_ID en TWITCH_CLIENT_SECRET.")
    r.raise_for_status()
    return r.json()["access_token"]


def twitch_get(pad: str, params, headers) -> list:
    r = requests.get(f"{TWITCH_API}/{pad}", params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def in_blokken(lijst, grootte=100):
    for i in range(0, len(lijst), grootte):
        yield lijst[i:i + grootte]


def haal_status(namen: list[str], client_id: str, token: str):
    headers = {"Client-Id": client_id, "Authorization": f"Bearer {token}"}
    gebruikers, streams = {}, {}
    for blok in in_blokken(namen):
        for u in twitch_get("users", [("login", n) for n in blok], headers):
            gebruikers[u["login"].lower()] = u
        for s in twitch_get("streams", [("user_login", n) for n in blok] + [("first", "100")], headers):
            streams[s["user_login"].lower()] = s
    return gebruikers, streams


# ---------- Discord-bericht ----------

def kijkers(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k".replace(".0k", "k").replace(".", ",")
    return str(n)


def kort(tekst: str, max_len: int) -> str:
    tekst = re.sub(r"\s+", " ", tekst or "").strip()
    tekst = tekst.replace("*", "").replace("_", "").replace("`", "").replace("[", "(").replace("]", ")")
    return tekst if len(tekst) <= max_len else tekst[: max_len - 1].rstrip() + "…"


def maak_bericht(config: dict, namen: list[str], gebruikers: dict, streams: dict) -> dict:
    live, offline, onbekend = [], [], []
    for naam in namen:
        sleutel = naam.lower()
        u = gebruikers.get(sleutel)
        weergave = (u or {}).get("display_name") or naam
        if sleutel in streams:
            live.append((streams[sleutel], weergave, sleutel))
        elif u:
            offline.append(weergave)
        else:
            onbekend.append(naam)

    live.sort(key=lambda x: -x[0].get("viewer_count", 0))
    regels = []
    for s, weergave, login in live:
        start = s.get("started_at", "")
        sinds = ""
        if start:
            ts = calendar.timegm(time.strptime(start, "%Y-%m-%dT%H:%M:%SZ"))
            sinds = f" · live sinds <t:{ts}:R>"
        spel = s.get("game_name") or "Geen categorie"
        regels.append(
            f"🔴 **[{weergave}](https://twitch.tv/{login})** — {kort(spel, 40)} · 👁 {kijkers(s.get('viewer_count', 0))}{sinds}\n"
            f" *{kort(s.get('title', ''), 90)}*"
        )

    nu = int(time.time())
    beschrijving = "\n".join(regels) if regels else "*Er is nu niemand live.*"
    # Discord: max 4096 tekens in de beschrijving
    while len(beschrijving) > 4000 and regels:
        regels.pop()
        beschrijving = "\n".join(regels) + "\n*…en meer*"

    embeds = [{
        "title": f"🔴 Live nu ({len(live)}/{len(namen)})",
        "description": beschrijving + f"\n\n-# Bijgewerkt <t:{nu}:R>",
        "color": PAARS if live else GRIJS,
    }]
    if offline:
        tekst = " · ".join(sorted(offline, key=str.lower))
        embeds.append({"title": f"⚫ Offline ({len(offline)})", "description": tekst[:4000], "color": GRIJS})
    if onbekend:
        log("Niet gevonden op Twitch: " + ", ".join(onbekend))
        embeds.append({"description": "❓ Niet gevonden op Twitch: " + ", ".join(onbekend), "color": GRIJS})

    return {
        "username": config.get("afzender", "Twitch Live"),
        "content": config.get("kop", ""),
        "embeds": embeds,
        "allowed_mentions": {"parse": []},
    }


# ---------- Discord-webhook ----------

def webhook_basis(webhook: str) -> str:
    m = re.match(r"(https?://[^ ]+?/api/webhooks/\d+/[\w-]+)", webhook)
    if not m:
        sys.exit("DISCORD_WEBHOOK_LIVE is geen geldige Discord-webhook-URL.")
    return m.group(1)


def discord(methode: str, url: str, bericht: dict | None = None) -> requests.Response:
    for _ in range(4):
        r = requests.request(methode, url, json=bericht, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
            continue
        return r
    raise RuntimeError("Discord bleef 'rate limited' antwoorden")


def plaats_of_werk_bij(webhook: str, bericht: dict, state: dict) -> None:
    basis = webhook_basis(webhook)
    bericht_id = state.get("bericht_id")
    if bericht_id:
        patch = dict(bericht)
        patch.pop("username", None)  # kan niet gewijzigd worden bij bijwerken
        r = discord("PATCH", f"{basis}/messages/{bericht_id}", patch)
        if r.status_code == 200:
            log("Statusbericht bijgewerkt.")
            return
        if r.status_code not in (404, 403):
            r.raise_for_status()
        log("Oud statusbericht niet gevonden (verwijderd?), er wordt een nieuw geplaatst.")
    r = discord("POST", f"{basis}?wait=true", bericht)
    r.raise_for_status()
    state["bericht_id"] = r.json()["id"]
    log(f"Nieuw statusbericht geplaatst ({state['bericht_id']}).")


# ---------- Hoofdprogramma ----------

def main() -> None:
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    namen = list(dict.fromkeys(n.strip().lstrip("@") for n in config["streamers"] if n.strip()))
    geheimen = ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "DISCORD_WEBHOOK_LIVE")
    if not any(os.environ.get(g, "").strip() for g in geheimen):
        log("Nog niet ingesteld: voeg de geheimen " + ", ".join(geheimen) + " toe. Er gebeurt nu niets.")
        return
    client_id = omgeving("TWITCH_CLIENT_ID")
    secret = omgeving("TWITCH_CLIENT_SECRET")
    webhook = omgeving("DISCORD_WEBHOOK_LIVE")

    token = twitch_token(client_id, secret)
    gebruikers, streams = haal_status(namen, client_id, token)
    log(f"{len(streams)} van {len(namen)} streamers live.")

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    plaats_of_werk_bij(webhook, maak_bericht(config, namen, gebruikers, streams), state)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
