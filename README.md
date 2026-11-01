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
