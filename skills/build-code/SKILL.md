---
name: build-code
description: Translate, encode and import a single Deadlock build with DeadlockMax - a deadchaps.gg / build link or id, or a build code pasted from the game ("Copier dans le presse-papier"), turned into a French or English build and a code to paste in game via "Coller le build" / "Paste build". Use when the user gives a build link or id to translate, pastes a build code, or has trouble pasting a build in game.
---

# DeadlockMax: build codes

Deadlock imports a build from the clipboard (**"Coller le build"** / "Paste build" button in the build editor).
Format: `base64(zstd(protobuf CMsgHeroBuild))`, without a trailing newline (the game rejects it otherwise).
This format has been verified in game.

`P` = the DeadlockMax plugin folder (`.claude/skills/deadlockmax`). Working folders in the project:
`builds/<id>` for a single build, `builds/search-<hero>` for a search.

## B. Translate one build (link or id)

1. `python3 -I .claude/skills/deadlockmax/scripts/fetch.py <url_or_id> builds/<id>`: compact summary + numbered "To translate" list.
2. `python3 -I .claude/skills/deadlockmax/scripts/apply.py builds/<id> --fr - <<'EOF'` + JSON list of translations in order + `EOF`:
   writes `build_fr.json`, `code.txt` and **copies the code**.
3. Tell the user: in game, the hero's builds -> **"Coller le build"**. Summarise in a few lines.
   To copy it again later: `wl-copy -n < builds/<id>/code.txt`.

## Details

- **apply.py** `--lang fr|en` writes `build_<lang>.json` and the code (`code.txt` in French, `code.en.txt` in English);
  `--tr -` fills that language's translations. It recomputes category width / height from the text length (the game cuts text with "..."); constants at
  the top of the file, `--keep-layout` keeps the original. It mirrors an in-game copy, with author account id 0: the game
  requires the field to show "Coller le build" but accepts any value, so codes contain nothing personal.
- **Translation**: official French names of items and abilities (the summary already gives them). Nicknames
  ("Cultist" = Sacrifice rituel, "E-Shift" = Refuge céleste…): compare `api.deadlock-api.com/v1/assets/items?language=<lang>`
  with `?language=french`. Natural French gamer tone (lane, farm, focus… are fine). `#Citadel_HeroBuilds_*` labels are
  not translated. End the description translation with "Traduit du build <id>.".

## Troubleshooting

- Pasting fails: ask the user to copy any build in game ("Copier dans le presse-papier"), then
  `python3 -I .claude/skills/deadlockmax/scripts/codec.py --decode "$(wl-paste -n)"` and compare.
- Reference protobuf: `CMsgHeroBuild` in
  `https://raw.githubusercontent.com/SteamDatabase/GameTracking-Deadlock/master/Protobufs/citadel_gcmessages_common.proto`.
- Game limit: 16,000 raw bytes per build (checked by apply.py).
- `assets.deadlock-api.com` may not answer: use `api.deadlock-api.com/v1/assets/...`.
- Useful endpoints: `/v1/analytics/scoreboards/players` (OTPs), `/v1/analytics/item-stats` and
  `/v1/analytics/ability-order-stats` (filterable by `account_id`), `/v1/builds` (`search_name`, `author_id`,
  `sort_by`), `/v1/players/rank`. Full schema: `https://api.deadlock-api.com/openapi.json`.
- Python 3.14+ required (built-in `compression.zstd`).
