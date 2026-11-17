"""Measured profile of every hero, from the local data lake cache (scripts/lake.py).

For each hero, in ranked matches (all ranks) and ranked Oracle+ (top players):
  win rate; laning (kills minus deaths in his lane before its first guardian falls, duo soul lead then);
  post-lane team fights by net worth (+1 enemy death / -1 ally death, at his net worth that second, vs all heroes)
  and the spike window (shape vs his own average); timing by minute at equal game state (team soul lead, his share);
  value of being fed; soul sources by phase; kill participation, healing given, self-healing and when anti-heal is
  worth it; damage to heroes; median net worth by minute (to place Rifts, urns and Patrons);
  key resources found blindly: every measured quantity (permanent ability bonuses, kills, ability kills, soul
  sources, healing...) whose high values win more at equal net worth for this hero than for the other heroes.

Writes  <out>/profiles.json  (everything, for pages and the explorer)
        <out>/profiles.md    (a short sourced summary per hero, for the agent)
Usage:  uv run --extra stats python -I scripts/profiles.py [--db PATH] [--out DIR] [--memory 3GB]
        (default out: skills/knowledge/ref, next to the item and hero references)
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get  # noqa: E402
from lake import DEFAULT_DB, DEFAULT_MEMORY, connect  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), "skills", "knowledge", "ref")
GROUPS = {"ranked": "match_mode = 'Ranked'", "top": "match_mode = 'Ranked' AND average_badge >= 80"}
B = list(range(0, 60001, 2500))                      # net worth buckets (the last one is 60K and more)
TBINS = [(0, 15), (15, 20), (20, 25), (25, 30), (30, 35), (35, 45), (45, 90)]
EVENTS = {"rift": [11, 18, 25, 32, 39, 46], "urn": [10, 15, 20, 25, 30, 35, 40, 45], "boss": [26, 34, 41]}
SOURCES = ["lanes", "jungle", "fights", "objectives", "rift_urn", "other"]
NWB = "least(floor({x} / 2500) * 2500, 60000)::INT"


def q(con, sql, *args):
    return con.execute(sql, list(args)).fetchall()


def setup(con):
    con.execute("""CREATE OR REPLACE TEMP MACRO nw_at(ts, nw, t) AS (CASE
        WHEN t <= ts[1] THEN nw[1] * t / ts[1] WHEN t >= ts[len(ts)] THEN nw[len(nw)]
        ELSE nw[len(list_filter(ts, lambda x: x <= t))] + (nw[len(list_filter(ts, lambda x: x <= t)) + 1]
             - nw[len(list_filter(ts, lambda x: x <= t))]) * (t - ts[len(list_filter(ts, lambda x: x <= t))])
             / (ts[len(list_filter(ts, lambda x: x <= t)) + 1] - ts[len(list_filter(ts, lambda x: x <= t))]) END)""")


# ----------------------------------------------------------------------------------------------- measurements

def win_rates(con, g):
    return {h: {"games": n, "wr": round(w, 4)} for h, n, w in
            q(con, f"SELECT hero_id, count(*), avg(won::INT) FROM ply WHERE {g} GROUP BY 1")}


def laning(con, g):
    rows = q(con, f"""WITH p AS (SELECT * FROM ply WHERE {g}),
      dd AS (SELECT p.match_id, p.player_slot, count(*) FILTER (WHERE d.vteam <> p.team) lk, count(*) FILTER (WHERE d.vteam = p.team) ld
             FROM p LEFT JOIN deaths d ON d.match_id = p.match_id AND d.vlane = p.assigned_lane AND d.t < p.t_end GROUP BY 1, 2),
      nw AS (SELECT match_id, player_slot, team, assigned_lane, t_end, nw_at(time_stamp_s, net_worth, t_end) me FROM p),
      duo AS (SELECT a.match_id, a.player_slot, sum(CASE WHEN b.team = a.team THEN b.me ELSE -b.me END) souls
              FROM nw a JOIN nw b ON b.match_id = a.match_id AND b.assigned_lane = a.assigned_lane GROUP BY 1, 2)
      SELECT p.hero_id, count(*), sum(dd.lk - dd.ld) / sum(p.t_end / 600.0), avg(duo.souls), avg(p.t_end) / 60
      FROM p JOIN dd USING (match_id, player_slot) JOIN duo USING (match_id, player_slot) GROUP BY 1""")
    return {h: {"n": n, "kd10": round(kd, 3), "duo_souls": round(s), "end_min": round(te, 1)} for h, n, kd, s, te in rows}


def post_lane_fights(con, g):
    """{hero: (minutes per bucket, signed deaths per bucket)} + the same for all heroes."""
    ev = q(con, f"""SELECT p.hero_id, {NWB.format(x='nw_at(p.time_stamp_s, p.net_worth, d.t)')} b,
                           sum(CASE WHEN d.vteam <> p.team THEN 1 ELSE -1 END)
                    FROM (SELECT * FROM ply WHERE {g}) p JOIN deaths d ON d.match_id = p.match_id AND d.t >= p.t_end GROUP BY 1, 2""")
    ex = q(con, f"""SELECT hero_id, {NWB.format(x='nw_at(time_stamp_s, net_worth, s + 15)')} b, count(*) / 2.0
                    FROM (SELECT *, unnest(range(t_end::INT, t_last::INT, 30)) s FROM ply WHERE {g}) GROUP BY 1, 2""")
    return ev, ex


def equal_state(con, g):
    """Signed deaths and minutes per (hero, minute bin, team lead bin, share bin): timing and fed value.

    A "moment" is either a death after the player's laning (weight +1 / -1) or a 30 s step of his post-lane play
    (exposure). Each is placed in a cell by the minute, his team's soul lead and his share of his team's souls."""
    tb = "CASE " + " ".join(f"WHEN t < {hi * 60} THEN {i}" for i, (_, hi) in enumerate(TBINS)) + " END"
    gb = ("CASE WHEN mine < 0.9 * theirs THEN 0 WHEN mine < 0.97 * theirs THEN 1 WHEN mine < 1.03 * theirs THEN 2 "
          "WHEN mine < 1.1 * theirs THEN 3 ELSE 4 END")
    sb = "CASE WHEN me < 0.9 * mine THEN 0 WHEN me < 1.1 * mine THEN 1 ELSE 2 END"

    def cells(moments, value):
        return q(con, f"""WITH p AS (SELECT * FROM ply WHERE {g}), m AS ({moments}),
            s AS (SELECT m.hero_id, m.t, m.sgn, nw_at(m.time_stamp_s, m.net_worth, m.t) me,
                         nw_at(a.lts, a.lnw, m.t) mine, nw_at(b.lts, b.lnw, m.t) theirs
                  FROM m JOIN teamnw a ON a.match_id = m.match_id AND a.team = m.team
                         JOIN teamnw b ON b.match_id = m.match_id AND b.team <> m.team)
            SELECT hero_id, {tb}, {gb}, {sb}, {value} FROM s WHERE mine > 0 AND theirs > 0 GROUP BY ALL""")

    deaths_after_lane = """SELECT p.*, d.t, CASE WHEN d.vteam <> p.team THEN 1 ELSE -1 END sgn
                           FROM p JOIN deaths d ON d.match_id = p.match_id AND d.t >= p.t_end"""
    play_after_lane = "SELECT *, s + 15 t, 0 sgn FROM (SELECT *, unnest(range(t_end::INT, t_last::INT, 30)) s FROM p)"
    return cells(deaths_after_lane, "sum(sgn)"), cells(play_after_lane, "count(*) / 2.0")


def intervals(con, g):
    """Post-lane snapshot intervals per hero and net worth bucket: damage, kill participation, healing."""
    return q(con, f"""WITH i AS (
        SELECT p.match_id, p.team, p.hero_id, k, time_stamp_s[k+1] - time_stamp_s[k] dur, net_worth[k] nw0,
               player_damage[k+1] - player_damage[k] dmg, (kills[k+1] - kills[k]) + (assists[k+1] - assists[k]) ka,
               (teammate_healing[k+1] - teammate_healing[k]) + (teammate_barriering[k+1] - teammate_barriering[k]) ally,
               self_healing[k+1] - self_healing[k] self, kills[k+1] - kills[k] kk
        FROM (SELECT *, unnest(range(1, len(time_stamp_s))) k FROM ply WHERE {g}) p
        WHERE time_stamp_s[k+1] > time_stamp_s[k] AND time_stamp_s[k] >= t_end),
      t AS (SELECT match_id, team, k, sum(kk) tk FROM i GROUP BY ALL)
      SELECT i.hero_id, {NWB.format(x='i.nw0')} b, count(*), sum(dur) / 60.0, sum(dmg), sum(ka), sum(tk), sum(ally), sum(self)
      FROM i JOIN t USING (match_id, team, k) GROUP BY 1, 2""")


def farm(con, g):
    cols = {"lanes": "gold_lane_creep[k+1]+gold_lane_creep_orbs[k+1]-gold_lane_creep[k]-gold_lane_creep_orbs[k]",
            "jungle": "gold_neutral_creep[k+1]+gold_neutral_creep_orbs[k+1]-gold_neutral_creep[k]-gold_neutral_creep_orbs[k]",
            "fights": "gold_player[k+1]+gold_source_assists_gold[k+1]-gold_player[k]-gold_source_assists_gold[k]",
            "objectives": "gold_boss[k+1]+gold_source_team_bonus_gold[k+1]-gold_boss[k]-gold_source_team_bonus_gold[k]",
            "rift_urn": "gold_treasure[k+1]-gold_treasure[k]",
            "other": "gold_source_breakable_gold[k+1]-gold_source_breakable_gold[k]"}
    ph = ("CASE WHEN time_stamp_s[k] < t_end THEN 0 WHEN time_stamp_s[k] < 1200 THEN 1 "
          "WHEN time_stamp_s[k] < 1800 THEN 2 ELSE 3 END")
    sums = ", ".join(f"sum({c})" for c in cols.values())
    return q(con, f"""SELECT hero_id, {ph} ph, sum(time_stamp_s[k+1] - time_stamp_s[k]) / 60.0, {sums}
        FROM (SELECT *, unnest(range(1, len(time_stamp_s))) k FROM ply WHERE {g})
        WHERE time_stamp_s[k+1] > time_stamp_s[k] GROUP BY 1, 2""")


def nw_by_minute(con, g):
    minutes = sorted({m for v in EVENTS.values() for m in v} | {5, 10, 15, 20, 25, 30, 35, 40, 45, 50})
    rows = q(con, f"""SELECT hero_id, m, quantile_cont(nw_at(time_stamp_s, net_worth, m * 60), [0.25, 0.5, 0.75])
        FROM (SELECT *, unnest(?::INT[]) m FROM ply WHERE {g}) WHERE t_last >= m * 60 GROUP BY 1, 2""", minutes)
    out = {}
    for h, m, v in rows:
        out.setdefault(h, {})[m] = [round(x) for x in v]
    return out


def key_resources(con, g):
    """Blind scan: for each hero and each measured quantity, the win-rate gap between games where it is above vs below
    its median, at equal net worth (5K buckets, 30-40 min games), compared with the same gap for the other heroes
    (or, for a hero's own permanent ability bonus, with that hero's kill gap)."""
    # [-1] = end-of-match value of a stats series; shares are relative to the final net worth
    nw = "greatest(final_net_worth, 1)"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE kr AS SELECT hero_id h, won::INT w, final_net_worth // 5000 b, ability_stats,
        final_kills::DOUBLE kills, final_deaths::DOUBLE deaths, final_assists::DOUBLE assists,
        ability_kills[-1]::DOUBLE / greatest(final_kills, 1) ability_kill_share,
        (gold_neutral_creep[-1] + gold_neutral_creep_orbs[-1])::DOUBLE / {nw} jungle_share,
        (gold_player[-1] + gold_source_assists_gold[-1])::DOUBLE / {nw} fight_share,
        (gold_boss[-1] + gold_source_team_bonus_gold[-1])::DOUBLE / {nw} objective_share,
        (teammate_healing[-1] + teammate_barriering[-1])::DOUBLE ally_healing, self_healing[-1]::DOUBLE self_healing,
        boss_damage[-1]::DOUBLE objective_damage, player_damage[-1]::DOUBLE hero_damage,
        player_damage_taken[-1]::DOUBLE damage_taken
        FROM ply WHERE {g} AND duration_s BETWEEN 1800 AND 2400""")
    features = ["kills", "deaths", "assists", "ability_kill_share", "jungle_share", "fight_share", "objective_share",
                "ally_healing", "self_healing", "objective_damage", "hero_damage", "damage_taken"]

    def gaps(table, value, key="0"):
        return q(con, f"""WITH y AS (SELECT h, {key} k, b, w, {value} > median({value}) OVER (PARTITION BY h, {key}, b) hi,
                                            count(*) OVER (PARTITION BY h, {key}, b) n FROM {table})
            SELECT h, k, sum(gp * nn) / sum(nn), sum(nn) FROM (
              SELECT h, k, b, avg(w) FILTER (WHERE hi) - avg(w) FILTER (WHERE NOT hi) gp, count(*) nn
              FROM y WHERE n >= 150 GROUP BY 1, 2, 3)
            WHERE gp IS NOT NULL GROUP BY 1, 2""")
    typical = {}
    for f in features:
        for h, med in q(con, f"SELECT h, median({f}) FROM kr GROUP BY 1"):
            typical[(h, f)] = med
    out = {}
    for f in features:
        for h, _, gp, n in gaps("kr", f):
            if typical.get((h, f)):   # a quantity the hero barely produces (median 0) says nothing about him
                out.setdefault(h, {})[f] = (gp, n)
    con.execute("""CREATE OR REPLACE TEMP TABLE kv AS
        SELECT h, w, b, unnest(map_keys(ability_stats)) k, unnest(map_values(ability_stats))::DOUBLE v FROM kr""")
    bonus = {}
    for h, k, gp, n in gaps("kv", "v", "k"):
        bonus.setdefault(h, {})[k] = (gp, n)
    return out, bonus


# ---------------------------------------------------------------------------------------------- shaping (Python)

def smooth(raw, weights, width):
    out = []
    for i, v in enumerate(raw):
        if v is None:
            out.append(None)
            continue
        win = [(raw[j], weights[j]) for j in range(i - width, i + width + 1) if 0 <= j < len(raw) and raw[j] is not None]
        out.append(round(sum(a * b for a, b in win) / sum(b for _, b in win), 3))
    return out


def spike_window(curve, minutes, min_minutes):
    """Where the curve is furthest above the hero's own average: buckets >= 60 % of the peak (peak >= +0.15)."""
    ok = [i for i, v in enumerate(curve) if v is not None and minutes[i] >= min_minutes and i < len(curve) - 1]
    if len(ok) < 4:
        return None
    mean = sum(curve[i] for i in ok) / len(ok)
    d = {i: curve[i] - mean for i in ok}
    pk = max(ok, key=d.get)
    if d[pk] < 0.15:
        return {"flat": True}
    lo = hi = pk
    while lo - 1 in d and d[lo - 1] >= 0.6 * d[pk]:
        lo -= 1
    while hi + 1 in d and d[hi + 1] >= 0.6 * d[pk]:
        hi += 1
    return {"from": B[lo], "to": B[hi] + 2500, "peak": B[pk], "gain": round(d[pk], 2)}


def minute_at(nwq, nw):
    pts = [(0, 0)] + sorted((m, v[1]) for m, v in nwq.items())
    for (a, x), (b, y) in zip(pts, pts[1:]):
        if x <= nw <= y and y > x:
            return round(a + (b - a) * (nw - x) / (y - x), 1)
    return None


def build(db, out_dir, memory=DEFAULT_MEMORY):
    t0 = time.time()
    con = connect(db, read_only=True, memory=memory)
    setup(con)
    meta = dict(zip(["partitions", "files", "first_match", "last_match", "matches", "built"], q(con, "SELECT * FROM meta")[0]))
    heroes_fr = {h["id"]: h for h in get("/v1/assets/heroes", language="french")}
    heroes_en = {h["id"]: h["name"] for h in get("/v1/assets/heroes")}
    abilities = {i["id"]: i for i in get("/v1/assets/items", language="french") if i.get("type") == "ability"}
    profiles = {}
    for gname, g in GROUPS.items():
        print(f"[{gname}] win rates, laning…", flush=True)
        wr, lane = win_rates(con, g), laning(con, g)
        print(f"[{gname}] post-lane fights…", flush=True)
        ev, ex = post_lane_fights(con, g)
        print(f"[{gname}] equal game state…", flush=True)
        sev, sex = equal_state(con, g)
        print(f"[{gname}] intervals, farm, net worth by minute…", flush=True)
        iv, fm, nwm = intervals(con, g), farm(con, g), nw_by_minute(con, g)
        print(f"[{gname}] key resources…", flush=True)
        kr, bonus = key_resources(con, g)

        sig, mins = {}, {}
        for h, b, s in ev:
            sig[(h, b)] = sig.get((h, b), 0) + s
            sig[("ALL", b)] = sig.get(("ALL", b), 0) + s
        for h, b, m in ex:
            mins[(h, b)] = mins.get((h, b), 0) + m
            mins[("ALL", b)] = mins.get(("ALL", b), 0) + m
        cell_s, cell_m = {}, {}
        for h, *c, s in sev:
            for k in ((h, *c), ("ALL", *c)):
                cell_s[k] = cell_s.get(k, 0) + s
        for h, *c, m in sex:
            for k in ((h, *c), ("ALL", *c)):
                cell_m[k] = cell_m.get(k, 0) + m
        rate = lambda k: cell_s.get(k, 0) / cell_m[k] * 10 if cell_m.get(k) else None
        ivd = {}
        for h, b, n, m, dmg, ka, tk, ally, self_ in iv:
            for k in ((h, b), ("ALL", b)):
                a = ivd.setdefault(k, [0, 0, 0, 0, 0, 0, 0])
                for j, x in enumerate((n, m, dmg, ka, tk, ally, self_)):
                    a[j] += x
        fmd = {}
        for h, ph, m, *v in fm:
            for k in ((h, ph), ("ALL", ph)):
                a = fmd.setdefault(k, [0] * 7)
                a[0] += m
                for j, x in enumerate(v):
                    a[j + 1] += x
        kill_gaps = [v["kills"][0] for v in kr.values() if "kills" in v]
        all_features = {f for v in kr.values() for f in v}
        medians = {f: statistics.median(v[f][0] for v in kr.values() if f in v) for f in all_features}
        min_minutes = 5000 if gname == "ranked" else 1000

        for h in wr:
            if h not in heroes_fr:
                continue
            p = profiles.setdefault(h, {"id": h, "fr": heroes_fr[h]["name"], "en": heroes_en.get(h, heroes_fr[h]["name"])})
            fights = [None if mins.get((h, b), 0) < min_minutes / 3 or b < 5000 else
                      sig.get((h, b), 0) / mins[(h, b)] * 10 - sig.get(("ALL", b), 0) / mins[("ALL", b)] * 10 for b in B]
            fights = smooth(fights, [mins.get((h, b), 0) for b in B], 2)
            m_curve = [round(mins.get((h, b), 0)) for b in B]
            timing, fed = [], []
            for tb in range(len(TBINS)):
                num = den = 0
                for gb in range(5):
                    for sb in range(3):
                        m = cell_m.get((h, tb, gb, sb), 0)
                        if m >= 30:
                            num += m * (cell_s.get((h, tb, gb, sb), 0) / m * 10 - rate(("ALL", tb, gb, sb)))
                            den += m
                timing.append(round(num / den, 3) if den > min_minutes / 3 else None)
            for tbs in ((0, 1), (2, 3), (4, 5, 6)):
                num = den = 0
                for tb in tbs:
                    for gb in range(5):
                        f, n_ = cell_m.get((h, tb, gb, 2), 0), cell_m.get((h, tb, gb, 1), 0)
                        if f >= 60 and n_ >= 60:
                            w = min(f, n_)
                            mine = rate((h, tb, gb, 2)) - rate((h, tb, gb, 1))
                            usual = rate(("ALL", tb, gb, 2)) - rate(("ALL", tb, gb, 1))
                            num += w * (mine - usual)
                            den += w
                fed.append(round(num / den, 3) if den > min_minutes / 6 else None)

            def per_bucket(fn):
                vals = [None if ivd.get((h, b), [0])[0] < 150 or b < 5000 else fn(ivd[(h, b)], ivd[("ALL", b)]) for b in B]
                return smooth(vals, [ivd.get((h, b), [0])[0] for b in B], 1)
            dmg = per_bucket(lambda a, al: (a[2] / a[1]) / (al[2] / al[1]))
            kp = per_bucket(lambda a, al: (a[3] / max(a[4], 1)) / (al[3] / max(al[4], 1)))
            ally = per_bucket(lambda a, al: a[5] / a[1] - al[5] / al[1])
            self_heal = per_bucket(lambda a, al: a[6] / a[1])
            self_avg = [None if ivd.get(("ALL", b), [0])[0] == 0 else round(ivd[("ALL", b)][6] / ivd[("ALL", b)][1]) for b in B]
            antiheal = next(({"from": B[i], "hp_min": round(v), "ratio": round(v / self_avg[i], 1)}
                             for i, v in enumerate(self_heal) if v and self_avg[i] and v >= 600 and v >= 1.5 * self_avg[i]), None)
            farm_out = []
            for ph in range(4):
                a, al = fmd.get((h, ph)), fmd.get(("ALL", ph))
                farm_out.append(None if not a or a[0] < 300 else
                                {"per_min": round(sum(a[1:]) / a[0]), "avg_per_min": round(sum(al[1:]) / al[0]),
                                 "share": {s: round(a[j + 1] / max(sum(a[1:]), 1) * 100, 1) for j, s in enumerate(SOURCES)},
                                 "avg_share": {s: round(al[j + 1] / max(sum(al[1:]), 1) * 100, 1) for j, s in enumerate(SOURCES)}})
            res = []
            for f, (gp, n) in kr.get(h, {}).items():
                res.append({"what": f, "gap": round(gp * 100, 1), "usual": round(medians[f] * 100, 1),
                            "excess": round((gp - medians[f]) * 100, 1), "n": n})
            hero_kill_gap = kr.get(h, {}).get("kills", (statistics.median(kill_gaps), 0))[0]
            for k, (gp, n) in bonus.get(h, {}).items():
                ab = abilities.get(k)
                if ab and n >= 1500:   # the hero's own ability (items are bought by anyone)
                    res.append({"what": "bonus", "ability": ab["name"], "ability_id": k, "gap": round(gp * 100, 1),
                                "usual": round(hero_kill_gap * 100, 1), "excess": round((gp - hero_kill_gap) * 100, 1), "n": n})
            for r_ in res:
                r_["z"] = round(r_["excess"] / (100 / r_["n"] ** 0.5), 1)   # standard error of a half-vs-half gap ~ 1/sqrt(n)
            res.sort(key=lambda r: -abs(r["z"]))
            spike = spike_window(fights, m_curve, min_minutes)
            nwq = nwm.get(h, {})
            if spike and not spike.get("flat"):
                spike["min_from"], spike["min_to"] = minute_at(nwq, spike["from"]), minute_at(nwq, spike["to"])
            p[gname] = {"wr": wr[h], "lane": lane.get(h), "fights": fights, "fight_minutes": m_curve, "spike": spike,
                        "timing": timing, "fed": fed, "damage": dmg, "kill_participation": kp, "ally_healing": ally,
                        "self_healing": self_heal, "self_healing_avg": self_avg, "antiheal": antiheal, "farm": farm_out,
                        "nw_by_minute": nwq, "key_resources": res}
    con.close()
    os.makedirs(out_dir, exist_ok=True)
    doc = {"meta": meta | {"generated": time.strftime("%Y-%m-%d")}, "buckets": B, "time_bins": TBINS, "events": EVENTS,
           "groups": list(GROUPS), "heroes": sorted(profiles.values(), key=lambda p: p["fr"])}
    with open(os.path.join(out_dir, "profiles.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "profiles.md"), "w", encoding="utf-8") as fh:
        fh.write(summary(doc))
    print(f"{len(profiles)} heroes -> {out_dir} ({time.time() - t0:.0f} s)")


# ------------------------------------------------------------------------------------------------ text summary

LABEL = {"kills": "ses kills", "deaths": "ses morts", "assists": "ses assists",
         "ability_kill_share": "sa part de kills faits avec une capacité",
         "jungle_share": "sa part d'âmes venant de la jungle", "fight_share": "sa part d'âmes venant des kills et assists",
         "objective_share": "sa part d'âmes venant des objectifs", "ally_healing": "les soins qu'il donne aux alliés",
         "self_healing": "les soins qu'il se donne", "objective_damage": "ses dégâts aux objectifs", "hero_damage": "ses dégâts aux héros",
         "damage_taken": "les dégâts qu'il encaisse"}


def fmt(x, nd=2):
    return ("+" if x >= 0 else "−") + f"{abs(x):.{nd}f}".replace(".", ",")


def fr(x, nd=1):
    return f"{x:.{nd}f}".replace(".", ",")


def k(nw):
    return fr(nw / 1000, 1).replace(",0", "") + "K"


def summary(doc):
    m = doc["meta"]
    lines = ["# Profil mesuré de chaque héros", "",
             f"Parties classées du {m['first_match']} au {m['last_match']} (data lake deadlock-api, généré le {m['generated']}). "
             "« Tous » = toutes les parties classées, « Oracle+ » = parties classées de rang moyen Oracle et plus (référence haut niveau).",
             "Ce sont des mesures de ce que font les joueurs, pas des consignes : à croiser avec le kit (heroes.md) et les créateurs. "
             "Les « ressources clés » sont trouvées à l'aveugle (écart de victoire à net worth égal, comparé aux autres héros) : "
             "l'agent doit les expliquer à partir de la description des capacités.", ""]
    for p in doc["heroes"]:
        r, t = p.get("ranked"), p.get("top")
        if not r:
            continue
        lines.append(f"## {p['fr']} ({p['en']})")
        wr = r["wr"]
        top = f", {fr(t['wr']['wr'] * 100)} % en Oracle+ ({t['wr']['games']} parties)" if t else ""
        lines.append(f"- Victoires : {fr(wr['wr'] * 100)} % sur {wr['games']} parties{top}.")
        ln = r["lane"]
        if ln:
            kd = ln["kd10"]
            verdict = "gagne souvent sa lane" if kd >= 0.2 else "perd souvent sa lane" if kd <= -0.2 else "fait jeu égal en lane"
            lines.append(f"- Lane : {verdict} ({fmt(kd)} kill pour 10 min, {fmt(ln['duo_souls'], 0)} âmes pour le duo "
                         f"à la fin de la lane, vers {fr(ln['end_min'])} min).")
        sp = r["spike"]
        if sp and not sp.get("flat"):
            known = sp.get("min_from") is not None and sp.get("min_to") is not None
            when = f", vers {fr(sp['min_from'], 0)} à {fr(sp['min_to'], 0)} min" if known else ""
            tsp = t and t.get("spike")
            tt = f" ; Oracle+ : {k(tsp['from'])} à {k(tsp['to'])}" if tsp and not tsp.get("flat") else ""
            lines.append(f"- Spike (combats d'équipe après la lane) : {k(sp['from'])} à {k(sp['to'])}{when}{tt}.")
        elif sp:
            lines.append("- Spike : pas de pic net, impact à peu près constant.")
        tm = [v for v in r["timing"] if v is not None]
        if tm:
            best = max(range(len(r["timing"])), key=lambda i: r["timing"][i] if r["timing"][i] is not None else -9)
            lo, hi = doc["time_bins"][best]
            lines.append(f"- À état de partie égal, au mieux entre {lo} et {hi} min "
                         f"({fmt(r['timing'][best])} combat pour 10 min vs les autres héros).")
        fed = r["fed"]
        if any(v is not None for v in fed):
            ph = ["avant 20 min", "20-30 min", "après 30 min"]
            lines.append("- Être fed (110 % des âmes de ses alliés), vs un héros moyen : " +
                         ", ".join(f"{ph[i]} {fmt(v)}" for i, v in enumerate(fed) if v is not None) + ".")
        f1 = r["farm"][1]
        if f1:
            gaps = sorted(((f1["share"][s] - f1["avg_share"][s], s) for s in SOURCES[:5]), key=lambda x: -abs(x[0]))
            names = {"lanes": "lanes", "jungle": "jungle", "fights": "kills et assists", "objectives": "objectifs",
                     "rift_urn": "Rift et urne"}
            g = [f"{names[s]} {f1['share'][s]:.0f} % (moy. {f1['avg_share'][s]:.0f} %)" for d, s in gaps if abs(d) >= 2.5][:2]
            extra = ", " + ", ".join(g) if g else ""
            lines.append(f"- Farm de la fin de lane à 20 min : {f1['per_min']} âmes/min (moy. {f1['avg_per_min']}){extra}.")
        ah = r["antiheal"]
        if ah:
            lines.append(f"- Anti-soin contre lui à partir de ~{k(ah['from'])} : il se soigne de {ah['hp_min']} PV/min, "
                         f"{fr(ah['ratio'])} fois la moyenne.")
        keys = [x for x in r["key_resources"] if abs(x["z"]) >= 2.5 and abs(x["excess"]) >= 3][:3]
        if keys:
            txt = []
            for x in keys:
                what = f"le bonus permanent de {x['ability']}" if x["what"] == "bonus" else LABEL.get(x["what"], x["what"])
                ref = "ses kills" if x["what"] == "bonus" else "les autres héros"
                txt.append(f"{what} ({fmt(x['gap'], 1)} pts de victoire quand il est haut, contre {fmt(x['usual'], 1)} pour {ref})")
            lines.append("- Ressources clés trouvées à l'aveugle (parties de 30-40 min, à net worth égal) : " + " ; ".join(txt) + ".")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--memory", default=DEFAULT_MEMORY, help="DuckDB memory cap (default 3GB, env DEADLOCKMAX_MEMORY)")
    a = ap.parse_args()
    sys.exit(build(a.db, a.out, a.memory))
