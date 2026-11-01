# WoW Feed Bot

Post automatisch in Discord:
- nieuw **WoW Forever**-nieuws van Wowhead
- nieuwe **Forever**-video's van het officiële World of Warcraft YouTube-kanaal

Draait via GitHub Actions elke ~10 minuten (`.github/workflows/bot.yml`).
De Discord-webhook staat als geheim in *Settings → Secrets and variables → Actions* onder de naam `DISCORD_WEBHOOK`.
Instellingen (filters, bronnen) staan in `config.json`. `gezien.json` houdt bij wat al gepost is.
