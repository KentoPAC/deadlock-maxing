"""Local cache of recent Deadlock matches from the public deadlock-api data lake (DuckDB).

Downloads only the needed columns of the latest complete partition(s) of `match_player` (one row per player and match,
with stats snapshots every 3 min until 15 min then every 5 min, exact death times, objectives) and builds the derived
tables the statistics use (laning end per player, deaths, team net worth over time).

Needs the optional `stats` dependencies (DuckDB, pinned in uv.lock): from the plugin folder,
    uv run --extra stats python -I scripts/lake.py [--partitions 1] [--db PATH] [--memory 3GB]
DuckDB is capped at 3 GB of RAM and 4 threads by default (it spills to ~/.cache/deadlockmax/duckdb_tmp).

Tables in the database (default ~/.cache/deadlockmax/lake.duckdb):
  mp        one row per player and match (ranked, + unranked with --unranked; normal mode): stats.* series under their own
            names (net_worth, kills...), end-of-match values as final_net_worth, final_kills...
  (mp.items = shop purchases: [{id, t, sold}], times in seconds, sold 0 when kept)
  ply       mp + t_end (end of his laning phase: first Tier 1 guardian of his lane, either side)
  deaths    one row per death: match, victim team, victim lane, time
  teamnw    per match and team: snapshot times and average net worth of the team
  meta      source files, partitions, match dates
"""
import argparse
import json
import os
import sys
import time
import urllib.request

MANIFEST = "https://data.deadlock-api.com/v1/manifest.json"
PUBLIC = "https://data.deadlock-api.com/"
CACHE = os.path.expanduser("~/.cache/deadlockmax")
DEFAULT_DB = os.path.join(CACHE, "lake.duckdb")
# DuckDB takes up to 80 % of the RAM by default: cap it and let big joins spill to disk instead.
DEFAULT_MEMORY = os.environ.get("DEADLOCKMAX_MEMORY", "3GB")
DEFAULT_THREADS = int(os.environ.get("DEADLOCKMAX_THREADS", "4"))
MIN_FILES = 40  # a partition with fewer base files is still filling up
# objective lanes -> assigned_lane (verified: correlation with the lane soul lead at 9 min)
LANE_OBJ = {"Tier1Lane1": 1, "Tier1Lane3": 4, "Tier1Lane4": 6}
STATS = ["time_stamp_s", "net_worth", "player_damage", "player_damage_taken", "kills", "deaths", "assists",
         "ability_kills", "bullet_kills", "teammate_healing", "teammate_barriering", "self_healing", "boss_damage",
         "creep_kills", "possible_creeps", "gold_lane_creep", "gold_lane_creep_orbs", "gold_neutral_creep",
         "gold_neutral_creep_orbs", "gold_player", "gold_source_assists_gold", "gold_boss",
         "gold_source_team_bonus_gold", "gold_treasure", "gold_source_breakable_gold"]
COLUMNS = ["match_id", "start_time", "duration_s", "match_mode", "average_badge", "account_id", "team", "player_slot",
           "assigned_lane", "hero_id", "won", "net_worth final_net_worth", "kills final_kills", "deaths final_deaths",
           "assists final_assists", "ability_stats",
           '"death_details.game_time_s"', '"objectives.destroyed_time_s"', '"objectives.team_objective"',
           '"objectives.team"', '"mid_boss.destroyed_time_s"', '"mid_boss.team_killed"']
ASSETS = "https://api.deadlock-api.com/v1/assets/items/by-type/upgrade"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "deadlockmax/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def manifest():
    return fetch(MANIFEST)


def shop_items():
    """Ids of the items sold in the shop (the purchase list also holds every ability point)."""
    return sorted(i["id"] for i in fetch(ASSETS) if i.get("shopable"))


def latest_files(n_partitions):
    """URLs of the base files of the n most recent complete partitions."""
    files = manifest()["tables"]["match_player"]["files"]
    by_part = {}
    for f in files:
        if f.get("kind") == "base":
            by_part.setdefault(f["partition"], []).append(f)
    complete = sorted(p for p, fs in by_part.items() if len(fs) >= MIN_FILES)[-n_partitions:]
    return complete, [PUBLIC + f["key"] for p in complete for f in by_part[p]]


def connect(db_path, read_only=False, memory=DEFAULT_MEMORY, threads=DEFAULT_THREADS):
    """DuckDB connection with a memory cap, a thread cap and a spill folder (big joins go to disk, not RAM)."""
    import duckdb  # optional dependency (extra "stats")

    spill = os.path.join(CACHE, "duckdb_tmp")
    os.makedirs(spill, exist_ok=True)
    con = duckdb.connect(db_path, read_only=read_only)
    con.execute(f"SET memory_limit = '{memory}'; SET threads = {threads}; SET temp_directory = '{spill}'; "
                "SET preserve_insertion_order = false")
    return con


def build(db_path, n_partitions, memory=DEFAULT_MEMORY, unranked=False):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    for old in (db_path, db_path + ".wal"):  # start from a new file: DuckDB never shrinks one
        if os.path.exists(old):
            os.remove(old)
    parts, urls = latest_files(n_partitions)
    print(f"Partitions {parts}: {len(urls)} files")
    con = connect(db_path, memory=memory)
    con.execute("INSTALL httpfs; LOAD httpfs")
    src = "read_parquet([" + ",".join(f"'{u}'" for u in urls) + "])"
    modes = "'Ranked', 'Unranked'" if unranked else "'Ranked'"
    shop = "[" + ",".join(map(str, shop_items())) + "]"
    # purchases of shop items only: [{id, t (bought, s), sold (s, 0 = kept)}]
    items = (f'[{{"id": z[1], "t": z[2], "sold": z[3]}} for z in list_zip("items.item_id", "items.game_time_s", '
             f'"items.sold_time_s") if list_contains({shop}, z[1])] items')
    cols = ", ".join(COLUMNS + [items] + [f'"stats.{s}"::BIGINT[] "{s}"' for s in STATS])
    t = time.time()
    con.execute(f"""CREATE OR REPLACE TABLE mp AS SELECT {cols} FROM {src}
        WHERE game_mode = 'Normal' AND match_mode IN ({modes}) AND len("stats.time_stamp_s") > 2""")
    print(f"mp: {con.execute('SELECT count(*), count(DISTINCT match_id) FROM mp').fetchone()} ({time.time() - t:.0f} s)")
    cases = " ".join(f"WHEN '{k}' THEN {v}" for k, v in LANE_OBJ.items())
    con.execute(f"""CREATE OR REPLACE TABLE lane_end AS SELECT match_id, CASE o {cases} END lane, min(t)::BIGINT t_end
        FROM (SELECT DISTINCT match_id, unnest("objectives.destroyed_time_s") t, unnest("objectives.team_objective") o FROM mp)
        WHERE o IN ({','.join(f"'{k}'" for k in LANE_OBJ)}) GROUP BY 1, 2""")
    con.execute("""CREATE OR REPLACE TABLE ply AS SELECT mp.*, coalesce(le.t_end, time_stamp_s[len(time_stamp_s)]) t_end,
        time_stamp_s[len(time_stamp_s)] t_last FROM mp LEFT JOIN lane_end le ON le.match_id = mp.match_id AND le.lane = mp.assigned_lane""")
    con.execute("""CREATE OR REPLACE TABLE deaths AS
        SELECT match_id, team vteam, assigned_lane vlane, unnest("death_details.game_time_s")::BIGINT t FROM mp""")
    con.execute("""CREATE OR REPLACE TABLE teamnw AS SELECT match_id, team, list(ts ORDER BY i) lts, list(anw ORDER BY i) lnw FROM (
        SELECT match_id, team, i, min(time_stamp_s[i]) ts, avg(net_worth[i])::BIGINT anw
        FROM (SELECT match_id, team, time_stamp_s, net_worth, unnest(range(1, len(time_stamp_s) + 1)) i FROM mp)
        GROUP BY 1, 2, 3 HAVING count(*) >= 5) GROUP BY 1, 2""")
    span = con.execute("SELECT min(start_time)::VARCHAR, max(start_time)::VARCHAR, count(DISTINCT match_id) FROM mp").fetchone()
    con.execute("CREATE OR REPLACE TABLE meta AS SELECT ? partitions, ? files, ? first_match, ? last_match, ? matches, ? built",
                [json.dumps(parts), len(urls), span[0][:10], span[1][:10], span[2], time.strftime("%Y-%m-%d")])
    print(f"Matches {span[0][:10]} -> {span[1][:10]}: {span[2]} ({time.time() - t:.0f} s) -> {db_path}")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--partitions", type=int, default=1)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--memory", default=DEFAULT_MEMORY, help="DuckDB memory cap (default 3GB, env DEADLOCKMAX_MEMORY)")
    ap.add_argument("--unranked", action="store_true", help="also keep unranked matches (player comparisons; ~6x bigger)")
    a = ap.parse_args()
    sys.exit(build(a.db, a.partitions, a.memory, a.unranked))
