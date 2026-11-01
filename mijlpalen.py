"""
WoW Mijlpalen
-------------
Houdt de characters uit mijlpalen.json in de gaten via de officiële Blizzard API
en post in Discord als er iets te vieren is:
  * level-ups (extra feestelijk op de levels uit "speciale_levels")
  * nieuwe gear vanaf "min_kwaliteit" (UNCOMMON, RARE, EPIC of LEGENDARY)
  * nieuwe mounts (alleen als de API die voor WoW Forever teruggeeft)

De eerste keer dat een character gevonden wordt, onthoudt de bot alleen de
huidige stand (niets posten), zodat het kanaal niet volloopt met oude spullen.

Let op: Blizzard werkt profielgegevens meestal pas bij nadat je uitlogt.

Instellingen:   mijlpalen.json
Geheimen (omgevingsvariabelen / GitHub Secrets):
  BLIZZARD_CLIENT_ID, BLIZZARD_CLIENT_SECRET
  DISCORD_WEBHOOK_MIJLPALEN   (valt terug op MILESTONES_WEBHOOK_URL of DISCORD_WEBHOOK)
Onthoudt de stand in: mijlpalen_status.json
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "mijlpalen.json"
STATE_FILE = BASE / "mijlpalen_status.json"
AUTH_URL = os.environ.get("BLIZZARD_AUTH_URL", "https://oauth.battle.net/token")
API_URL = os.environ.get("BLIZZARD_API_URL", "https://{regio}.api.blizzard.com")

KWALITEIT = ["POOR", "COMMON", "UNCOMMON", "RARE", "EPIC", "LEGENDARY"]
KWALITEIT_KLEUR = {"UNCOMMON": 0x1EFF00, "RARE": 0x0070DD, "EPIC": 0xA335EE, "LEGENDARY": 0xFF8000}
KWALITEIT_ICOON = {"UNCOMMON": "🟢", "RARE": "🔵", "EPIC": "🟣", "LEGENDARY": "🟠"}
CLASS_KLEUR = {  # officiële class-kleuren, op class-ID
    1: 0xC69B6D, 2: 0xF48CBA, 3: 0xAAD372, 4: 0xFFF468, 5: 0xFFFFFF,
    6: 0xC41E3A, 7: 0x0070DD, 8: 0x3FC7EB, 9: 0x8788EE, 10: 0x00FF98,
    11: 0xFF7C0A, 12: 0xA330C9, 13: 0x33937F,
}
GOUD = 0xF1C40F


class NietGevonden(Exception):
    pass


def log(msg: str) -> None:
    print(time.strftime("[%Y-%m-%d %H:%M:%S]"), msg, flush=True)


def slug(tekst: str) -> str:
    tekst = tekst.strip().lower().replace("'", "")
    return re.sub(r"\s+", "-", tekst)


# ---------- Blizzard API ----------

def blizzard_token(client_id: str, secret: str) -> str:
    r = requests.post(AUTH_URL, auth=(client_id, secret),
                      data={"grant_type": "client_credentials"}, timeout=30)
    if r.status_code in (400, 401, 403):
        sys.exit("Blizzard weigert de Client ID / Client Secret. Controleer de geheimen "
                 "BLIZZARD_CLIENT_ID en BLIZZARD_CLIENT_SECRET.")
    r.raise_for_status()
    return r.json()["access_token"]


class Blizzard:
    def __init__(self, token: str, regio: str, taal: str):
        self.basis = API_URL.format(regio=regio)
        self.taal = taal
        self.sessie = requests.Session()
        self.sessie.headers["Authorization"] = f"Bearer {token}"

    def character(self, realm: str, naam: str, namespace: str, extra: str = "") -> dict:
        pad = f"/profile/wow/character/{quote(slug(realm))}/{quote(naam.strip().lower())}{extra}"
        for poging in range(3):
            r = self.sessie.get(self.basis + pad, timeout=30,
                                params={"namespace": namespace, "locale": self.taal})
            if r.status_code == 429:
                time.sleep(2 + poging * 2)
                continue
            if r.status_code in (403, 404):
                raise NietGevonden(f"{r.status_code} op {pad}")
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Blizzard bleef 'rate limited' antwoorden")

    def optioneel(self, realm, naam, namespace, extra):
        """Onderdelen die de API voor Classic-versies soms niet heeft: None i.p.v. fout."""
        try:
            return self.character(realm, naam, namespace, extra)
        except NietGevonden:
            return None


def kies_namespace(api: Blizzard, config: dict, state: dict, chars: list) -> str | None:
    regio = config.get("regio", "eu")
    if config.get("namespace", "auto") != "auto":
        return config["namespace"].format(regio=regio)
    if state.get("namespace"):
        return state["namespace"]
    for kandidaat in config.get("namespace_kandidaten", []):
        ns = kandidaat.format(regio=regio)
        for c in chars:
            try:
                api.character(c["realm"], c["naam"], ns)
            except NietGevonden:
                continue
            log(f"Namespace gevonden: {ns} (via {c['naam']})")
            state["namespace"] = ns
            return ns
    return None


# ---------- Wat is er veranderd? ----------

def gear_link(config: dict, item_id: int) -> str:
    pad = config.get("wowhead_pad", "").strip("/")
    return f"https://www.wowhead.com/{pad + '/' if pad else ''}item={item_id}"


def controleer(api: Blizzard, config: dict, c: dict, ns: str, oud: dict | None) -> tuple[dict, list]:
    realm, naam = c["realm"], c["naam"]
    profiel = api.character(realm, naam, ns)
    uitrusting = api.optioneel(realm, naam, ns, "/equipment") or {}
    mounts_data = api.optioneel(realm, naam, ns, "/collections/mounts")
    media = api.optioneel(realm, naam, ns, "/character-media") or {}

    items = [i for i in uitrusting.get("equipped_items", []) if i.get("item", {}).get("id")]
    mounts = {m["mount"]["id"]: m["mount"].get("name", "Mount")
              for m in (mounts_data or {}).get("mounts", []) if m.get("mount", {}).get("id")}

    nieuw = {
        "level": profiel.get("level", 0),
        "items": sorted({i["item"]["id"] for i in items} | set((oud or {}).get("items", []))),
        "mounts": sorted(set(mounts) | set((oud or {}).get("mounts", []))),
        "mounts_bekend": mounts_data is not None,
    }
    if oud is None:
        log(f"{naam}: voor het eerst gevonden (level {nieuw['level']}, {len(items)} items, "
            f"{len(mounts) if mounts_data is not None else 'geen'} mounts) — stand onthouden, niets gepost.")
        return nieuw, []

    kop = {
        "name": f"{profiel.get('name', naam)}" + (f" ({c['speler']})" if c.get("speler") else ""),
    }
    avatar = next((a["value"] for a in media.get("assets", []) if a.get("key") == "avatar"), None)
    if avatar:
        kop["icon_url"] = avatar
    class_kleur = CLASS_KLEUR.get(profiel.get("character_class", {}).get("id"), GOUD)
    nu = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    embeds = []

    # Level-up
    was, is_nu = oud.get("level", 0), nieuw["level"]
    if is_nu > was:
        speciaal = [lv for lv in config.get("speciale_levels", []) if was < lv <= is_nu]
        max_lv = max(config.get("speciale_levels", [60]) or [60])
        if is_nu >= max_lv and was < max_lv:
            titel, kleur = f"🏆 MAX LEVEL! {profiel.get('name', naam)} is level {is_nu}!", GOUD
        elif speciaal:
            titel, kleur = f"🎉 Level {is_nu} bereikt!", GOUD
        else:
            titel, kleur = f"⬆️ Level {is_nu}", class_kleur
        klasse = profiel.get("character_class", {}).get("name", "")
        ras = profiel.get("race", {}).get("name", "")
        omschrijving = f"Van level {was} naar **{is_nu}**." if is_nu - was > 1 else ""
        if ras or klasse:
            omschrijving += ("\n" if omschrijving else "") + f"-# {ras} {klasse}".strip()
        embeds.append({"author": kop, "title": titel, "description": omschrijving or None,
                       "color": kleur, "timestamp": nu})

    # Nieuwe gear
    drempel = KWALITEIT.index(config.get("min_kwaliteit", "RARE").upper())
    gezien = set(oud.get("items", []))
    nieuwe_items = [i for i in items
                    if i["item"]["id"] not in gezien
                    and i.get("quality", {}).get("type", "COMMON") in KWALITEIT
                    and KWALITEIT.index(i["quality"]["type"]) >= drempel]
    if nieuwe_items:
        beste = max(nieuwe_items, key=lambda i: KWALITEIT.index(i["quality"]["type"]))["quality"]["type"]
        regels = [f"{KWALITEIT_ICOON.get(i['quality']['type'], '▫️')} "
                  f"**[{i.get('name', 'Item')}]({gear_link(config, i['item']['id'])})**"
                  f" · {i.get('slot', {}).get('name', '')}" for i in nieuwe_items]
        embeds.append({"author": kop, "title": "✨ Nieuwe gear!" if len(regels) > 1 else "✨ Nieuw item!",
                       "description": "\n".join(regels)[:4000],
                       "color": KWALITEIT_KLEUR.get(beste, class_kleur), "timestamp": nu})

    # Nieuwe mounts
    # (alleen als er vorige keer ook al mount-gegevens waren, anders is dit de nulmeting)
    nieuwe_mounts = [n for mid, n in mounts.items() if mid not in set(oud.get("mounts", []))]
    if nieuwe_mounts and oud.get("mounts_bekend"):
        embeds.append({"author": kop, "title": "🐎 Nieuwe mount!" if len(nieuwe_mounts) == 1 else "🐎 Nieuwe mounts!",
                       "description": "\n".join(f"**{n}**" for n in nieuwe_mounts)[:4000],
                       "color": class_kleur, "timestamp": nu})
    nieuw["mounts_bekend"] = mounts_data is not None or bool(oud.get("mounts_bekend"))

    if avatar:
        for e in embeds:
            e["thumbnail"] = {"url": avatar}
    return nieuw, [{k: v for k, v in e.items() if v is not None} for e in embeds]


# ---------- Discord ----------

def post(webhook: str, afzender: str, embeds: list) -> None:
    for blok in range(0, len(embeds), 10):  # Discord: max 10 embeds per bericht
        bericht = {"username": afzender, "embeds": embeds[blok:blok + 10],
                   "allowed_mentions": {"parse": []}}
        for _ in range(4):
            r = requests.post(webhook, json=bericht, timeout=30)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError("Discord bleef 'rate limited' antwoorden")
        time.sleep(1)


# ---------- Hoofdprogramma ----------

def main() -> None:
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    standaard_realm = config.get("realm", "")
    chars = []
    for c in config.get("characters", []):
        c = dict(c, realm=(c.get("realm") or standaard_realm).strip(), naam=c.get("naam", "").strip())
        if c["naam"] and c["realm"]:
            chars.append(c)
        elif c.get("speler") or c["naam"]:
            log(f"Overgeslagen: {c.get('speler') or c['naam']} — vul 'naam' en 'realm' in mijlpalen.json in.")
    if not chars:
        log("Nog geen characters ingevuld in mijlpalen.json. Er gebeurt nu niets.")
        return

    client_id = os.environ.get("BLIZZARD_CLIENT_ID", "").strip()
    secret = os.environ.get("BLIZZARD_CLIENT_SECRET", "").strip()
    webhook = next((os.environ[v].strip() for v in
                    ("DISCORD_WEBHOOK_MIJLPALEN", "MILESTONES_WEBHOOK_URL", "DISCORD_WEBHOOK")
                    if os.environ.get(v, "").strip()), "")
    ontbreekt = [n for n, w in (("BLIZZARD_CLIENT_ID", client_id), ("BLIZZARD_CLIENT_SECRET", secret),
                                ("DISCORD_WEBHOOK_MIJLPALEN", webhook)) if not w]
    if ontbreekt:
        log("Nog niet ingesteld: voeg de geheimen " + ", ".join(ontbreekt) + " toe. Er gebeurt nu niets.")
        return
    if "/api/webhooks/" not in webhook:
        sys.exit("DISCORD_WEBHOOK_MIJLPALEN is geen geldige Discord-webhook-URL.")

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    state.setdefault("characters", {})

    api = Blizzard(blizzard_token(client_id, secret), config.get("regio", "eu"), config.get("taal", "en_GB"))
    ns = kies_namespace(api, config, state, chars)
    if not ns:
        log("Geen enkel character gevonden in de API (nog niet live, verkeerde naam/realm, "
            "of nog nooit ingelogd/uitgelogd). Volgende keer opnieuw.")
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    gevonden = 0
    for c in chars:
        sleutel = f"{slug(c['realm'])}/{c['naam'].lower()}"
        try:
            nieuw, embeds = controleer(api, config, c, ns, state["characters"].get(sleutel))
        except NietGevonden:
            log(f"{c['naam']}: niet gevonden op realm '{c['realm']}' ({ns}).")
            continue
        except Exception as fout:  # één character mag de rest niet stoppen
            log(f"{c['naam']}: fout → {fout}")
            continue
        gevonden += 1
        if embeds:
            post(webhook, config.get("afzender", "WoW Mijlpalen"), embeds)
            log(f"{c['naam']}: {len(embeds)} mijlpaal/mijlpalen gepost.")
        state["characters"][sleutel] = nieuw

    if gevonden == 0 and config.get("namespace", "auto") == "auto":
        log(f"Niemand gevonden met namespace {ns}; volgende keer wordt opnieuw gezocht.")
        state.pop("namespace", None)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
