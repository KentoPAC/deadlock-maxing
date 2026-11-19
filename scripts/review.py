"""Critical review of a DeadlockMax build: what a strong player would challenge before it is published.

Three checks, each raising flags the agent answers in the spec ("review": {"<flag>": "why"}) or fixes:
1. Investment thresholds. Every soul spent in a shop column (weapon, vitality, spirit) counts towards a bonus
   (cost_bonuses of the hero asset, the same for every hero): +9 % weapon at 800, +46 % at 4,800, up to +115 % at
   28,800 souls. The 4,800 step is by far the most profitable (the community's "4.8k spike"): good builds reach the
   vitality one early ("Early greens: get that 4.8k") and their main column's one soon after. Flags
   "invest:vitality" and "invest:<main column>" when the lane + core order reaches them late.
2. Good builds. The hero's most favourited builds of the patch: a core item none of them takes (and the best
   one-tricks do not buy either), an item most of them take that the build leaves out, an imbue target that differs
   from theirs. Flags "absent:<id>", "missing:<id>", "imbue:<id>".
3. Win rate at equal souls. A raw item win rate is biased: rich players win more and buy more expensive items. The
   API splits purchases by the buyer's net worth at purchase time (item-stats bucket net_worth_by_5000): an item is
   compared with every purchase made at the same net worth (the hero's purchases in that bucket), weighted by when it
   is bought. Flag "weak:<id>" for a core item clearly below the others bought at the same souls.

Usage: python3 -I review.py <builds/search-hero folder> [spec.json]   (default: the folder's dlmax/spec.json)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get, heroes, items, read_json, write_json  # noqa: E402

COLUMNS = ("weapon", "vitality", "spirit")
STEP = 4800                    # the big investment step of every column
# When the 4.8k steps come (souls spent on items): later than 3 good builds out of 4 of the hero is flagged. Without
# enough good builds, the usual marks (Paradox and Lady Geist builds, 2026-11: vitality 10-14K, main column 7-18K)
VITALITY_BY, MAIN_BY = 13000, 18000
EARLY_CATS = 3                 # a good build's purchase order: its first categories (lane, early, mid)
FAV_MIN, GOOD_MAX = 5, 30      # good builds: at least 5 favourites, the 30 most favourited of the patch
GOOD_MIN = 8                   # fewer good builds than this: too few to judge what they agree on
ABSENT_SHARE, MISSING_SHARE = 0.10, 0.60
WEAK_DELTA, WEAK_MATCHES = -3.0, 300   # points of win rate below the purchases at the same souls
BADGE = 90                     # Phantom+
CACHE_S = 86400


def thresholds(hero_id):
    """{column: [(souls, bonus %)]}: the hero's investment table."""
    bonuses = (heroes().get(hero_id) or {}).get("cost_bonuses") or {}
    return {c: [(b["gold_threshold"], b["bonus"]) for b in bonuses.get(c) or []] for c in COLUMNS}


def bonus(table, invested):
    return max([b for t, b in table if invested >= t] or [0])


def path(spec):
    """The purchase order: the first (lane) category, then the core, left to right."""
    cats = spec.get("categories") or []
    core = next((c for c in cats if c.get("core")), None)
    return [m["id"] for c in ([cats[0]] if cats and cats[0] is not core else []) + ([core] if core else [])
            for m in c.get("mods") or []]


def investments(order, hero_id=None):
    """Walk the purchases: [{id, spent, invested: {column: souls}}]. An upgrade replaces its component (its price
    is paid on top of the component's), so the invested value is what the inventory is worth."""
    all_items = items()
    by_class = {i.get("class_name"): i["id"] for i in all_items.values()}
    owned, spent, steps = [], 0, []
    for iid in order:
        item = all_items.get(iid) or {}
        comps = {by_class.get(c) for c in item.get("component_items") or []}
        replaced = [o for o in owned if o in comps]
        spent += (item.get("cost") or 0) - sum(all_items.get(o, {}).get("cost") or 0 for o in replaced)
        owned = [o for o in owned if o not in replaced] + [iid]
        invested = {c: 0 for c in COLUMNS}
        for o in owned:
            col = all_items.get(o, {}).get("item_slot_type")
            if col in invested:
                invested[col] += all_items[o].get("cost") or 0
        steps.append({"id": iid, "spent": spent, "invested": invested})
    return steps


def reached(steps, column, souls=STEP):
    """(index, step) of the purchase that takes the column to `souls`, or None."""
    return next(((i, s) for i, s in enumerate(steps) if s["invested"][column] >= souls), None)


def main_column(spec):
    all_items = items()
    core = next((c for c in spec.get("categories") or [] if c.get("core")), {})
    total = {c: 0 for c in COLUMNS}
    for m in core.get("mods") or []:
        col = all_items.get(m["id"], {}).get("item_slot_type")
        if col in total:
            total[col] += all_items[m["id"]].get("cost") or 0
    return max(total, key=total.get)


def marks(good):
    """{column: souls}: when 3 good builds out of 4 have reached the column's 4.8k step (None: too few builds)."""
    out = {}
    for col in COLUMNS:
        hits = sorted(h[1]["spent"] for b in good if b.get("order")
                      for h in [reached(investments([i for i in b["order"] if i in items()]), col)] if h)
        out[col] = hits[(3 * len(hits)) // 4] if len(hits) >= GOOD_MIN // 2 else None
    return out


def investment_flags(spec, good=()):
    steps, main = investments(path(spec)), main_column(spec)
    by_good = marks(good)
    flags = {}
    for col, default in (("vitality", VITALITY_BY), (main, MAIN_BY)):
        by = by_good.get(col) or default
        hit = reached(steps, col)
        if not hit or hit[1]["spent"] > by:
            when = f"after {hit[1]['spent']:,} souls of items ({items()[hit[1]['id']]['name']})" if hit else "never"
            ref = "3 good builds out of 4 of this hero" if by_good.get(col) else "good builds"
            flags[f"invest:{col}"] = (f"the {col} 4.8k investment step comes {when}; {ref} reach it within "
                                      f"{by:,} souls (main column: {main})")
    return flags


def _cached(folder, name, fetch):
    path_ = f"{folder}/{name}"
    if os.path.exists(path_) and time.time() - os.path.getmtime(path_) < CACHE_S:
        return read_json(path_)
    data = fetch()
    write_json(path_, data)
    return data


def good_builds(folder, hero_id, since):
    """The hero's most favourited builds of the patch: [{favorites, items: [ids], imbue: {id: ability}}]."""
    def fetch():
        # all-time favourites are missing for some heroes (Violet, 2026-11): the weekly count stands in, as in guides.py
        rows, seen = [], set()
        for sort in ("favorites", "weekly_favorites"):
            for x in get("/v1/builds", hero_id=hero_id, sort_by=sort, only_latest="true", limit=GOOD_MAX * 2,
                         min_unix_timestamp=since):
                if x["hero_build"]["hero_build_id"] not in seen:
                    seen.add(x["hero_build"]["hero_build_id"])
                    rows.append(dict(x, num_favorites=max(x.get("num_favorites") or 0, x.get("num_weekly_favorites") or 0)))
        rows.sort(key=lambda x: -x["num_favorites"])
        out = []
        for x in rows:
            if x["num_favorites"] < FAV_MIN:
                continue
            cats = x["hero_build"]["details"]["mod_categories"]
            mods = [m for c in cats for m in c.get("mods") or []]
            out.append({"favorites": x["num_favorites"], "items": sorted({m["ability_id"] for m in mods}),
                        "order": [m["ability_id"] for c in cats[:EARLY_CATS] for m in c.get("mods") or []],
                        "imbue": {str(m["ability_id"]): m["imbue_target_ability_id"] for m in mods
                                  if m.get("imbue_target_ability_id")}})
        return out[:GOOD_MAX]
    return _cached(folder, "goodbuilds.json", fetch)


def otp_items(folder):
    """Items the best one-tricks buy (their rebuilt builds in the search folder)."""
    out = set()
    for name in os.listdir(folder):
        f = f"{folder}/{name}/build_fr.json"
        if name.startswith("otp-") and os.path.exists(f):
            out |= {m["ability_id"] for c in read_json(f)["details"]["mod_categories"] for m in c.get("mods") or []}
    return out


def build_flags(spec, good, otps, matched=None):
    if len(good) < GOOD_MIN:
        return {}
    all_items = items()
    share = lambda i: sum(1 for b in good if i in b["items"]) / len(good)
    cats = spec.get("categories") or []
    core = {m["id"] for c in cats if c.get("core") for m in c.get("mods") or []}
    every = {m["id"] for c in cats for m in c.get("mods") or []}
    flags = {}
    for i in sorted(core):
        if share(i) < ABSENT_SHARE and i not in otps:
            flags[f"absent:{i}"] = (f"{all_items[i]['name']} is in the core but in {share(i):.0%} of the {len(good)} "
                                    f"good builds and the best one-tricks do not buy it")
    pool = {i for b in good for i in b["items"]}
    for i in sorted(pool - every, key=lambda i: -share(i)):
        item = all_items.get(i) or {}
        if share(i) >= MISSING_SHARE and item.get("type") == "upgrade" and item.get("shopable"):
            seen = (matched or {}).get(i)
            data = (f"; the hero's players bought it in {seen['matches']:,} games, {seen['delta']:+.1f} points at equal "
                    f"souls" if seen else "")
            flags[f"missing:{i}"] = f"{item['name']} is in {share(i):.0%} of the good builds and not in this one{data}"
    for c in cats:
        for m in c.get("mods") or []:
            targets = [b["imbue"][str(m["id"])] for b in good if str(m["id"]) in b["imbue"]]
            if m.get("imbue") and len(targets) >= 3:
                top = max(set(targets), key=targets.count)
                if top != m["imbue"] and targets.count(top) / len(targets) >= 0.6:
                    name = lambda a: all_items.get(a, {}).get("name", a)
                    flags[f"imbue:{m['id']}"] = (f"{all_items[m['id']]['name']} imbues {name(m['imbue'])}; "
                                                 f"{targets.count(top)}/{len(targets)} good builds imbue {name(top)}")
    return flags


def matched_winrates(folder, hero_id, since):
    """{item id: {"delta": points vs the purchases at the same net worth, "matches", "nw": typical net worth at
    purchase}} for the hero (Phantom+ games since `since`)."""
    def fetch():
        return get("/v1/analytics/item-stats", hero_id=hero_id, bucket="net_worth_by_5000", min_average_badge=BADGE,
                   min_unix_timestamp=since)
    rows = _cached(folder, "itemstats_nw.json", fetch)
    base = {}
    for r in rows:
        w, m = base.get(r["bucket"], (0, 0))
        base[r["bucket"]] = (w + r["wins"], m + r["matches"])
    out = {}
    for r in rows:
        w, m = base[r["bucket"]]
        o = out.setdefault(r["item_id"], {"excess": 0.0, "matches": 0, "nw": 0.0})
        o["excess"] += r["wins"] - r["matches"] * w / m
        o["matches"] += r["matches"]
        o["nw"] += r["matches"] * (r["bucket"] + 2500)
    return {i: {"delta": round(100 * o["excess"] / o["matches"], 1), "matches": o["matches"],
                "nw": int(o["nw"] / o["matches"])} for i, o in out.items() if o["matches"]}


def weak_flags(spec, matched):
    all_items = items()
    core = [m["id"] for c in spec.get("categories") or [] if c.get("core") for m in c.get("mods") or []]
    return {f"weak:{i}": (f"{all_items[i]['name']}: {matched[i]['delta']:+.1f} points of win rate against the "
                          f"purchases made at the same souls (~{matched[i]['nw']:,}, {matched[i]['matches']} games)")
            for i in core if i in matched and matched[i]["matches"] >= WEAK_MATCHES
            and matched[i]["delta"] <= WEAK_DELTA}


def flags(folder, spec, hero_id, since):
    """Every point to answer in spec["review"] (or fix): {flag: why it is raised}. Data errors (API down) skip
    the checks that need the API."""
    try:
        good = good_builds(folder, hero_id, since)
    except Exception as e:  # noqa: BLE001
        good = []
        print(f"(good builds unavailable: {e})", file=sys.stderr)
    try:
        matched = matched_winrates(folder, hero_id, since)
    except Exception as e:  # noqa: BLE001
        matched = {}
        print(f"(win rates at equal souls unavailable: {e})", file=sys.stderr)
    out = investment_flags(spec, good)
    out.update(build_flags(spec, good, otp_items(folder), matched))
    out.update(weak_flags(spec, matched))
    return out


def unanswered(spec, raised):
    answers = spec.get("review") or {}
    return {f: why for f, why in raised.items() if len((answers.get(f) or "").strip()) < 20}


def thresholds_line(spec, hero_id, lang):
    """In-game line, generated by code: with which item of the build each 4.8k step is reached."""
    steps = investments(path(spec))
    names = items(lang)
    col_name = {"fr": {"weapon": "Arme", "vitality": "Vitalité", "spirit": "Esprit"},
                "en": {"weapon": "Weapon", "vitality": "Vitality", "spirit": "Spirit"}}[lang]
    parts = []
    for col in COLUMNS:
        hit = reached(steps, col)
        if hit:
            name = (names.get(hit[1]["id"]) or {}).get("name", "?")
            parts.append((hit[0], f"{col_name[col]} avec {name}" if lang == "fr" else f"{col_name[col]} with {name}"))
    if not parts:
        return ""
    head = {"fr": "▸ Spike 4.8k (bonus du shop à 4 800 âmes par colonne) : ",
            "en": "▸ 4.8k spike (shop bonus at 4,800 souls per column): "}[lang]
    return head + " · ".join(p for _, p in sorted(parts))


def report(folder, spec, hero_id, since):
    """Text report: the investment walk, the good builds' view, win rates at equal souls, the flags."""
    all_items = items()
    lines = ["Investment (lane + core, souls spent on items → invested per column):"]
    for s in investments(path(spec)):
        inv = " ".join(f"{c[0].upper()}{s['invested'][c]:>6,}" for c in COLUMNS)
        lines.append(f"  {s['spent']:>6,}  {inv}  {all_items[s['id']]['name']}")
    try:
        matched = matched_winrates(folder, hero_id, since)
        every = [m["id"] for c in spec.get("categories") or [] for m in c.get("mods") or []]
        lines.append("Win rate at equal souls (points vs the hero's purchases at the same net worth; raw win rates "
                     "favour expensive items):")
        for i in every:
            if i in matched:
                d = matched[i]
                lines.append(f"  {d['delta']:+5.1f}  ~{d['nw']:>6,} souls  {d['matches']:>6} games  {all_items[i]['name']}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"(win rates at equal souls unavailable: {e})")
    raised = flags(folder, spec, hero_id, since)
    todo = unanswered(spec, raised)
    lines.append(f"Flags: {len(raised)}, unanswered: {len(todo)}")
    lines += [f"  {f}: {why}" + ("" if f in todo else "  [answered]") for f, why in raised.items()]
    return "\n".join(lines)


if __name__ == "__main__":
    folder = sys.argv[1].rstrip("/")
    spec = read_json(sys.argv[2] if len(sys.argv) > 2 else f"{folder}/dlmax/spec.json")
    data = read_json(f"{folder}/candidates.json")
    print(report(folder, spec, data["hero"]["id"], data.get("since")))
