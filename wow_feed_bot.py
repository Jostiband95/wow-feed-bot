"""
WoW Feed Bot
------------
Plaatst automatisch in Discord:
  * nieuwe WoW Forever-nieuwsartikelen van Wowhead
  * nieuwe video's van het officiele World of Warcraft YouTube-kanaal

Werkt via Discord-webhooks: geen bot-token of Developer Portal nodig.
Instellingen staan in config.json (zie LEESMIJ.md). Logboek: bot.log.
"""

import html
import json
import os
import re
import socket
import sys
import time
from pathlib import Path

import feedparser
import requests

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"
STATE_FILE = BASE / "gezien.json"
USER_AGENT = "WoWFeedBot/1.0 (Discord nieuwsbot)"
MAX_ONTHOUDEN = 300  # per bron, zodat gezien.json niet eindeloos groeit


LOG_FILE = BASE / "bot.log"


def log(msg: str) -> None:
    regel = f"{time.strftime('[%Y-%m-%d %H:%M:%S]')} {msg}"
    if sys.stdout:
        print(regel, flush=True)
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.replace(LOG_FILE.with_suffix(".log.old"))
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(regel + "\n")
    except OSError:
        pass


def enige_instantie():
    """Voorkomt dat de bot twee keer tegelijk draait (anders dubbele posts)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 47821))
    except OSError:
        log("Bot draait al, deze tweede start wordt afgebroken.")
        sys.exit(0)
    return s


def laad_json(pad: Path, standaard):
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return standaard


def bewaar_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def haal_feed(url: str):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"feed kon niet gelezen worden: {feed.bozo_exception}")
    return feed.entries


def entry_id(e) -> str:
    return e.get("yt_videoid") or e.get("id") or e.get("link")


def schoon(tekst: str, max_len: int = 300) -> str:
    tekst = html.unescape(re.sub(r"<[^>]+>", " ", tekst or ""))
    tekst = re.sub(r"\s+", " ", tekst).strip()
    return tekst if len(tekst) <= max_len else tekst[: max_len - 1].rstrip() + "…"


def past_filter(e, trefwoorden) -> bool:
    if not trefwoorden:
        return True
    tekst = " ".join(
        [e.get("title", ""), e.get("summary", "")]
        + [t.get("term", "") for t in e.get("tags", [])]
    ).lower()
    return any(w.lower() in tekst for w in trefwoorden)


def afbeelding(e):
    for veld in ("media_thumbnail", "media_content"):
        if e.get(veld):
            return e[veld][0].get("url")
    for link in e.get("links", []):
        if link.get("type", "").startswith("image"):
            return link.get("href")
    m = re.search(r'<img[^>]+src="([^"]+)"', e.get("summary", ""))
    return m.group(1) if m else None


def maak_bericht(bron: dict, e) -> dict:
    if bron["type"] == "youtube":
        # Een kale link laat Discord zelf de afspeelbare videospeler tonen.
        tekst = bron.get("bericht", "📺 Nieuwe video: **{titel}**\n{link}")
        return {"content": tekst.format(titel=e.get("title", ""), link=e.get("link", ""))}

    embed = {
        "title": e.get("title", "Nieuw artikel")[:256],
        "url": e.get("link"),
        "description": schoon(e.get("summary", "")),
        "color": int(bron.get("kleur", "#B4004E").lstrip("#"), 16),
        "footer": {"text": bron.get("naam", "Wowhead")},
    }
    if bron.get("tijd") is not False and e.get("published_parsed"):
        embed["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", e.published_parsed)
    img = afbeelding(e)
    if img:
        embed["image"] = {"url": img}
    bericht = {"embeds": [embed]}
    if bron.get("bericht"):
        bericht["content"] = bron["bericht"]
    return bericht


def post(webhook: str, bericht: dict, naam: str, avatar: str | None) -> None:
    bericht = dict(bericht, username=naam)
    if avatar:
        bericht["avatar_url"] = avatar
    for _ in range(3):
        r = requests.post(webhook, json=bericht, timeout=30)
        if r.status_code == 429:  # rate limit van Discord
            wacht = float(r.json().get("retry_after", 2))
            time.sleep(wacht + 0.5)
            continue
        r.raise_for_status()
        return
    raise RuntimeError("Discord bleef 'rate limited' antwoorden")


def check_bron(bron: dict, state: dict) -> None:
    sleutel = bron["naam"]
    eerste_keer = sleutel not in state
    gezien = state.setdefault(sleutel, [])

    entries = haal_feed(bron["feed"])
    link_bevat = bron.get("link_bevat")  # bijv. "/eu/" om alleen EU-posts te nemen
    nieuw = [
        e for e in entries
        if entry_id(e) not in gezien
        and past_filter(e, bron.get("filter"))
        and (not link_bevat or link_bevat in (e.get("link") or ""))
    ]

    if eerste_keer:
        # Eerste run: alles als 'gezien' markeren zodat het kanaal niet volgespamd wordt.
        gezien.extend(entry_id(e) for e in entries)
        log(f"{sleutel}: eerste keer, {len(entries)} bestaande items overgeslagen")
        if bron.get("bij_start_laatste_posten") and nieuw:
            nieuw = nieuw[:1]
        else:
            return

    for e in reversed(nieuw):  # oudste eerst, zodat de volgorde klopt in Discord
        post(bron["webhook"], maak_bericht(bron, e), bron.get("afzender", sleutel), bron.get("avatar"))
        if entry_id(e) not in gezien:
            gezien.append(entry_id(e))
        log(f"{sleutel}: gepost → {e.get('title')}")
        time.sleep(1.5)

    # Ook items die niet door het filter kwamen onthouden, en de lijst inkorten.
    for e in entries:
        if entry_id(e) not in gezien:
            gezien.append(entry_id(e))
    del gezien[:-MAX_ONTHOUDEN]


def laad_config():
    config = laad_json(CONFIG_FILE, None)
    if config is None:
        sys.exit("config.json ontbreekt. Kopieer config.voorbeeld.json naar config.json en vul je webhooks in.")
    bronnen = [b for b in config["bronnen"] if b.get("aan", True)]
    for b in bronnen:
        # "${DISCORD_WEBHOOK}" wordt vervangen door de geheime waarde (GitHub Secret)
        b["webhook"] = os.path.expandvars(b.get("webhook", ""))
        if "discord.com/api/webhooks" not in b.get("webhook", ""):
            sys.exit(f"Vul bij bron '{b['naam']}' een geldige Discord-webhook-URL in.")
    interval = max(int(config.get("interval_minuten", 10)), 2) * 60
    return bronnen, interval


def main() -> None:
    bronnen, interval = laad_config()
    slot = enige_instantie()  # noqa: F841 (moet open blijven)
    eenmalig = "--eenmalig" in sys.argv
    log(f"Bot gestart met {len(bronnen)} bron(nen), controle elke {interval // 60} min.")

    while True:
        # config.json elke ronde opnieuw lezen, zodat wijzigingen zonder herstart werken
        try:
            bronnen, interval = laad_config()
        except (SystemExit, ValueError) as fout:
            log(f"config.json kon niet gelezen worden, vorige instellingen blijven actief ({fout})")
        state = laad_json(STATE_FILE, {})
        for bron in bronnen:
            try:
                check_bron(bron, state)
            except Exception as fout:  # één kapotte feed mag de rest niet stoppen
                log(f"{bron['naam']}: fout → {fout}")
            bewaar_state(state)
        if eenmalig:
            break
        time.sleep(interval)

if __name__ == "__main__":
    main()
