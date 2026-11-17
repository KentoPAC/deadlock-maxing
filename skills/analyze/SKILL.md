---
name: analyze
description: Analyse Deadlock matches with DeadlockMax - one match from its id or a "MATCH <id>" screenshot (souls per phase vs the lane opponents, creeps, deaths with killer and respawn time, purchase timings, comparison with the hero's top players), or a player's recent games on a hero compared with the same mode, ranked and Oracle+ players (lane, farm speed, soul sources, fights, damage, healing). Use when the user gives a match id, a match screenshot, or asks how they played, what to improve, or to compare their games.
---

# DeadlockMax: match analysis

The user's account: see the project memory (deadlock-match-analysis). Answer in the user's language, with full
official item and ability names (**deadlockmax:knowledge**).

## One match

- `GET https://api.deadlock-api.com/v1/matches/<id>/metadata` (names: `/v1/assets/heroes|items?language=french`).
- Not cached yet -> 404: call `/v1/matches/<id>/salts`, then retry. These uncached fetches are limited to
  **3 requests per hour per IP** (plus 503 "Steam is busy"): one attempt, then wait; never loop.
- Recent matches are also in the data lake (see **deadlockmax:stats**), without that limit, once ingested.
- Useful: souls per 3-5 min slice vs the lane opponents, creeps / possible creeps, deaths (minute, killer, respawn
  time), items with purchase minute, `heal_prevented`; compare with the hero's one-tricks and Oracle+ players.

## A player's recent games on a hero

1. Match ids: `GET /v1/players/<account>/match-history` (mode, hero, result). `match_mode` 1 = Unranked, 4 = Ranked.
2. Rows: data lake files of the partitions `match_id / 1e6` of those matches (+ residual files), filtered on
   `match_id IN (...)`, only the needed columns, all 12 players (lane, team and lobby context). Some recent matches
   are not ingested yet: say how many were found.
3. Same metrics with the same code for the player and for references of the same hero: **same mode** (the real
   reference), Ranked, Ranked Oracle+ (top level). Metrics: lane kills minus deaths per 10 min, souls ahead of the
   lane opponent at lane end, lane creep share, net worth at 10/15/20/25 min, minute to reach 15K / 25K, post-lane
   deaths per 10 min, kill participation, damage per minute, souls per minute, self / ally healing, soul sources.
   Stream the reference matches one by one (loading 100 000 matches at once runs out of memory).
4. Report each gap with its standard error: with 10-20 games only big gaps are real. Turn the gaps into concrete
   advice tied to the hero's measured spike (e.g. strong lane but few objective souls -> convert the lead on towers
   during the early spike).
