# WoW Feed Bot

Post automatisch in Discord:
- nieuw **WoW Forever**-nieuws van Wowhead
- nieuwe **Forever**-video's van het officiële World of Warcraft YouTube-kanaal

Draait via GitHub Actions elke ~10 minuten (`.github/workflows/bot.yml`).
De Discord-webhook staat als geheim in *Settings → Secrets and variables → Actions* onder de naam `DISCORD_WEBHOOK`.
Instellingen (filters, bronnen) staan in `config.json`. `gezien.json` houdt bij wat al gepost is.

## Twitch Live Status

Houdt in Discord één statusbericht bij met welke streamers live zijn (elke ~5 minuten bijgewerkt, `.github/workflows/twitch.yml`).
- Streamers aanpassen: bewerk `streamers.json` (Twitch-namen zoals in twitch.tv/**naam**).
- Geheimen: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `DISCORD_WEBHOOK_LIVE`.
- Statusbericht kwijt of verwijderd? Dan plaatst de bot vanzelf een nieuw.

## WoW Mijlpalen

Post in Discord als een van jullie characters een mijlpaal haalt: **level-ups**, **nieuwe gear** (vanaf blauw/rare) en **nieuwe mounts** (als de Blizzard API die voor Forever teruggeeft). Draait elke ~20 minuten (`.github/workflows/mijlpalen.yml`).
- Characters aanpassen: bewerk `mijlpalen.json` — per persoon `speler` (hoe hij heet in de groep) en `naam` (exacte character-naam, zonder spaties). `realm` mag leeg blijven: dan zoekt de bot zelf op welke realm het character staat en onthoudt dat.
- Gear-drempel: `min_kwaliteit` = `UNCOMMON`, `RARE`, `EPIC` of `LEGENDARY`.
- Geheimen: `BLIZZARD_CLIENT_ID`, `BLIZZARD_CLIENT_SECRET` (van develop.battle.net) en `DISCORD_WEBHOOK_MIJLPALEN` (zonder die laatste post hij in het nieuwskanaal).
- De eerste keer onthoudt de bot alleen de stand en post hij niets.
- Blizzard werkt gegevens meestal pas bij nadat je **uitlogt**, dus een melding kan even op zich laten wachten.
- `namespace` staat op `auto`: de bot probeert zelf de juiste WoW Forever-namespace te vinden. `mijlpalen_status.json` onthoudt de stand.
