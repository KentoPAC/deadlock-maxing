---
name: stats
description: Measure how Deadlock heroes really play from match data with DeadlockMax - lane strength, power spike window by net worth and by minute at equal game state, value of being fed, team fights, objectives, kill participation, healing given and self-healing (when to buy anti-heal), soul sources (lane / jungle / fights / objectives), win rate, and the real effect of an item at equal game state. Use when a hero page or an answer needs numbers on how a hero plays or when it is strong, when the user asks about power spikes, "when should X fight", farm patterns, anti-heal timing, or wants to explore the statistics.
---

# DeadlockMax: measured statistics

Statistics describe what players **do**, not what they **should** do. Always compare with top players (Oracle+ and
the hero's one-tricks), cross-check with the hero's kit (**deadlockmax:knowledge**) and with creators
(**deadlockmax:videos**), and flag disagreements. Give the sample size; a gap smaller than its error is noise.

## Data

- **Data lake** (no rate limit, full match details): `https://data.deadlock-api.com/v1/manifest.json` lists the
  parquet files of `match_player` (one row per player and match: `stats.*` snapshots every 3 min until 15 min then
  every 5 min, `death_details.*` with exact times, `items.*` with purchase times, `objectives.*`, `mid_boss.*`).
  Partition = `match_id / 1e6`; the highest partition holds the latest matches. Query it with DuckDB from Python:
  `uv venv` + `uv pip install duckdb pytz`, `LOAD httpfs`, `read_parquet([...urls])`, select only the needed columns
  (`SELECT *` runs out of memory), `SET threads=6; SET preserve_insertion_order=false` for big extracts.
- `/v1/sql` on the API is deprecated and times out after 45 s: do not use it for these aggregates.
- Ranked (`match_mode='Ranked'`, `average_badge` = tier*10+subrank, 80 = Oracle) and Unranked matches are both there.

## Definitions (validated 2026-11-17, keep them)

- **End of laning** for a player: first Tier 1 guardian of **his** lane destroyed (either side). Objective lanes map
  to `assigned_lane`: Tier1Lane1 -> 1, Tier1Lane3 -> 4, Tier1Lane4 -> 6. Median 9 min.
- **Lane strength**: enemy deaths in his lane minus his duo's deaths before that end, per 10 min of lane; duo soul
  lead at that moment.
- **Team fights (post-lane)**: every death of the match after his lane end, +1 enemy / -1 ally, placed at the hero's
  net worth at that second, per 10 min of post-lane play, minus the average of all heroes at the same net worth.
- **Equal game state**: compare a hero with the others in the same cell of (minute bin, his team's soul lead over
  the enemy team: <-10 %, -10/-3, ±3, +3/+10, >+10 %, his share of his team's souls: <90 %, 90-110 %, >110 %).
  Never condition on the hero's lead over the lobby alone (a farming carry at the lobby average often means his
  team is behind).
- **Spike** = where the post-lane team-fight curve is furthest above the hero's **own** average (shape, not level:
  the level mixes timing with how strong the hero is this patch, so always show the win rate next to it).
  Window = buckets >= 60 % of the peak, peak >= +0.15, buckets with enough minutes only, last capped bucket excluded.
- **Fed** = share > 110 % of his allies' average, compared with the same hero at 90-110 % in the same cell, minus the
  same gap over all heroes.
- **Unstable Rift and urn** are not in the data by name: `stats.gold_treasure` = Rift bounty split equally in the
  winning team (1482 + 222/min after 13 min, / 6; Rifts ~11 min then every ~7 min) + urn souls to the courier only
  (250 + 70/min, 50/50 with an ally who picks an orb; urns at 10 min then every 5 min). The hero barely changes the
  Rift win rate (±3 pts): use them as time markers, converted to net worth with the hero's median (and its 25-75 %
  range).
- **Healing**: `teammate_healing + teammate_barriering` = given to allies; `self_healing` = on himself (player
  healing = self + allies exactly). Anti-heal worth it from the first net worth where self-healing >= 1.5x the
  average and >= 600 HP/min.
- **Soul sources**: lanes = lane creeps + orbs, jungle = neutral creeps + orbs, fights = kills + assists, objectives
  = boss + team bonus, Rift and urn = treasure, other = breakables + items; sums match net worth within ~4 %. Lanes
  dominate for everyone (~35 %): read the gap to the average, not the raw share.
- **Items**: never rank by raw win rate (hero base win rate, "win-more" purchases, long-game survivorship). Compare
  buyers with non-buyers of the same hero at the same minute and team lead, or the hero's impact just before vs
  just after the purchase; explain the effect from the item description.

## Status

The profile pipeline (DuckDB cache + one profile per hero, summary for heroes.md, explorer page) is being moved into
`.claude/skills/deadlockmax/scripts/`. Until it is there, the 2026-11-17 prototype lives in the session scratchpad: rebuild with
these definitions rather than inventing new ones.
