---
name: hero-page
description: Build or update a Deadlock hero page with DeadlockMax - the best builds (high-ranked one-tricks, Mobalytics, community, creator videos), how to play it (lane, phases, abilities, power spikes, measured play style) and how to counter it (matchups, counter items), in French and English with codes to paste in game. Use when the user asks for a hero's builds, how to play or counter a hero, to redo / update a hero page, or opens the "all heroes" page.
---

# DeadlockMax: hero pages

`P` = the DeadlockMax plugin folder (`.claude/skills/deadlockmax`). Working folders in the project:
`builds/<id>` for a single build, `builds/search-<hero>` for a search.

Item and ability names, effects and kits: use the **deadlockmax:knowledge** skill. A single build link or code to
translate: **deadlockmax:build-code**. A YouTube video: **deadlockmax:videos**. Measured statistics (spikes, lane,
farm, healing, item effect at equal game state): **deadlockmax:stats**.

Pages exist in **English** (default) and **French**: every text is written in French first (`summaries.json`), then
in English with the same structure (`summaries.en.json`, official English item and ability names). Answer the user in
their language.

Philosophy: statistical builds from ".gg" sites are not trusted (a win rate does not say *why* to buy an item).
The goal is builds from strong players, **with early / mid / late explanations**. The win rate is never a ranking
criterion, only displayed information.

Statistics describe what players do, not what they should do: compare with top players (OTPs, Oracle+), with the
hero's kit and with creators, and flag disagreements.

## A. "Find me the best <hero> builds": 2 calls

**An analysis is only complete with ALL these fields** (report.py prints what is missing: "To complete for an
up-to-date analysis", and the page and home page show "Ancienne analyse" until nothing is missing): `tr` (when there
are texts to translate), `intro`, one `{resume, points}` per build, `tldr` (pick, why, early, mid, late, keys),
`plan` (lane, early, mid, late, tips, role, abilities 1-4, strengths, weaknesses, vs), `sources`, and `en` (all of these
texts in English, same paths). Never finish with something still missing.

**Writing**: full sentences, every item / ability inside a sentence with a verb ("achète Malédiction de
ralentissement pour…"), never "… pour survivre : Malédiction de ralentissement."; always the **full official name**
(not "Dissipateur", "Redingote"): otherwise there is no link and the EN toggle mixes languages. report.py flags
every "Shortened name".

**No filler, no repeats**: the reader plays Deadlock. Every sentence must say something specific to this hero (a
number, a name, a timing, an item, an action); never explain game basics (lanes are played in duos, what the jungle
or souls are, "farm between fights", "do not die"), never write meta phrases ("My explanation:", "It is important
to…") and never present a number that equals the average as a finding ("like the average"). Sections must not repeat
each other: a **weakness** speaks to the hero's player (the flaw and how to make up for it), a **`vs` point** speaks
to the opponent with something concrete (timing, item with its measured gain, matchup) that is not already a
weakness. report.py flags "Filler" (locale `filler_patterns`) and "Repeated idea" (weakness / `vs` pairs sharing
most of their words): fix every one before finishing.

**Every written text cites its sources** (metadata, not displayed yet): in the same finish.py JSON,
`"sources": {"<path>": ["<ref>", …]}` for EVERY text path (`intro`, `<key>.resume`, `<key>.points[i]`,
`tldr.why/early/mid/late/keys[i]`, `plan.early`, `plan.vs[i]`, `plan.abilities.1`…). Refs: `build:<key>`,
`guide:<n>` ([Gn] from guides.py), `video:<id>@<seconds>`, `stat:<module>` (playstyle, baseline, roles, matchups,
counterplay, counters, kit, items, patch), `roles-guide`, `analyse` (my own deduction, always alongside the sources
it rests on). report.py flags every text without a source and every unknown reference.

**Versioned method** (`data/changelog.json`): ANY change to how information is gathered or what is written (even a
small one) adds an entry `{version, date, title, parts, scripts?, auto?, todo}`; `todo` says exactly what to do on an
existing page, and only that. `ANALYSIS_VERSION` = last version. Older pages show "Méthode changée", the list of
changes and a targeted request to copy. When that request comes in: apply only the `todo` of the pending versions
(read changelog.json), without rewriting the rest; finish.py moves a page to the current version only once nothing
is missing.

1. `python3 -I .claude/skills/deadlockmax/scripts/find.py <hero> builds/search-<hero>` (~30 s; options `--days 60 --otp 2 --community 2`).
   Sources: **OTP** (Phantom+ players who mostly play the hero, build rebuilt from their real purchases:
   items in >= 75% of games sorted into early < 10 min / mid < 22 min / late, then situational 25-75%),
   **Mobalytics** (official accounts only), **Community** (popular, >= 150 characters of notes, Oracle+ authors),
   **Vidéo** (`vid-<id>`: builds recommended in a creator's guide video about the hero, see videos.py `guide`;
   `--videos-only` adds them to an existing search without touching the rest).
   Compact output, read it once (do not reopen the JSON files):
   - shortened OTP notes: `98%@4m rev9m` = bought in 98% of games around 4 min, sold around 9 min;
   - texts to translate are numbered `[n]` in the summary and listed once under "To translate";
   - builds already in French get their `code.txt` right away.
2. One call to finish everything (translations + analysis -> codes + page opened):
   ```
   python3 -I .claude/skills/deadlockmax/scripts/finish.py builds/search-<hero> - <<'EOF'
   {"tr": {"<key>": ["fr of [0]", "fr of [1]", …]},
    "intro": "What the builds agree on, the real differences, my advice",
    "<key>": {"resume": "2 sentences", "points": ["Early : …", "Mid : …", "Late : …", "Particularité : …"]},
    "tldr": {…}, "plan": {…}, "sources": {…},
    "en": {"intro": "…", "<key>": {…}, "tldr": {…}, "plan": {…}},
    "tr_en": {"<key>": ["en of [0]", …]},
    "agent_build": {"name": "…", "description": "…", "categories": [{"name": "…", "description": "…",
                    "core": false, "endgame": false, "mods": [{"id": 0, "note": "…"}]}], "abilities": [0, …],
                    "ability_notes": {"<id>": "…"}, "en": {"name": "…", "description": "…",
                    "categories": [{"name": "…", "description": "…", "notes": ["…"]}], "ability_notes": {}}}}
   EOF
   ```
   `tr`: one list per key, **in the exact order** of "To translate" (or a partial `{"n": "fr"}`).
   `en`: the same analysis in English (every path of the French one; sources are shared). Use official English names
   (compare `/v1/assets/items?language=english` with `?language=french`; e.g. Fléau = Affliction, Scopa = Wraith).
   `tr_en`: only for builds listed under "To translate into English" (authors who did not write in English); English
   authors' texts and generated OTP texts are filled in automatically, and finish.py builds the codes in both languages.
   `tldr` (default "L'essentiel" view, readable during a loading screen): `{"pick": "<key of the advised build>",
   "why": "1 sentence", "early": "1-2 sentences", "mid": "…", "late": "…", "keys": ["3 takeaways max"]}`: short and
   concrete, like a good player guide: each phase says first what to DO (where to stand, how to trade in lane, when
   to join fights, which objectives / timers / urns), then the items with their minute.
   `plan` ("Comment le jouer" view): `{"lane": "which lane or map position and why", "early": "…", "mid": "…",
   "late": "…", "tips": ["…"],
   "role": "what the hero must do in fights given its position (initiate, frontline, assassinate, carry…)",
   "abilities": {"1": "how to use ability 1", …, "4": "…"},
   "strengths": ["…"], "weaknesses": ["…"], "vs": ["how to beat it / what to watch out for"],
   "counters": {"<item_id>": "why this counter item"}}` (plan, tldr and sources are merged when sent again).
   The plan **cross-checks** the measured play style (find.py "Measured play style" section: souls/min,
   lane/jungle/fights/objectives share, K/D/A, objective damage vs the Phantom+ average) with the "Community advice"
   [G0]… (guide-like builds and Steam guides newer than the last big patch). Say who says what ("Kiwi",
   "Lowavy's guide", measured numbers), flag contradictions (a pre-patch note vs what players actually do). Check
   every number quoted, and the official French name of every item (e.g. Crippling Headshot = Brise-tête).
   French homonyms: "Fléau" = Pocket's ultimate AND an item (Scourge); "Ténacité" = an item AND an ability.
   Write "l'objet Fléau" for the item (page links give priority to the hero's ability).
   Analysis: only from the data shown; flag inconsistencies. The page computes the "Comparer" view (shared items)
   itself: the intro does not need to list them all.
   **The DeadlockMax build** (`"agent_build"`, candidate key `dlmax`, shown first and advised by default): the real
   builds are kept as references; this one is ours, the best build we can write by crossing everything gathered:
   what the OTPs actually buy and keep (incl. their "Fin de partie : 12 emplacements" category), creators' videos and
   guides, the measured profile (deadlockmax:stats: spike window, items that power it up, lane items, anti-heal,
   farm) and the kit (deadlockmax:knowledge). Format and checks: `scripts/agent_build.py` (refused with the list of
   problems if a rule is broken). Organisation, in this order:
   - **Lane**: the starting items, then the 4 lane items that never upgrade (Restorative Shot, Extra Regen,
     Rebuttal, Golden Goose Egg) reasoned against the kit and the lane opponent: which one if you poke, if you are
     bullied, against melee heroes (lane_items: effect at equal opponent, who they are bought against).
   - **Core** (`"core": true`): the items bought every game, in purchase order, each note saying when (minute or
     souls) and why for THIS hero (which ability or stat it feeds, which spike it prepares).
   - **Endgame proposals** (`"endgame": true`): a few items to finish the inventory, each saying when to pick it
     and what to sell for room. Core + proposals fill the 12 slots (an upgrade takes its component's slot).
   - **Situational**: one category per situation ("Contre les soins", "Contre les tanks", "Si tu es en retard"…),
     each note written "if <situation>, buy <item> around <time>, because <reason>".
   - `abilities`: the point order (the OTPs' most common order unless the kit or a creator says otherwise), with
     `ability_notes` on the unlocks.
   Never justify an item by its win or pick rate (Farmingbip trap): a statistic is a clue to explain with the kit.
   Every note quotes its reason; `sources` can cite `build:dlmax/...` paths like the other texts. Write its
   `{resume, points}` like the other builds and set `tldr.pick` to `dlmax` unless a real build is clearly better.
3. Reply briefly: the candidates, my advice, the page link. No screenshot unless the user reports a display
   issue. Counter items (counters.py) arrive ~2 min later in the background: the page regenerates itself.

## A'. "Redo / update <hero>" (existing page, or "Ancienne analyse" / "Méthode changée" on the home page)

- **Patch released or old data**: rerun `find.py <hero> builds/search-<hero>` in the **same folder** (existing
  translations are kept), then `finish.py` with the full analysis (every field above).
- **Analysis only** (recent data): run `playstyle.py`, `guides.py`, `roles.py`, `matchups.py`, `counterplay.py` on the
  folder (and `counters.py … --report` in the background), read their output, reread `summaries.json`, then
  `finish.py` with the missing fields.
- **"Méthode changée"**: apply only the pending changelog `todo`s (see above).

## C. Details

- **Home page**: `builds/index.html` (`hub.py`, rerun by report.py): every hero, stamps (À jour / À vérifier / Patch
  sorti / Ancienne analyse / Méthode changée), TLDR and "Le contrer" links, a button that copies the request for
  Claude. A new required part = an entry in `data/changelog.json` (+ `NEEDED_*` in `status.py` if needed).
- **Hero page**: `templates/hero.html` (official site look: charcoal, parchment, hero colour) + JSON data injected by
  `report.py`. No item data is hard-coded: names, icons, costs, categories and tooltips come from the API on every
  run (items change with every update). Banner / emblem (`assets/`) are copied to `builds/_assets/`.
  Regenerate a page without refetching: `python3 -I .claude/skills/deadlockmax/scripts/report.py builds/search-<hero>`.
  Hero theme (colour, background, name art, portrait, tags), rank emblems, FR + EN items (FR/EN toggle or `?lang=en`)
  and the patch list are all re-read from the API. The page compares dates with today and with patches itself
  (freshness stamp, ⚠ build older than a big patch, live check for new patches). find.py limits OTP games to the last
  big patch when it is >= 21 days old.
- Code layout: `report.py` (page assembly) uses `tooltips.py` (item / ability tooltips), `textlinks.py` (links in
  texts, shortened-name check) and `status.py` (method version, completeness, sources).
- **Languages**: report.py and hub.py write one page per language: `index.html` (English, default) and
  `index.fr.html`, with an EN | FR switch. Interface strings live in `locales/<lang>.json` (scripts: `i18n.t/table/
  pattern`; templates: `{{ui:key}}` tokens and the `L('key')` helper, keys under `"ui"`); never hard-code interface
  text. Every key must exist in every locale (a test checks it). Written content is tagged: `summaries.json` has
  `"lang": "fr"` (set by finish.py), each video tip has `"lang"`; content missing in a page's language is shown in its
  own language with a notice. Analysis modules store ids (play style tags, metric keys), labelled at render time.
- **playstyle.py** / **guides.py** (run by find.py, can be rerun alone on a search folder): measured style via
  `/v1/analytics/player-performance-curve` (OTPs + authors with >= 10 games on the hero, "small sample" under 20), with
  each phase's lean vs the Phantom+ average (`focus`: lane farm, jungle farm, fights, objectives, >= +15%; shown in
  the TLDR, the build view and the comparison: use it to say how each build is played); advice = in-game builds with
  >= 500 characters of explanation + serious Steam guides updated after the patch.
  Mobalytics (Cloudflare) and Reddit (403) are not reachable: do not try to get around it.
- **roles.py**: game class + meta position (recent Steam "roles / positions" guide, last known guide from the cache
  when Steam answers 429) + hero percentiles (farm, damage taken, damage, assists, kills, deaths, objectives).
- **matchups.py**: matchups (gap to the expected result, often small at high level: say so) and items that beat the
  hero (gain beyond the average gain). Explain *why* from the item description, never guessed.
- **laning.py** (run by find.py): who wins the lane against the hero (duo soul lead at 9 min vs its usual lead,
  /v1/analytics/lane-matchup-stats, Phantom+), with each enemy's general lane strength (a strong laner beats
  everyone: say so), and lane items bought before 9 min that win clearly more against it (gap >= 1.5 pts and
  >= 2 standard errors; when fewer than 4 are, gaps >= 1 pt and >= 1 standard error fill in, flagged "trend"),
  in their own section "Items that beat <hero> in lane". Use it in `plan.lane` and `vs` (source `stat:laning`).
- **counterplay.py**: late-game counterplay by enemy composition (big healers -> anti-heal, tanks -> % HP /
  resistance shred, heavy spirit / gun damage -> resistances, crowd control -> status resistance). Measured hero
  profiles (cached for a day), items classified by their technical properties in the API, filtered on what the
  hero's players buy. Do not rewrite these lists by hand in the analysis: cite them.
  "against" part ("Le contrer" view): hero profile (heals / tanks / spirit / gun) -> most played late items (tier
  III-IV) of the category; matchups.py adds the counter items measured after 20 min.
- **counters.py** (background, started by find.py, regenerates the page): items the OTPs buy clearly more against
  some heroes (statistical test). Steam pages are cached for a day (`~/.cache/deadlock-maxing`).
- Power spikes and ability cards: computed by report.py (game level thresholds x the OTP's ability order).
