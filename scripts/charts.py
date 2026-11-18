"""Text charts of a hero's measured profile (profiles.json): readable in a terminal and by the agent in profiles.md.

Usage: python3 -I charts.py <hero> [--top]      the hero's charts (--top: Oracle+ games instead of all ranked games)

Charts (no DuckDB needed, they only read profiles.json):
  power   team fights after the lane by net worth, compared with other heroes at the same net worth, with the
          spike window and the objectives (Rift, Mid-Boss) placed at the hero's median net worth at their minute
  timing  impact by game minute, at an equal game state
  fed     what a soul lead is worth for this hero compared with an average hero
  farm    where the souls come from, by phase, against the average hero
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "..", "skills", "knowledge", "ref", "profiles.json")
FIRST, LAST = 2, 24          # buckets drawn: 5K to 60K souls (2,500 souls each)
ROWS = 4                     # rows above and below the zero line


def k(v, lang="fr"):
    s = f"{v / 1000:.0f}K" if v % 1000 == 0 else f"{v / 1000:.1f}K"
    return s.replace(".", ",") if lang == "fr" else s


def num(v, d=2):
    return ("+" if v >= 0 else "−") + f"{abs(v):.{d}f}".replace(".", ",")


def minute_at(nwq, nw):
    pts = [(0, 0)] + sorted((int(m), q[1]) for m, q in (nwq or {}).items())
    for (m0, v0), (m1, v1) in zip(pts, pts[1:]):
        if v0 < nw <= v1:
            return m0 + (m1 - m0) * (nw - v0) / (v1 - v0)
    return None


def power(g, buckets, events, name):
    """Columns of team fights per bucket of net worth, zero = other heroes at the same net worth."""
    vals = g["fights"][FIRST:LAST + 1]
    top = max([abs(v) for v in vals if v is not None] + [0.2])
    step = top / ROWS
    sp = g.get("spike") or {}
    nwq = g.get("nw_by_minute") or {}
    lane_nw = None
    if g.get("lane"):
        mins = sorted((int(m), q[1]) for m, q in nwq.items())
        end = g["lane"]["end_min"]
        for (m0, v0), (m1, v1) in zip([(0, 0)] + mins, mins):
            if m0 <= end <= m1:
                lane_nw = v0 + (v1 - v0) * (end - m0) / (m1 - m0)
    cols = list(range(FIRST, LAST + 1))
    out = [f"{name} — combats d'équipe après la lane (kills − morts pour 10 min), écart aux autres héros au même net worth",
           "▲ au-dessus : son équipe gagne plus de combats que la moyenne · ▼ en dessous : elle en perd plus"]

    def cell(i, row):
        v = g["fights"][i]
        if v is None:
            return "  "
        thr = (abs(row) - 0.5) * step
        return "██" if (row > 0 and v >= thr) or (row < 0 and v <= -thr) else "  "
    for row in list(range(ROWS, 0, -1)) + [0] + list(range(-1, -ROWS - 1, -1)):
        if row == 0:
            line = "".join("──" for _ in cols)
            out.append(f"{'0':>7} ┤{line}  autres héros")
            continue
        label = num(row * step) if abs(row) in (ROWS, 2) else ""
        out.append(f"{label:>7} │" + "".join(cell(i, row) for i in cols))
    band = "".join("▔▔" if sp.get("from") and sp["from"] <= buckets[i] < sp["to"] else "  " for i in cols)
    if sp.get("from"):
        out.append(f"{'SPIKE':>7}  {band}")
    obj = [" "] * (len(cols) * 2)
    for key, mark in (("rift", "R"), ("boss", "B")):
        for mn in events.get(key, []):
            q = nwq.get(str(mn)) or nwq.get(mn)
            if q:
                pos = int((q[1] - buckets[FIRST]) / 2500 * 2)
                if 0 <= pos < len(obj):
                    obj[pos] = mark
    if lane_nw is not None:
        pos = max(0, int((lane_nw - buckets[FIRST]) / 2500 * 2))
        if pos < len(obj) and obj[pos] == " ":
            obj[pos] = "L"
    out.append(f"{'repères':>9}" + "".join(obj).rstrip()
               + "   (L = fin de lane, R = Rift, B = Patron, placés à son net worth médian à cette minute)")
    axis, mins = [" "] * (len(cols) * 2 + 4), [" "] * (len(cols) * 2 + 4)
    for nw in range(10000, 60001, 10000):
        pos = int((nw - buckets[FIRST]) / 2500 * 2)
        for j, ch in enumerate(k(nw)):
            axis[pos + j] = ch
        mm = minute_at(nwq, nw)
        if mm is not None:
            for j, ch in enumerate(f"{mm:.0f}'"):
                mins[pos + j] = ch
    out.append(f"{'âmes':>9}" + "".join(axis).rstrip() + "   (la courbe commence à 5K : la lane n'est pas comptée)")
    out.append(f"{'≈ min':>9}" + "".join(mins).rstrip())
    if sp.get("from"):
        out.append(f"Spike : {k(sp['from'])} à {k(sp['to'])}" + (f", vers {sp['min_from']:.0f} à {sp['min_to']:.0f} min"
                                                                if sp.get("min_from") is not None else "")
                   + " (comparé à sa propre moyenne : un spike peut être sous zéro).")
    return out


def bar(v, scale, width=12):
    """Horizontal diverging bar: ▏ = zero, filled to the right if positive, to the left if negative."""
    n = min(width, round(abs(v) / scale * width)) if scale else 0
    left = " " * (width - n) + "█" * n if v < 0 else " " * width
    right = "█" * n if v >= 0 else ""
    return f"{left}│{right:<{width}}"


def timing(g, bins):
    vals = g["timing"]
    scale = max([abs(v) for v in vals if v is not None] + [0.2])
    out = ["Selon la minute, à état de partie égal (même avance d'âmes de l'équipe) : écart aux autres héros, /10 min"]
    for (a, b), v in zip(bins, vals):
        label = f"{a}'+" if b > 60 else f"{a}-{b}'"
        out.append(f"{label:>8} " + (bar(v, scale) + f" {num(v)}" if v is not None else "   (pas assez de parties)"))
    return out


def fed(g):
    vals, names = g.get("fed") or [], ["avant 20'", "20-30'", "après 30'"]
    if not any(v is not None for v in vals):
        return []
    scale = max([abs(v) for v in vals if v is not None] + [0.15])
    out = ["Être fed (110 % des âmes de ses alliés) : ce que ça lui rapporte de plus qu'à un héros moyen, /10 min"]
    for n, v in zip(names, vals):
        out.append(f"{n:>9} " + (bar(v, scale) + f" {num(v)}" if v is not None else "   (pas assez de parties)"))
    return out


SOURCE = (("lanes", "L", "lane"), ("jungle", "J", "jungle"), ("fights", "K", "kills/assists"), ("objectives", "O", "objectifs"))


def farm(g):
    phases = ["Lane", "Fin lane-20'", "20-30'", "Après 30'"]
    out = ["D'où viennent ses âmes (L = lane, J = jungle, K = kills et assists, O = objectifs), lui puis la moyenne"]

    def stacked(share, width=40):
        s = "".join(letter * round((share.get(key) or 0) / 100 * width) for key, letter, _ in SOURCE)
        return f"{s[:width]:<{width}}"
    for name, f in zip(phases, g.get("farm") or []):
        if not f:
            continue
        out.append(f"{name:>12} lui  {stacked(f['share'])} {f['per_min']} âmes/min")
        out.append(f"{'':>12} moy. {stacked(f['avg_share'])} {f['avg_per_min']} âmes/min")
    return out


INGAME = {
    "fr": {"title": "Quand il est fort", "head": "Son impact sur les combats selon ses âmes (■ = plus fort), mesuré après la lane :",
           "strong": "◆ FORT", "window": "Fort entre {a} et {b} âmes (vers {ma} à {mb} min)", "obj": " : force {list}.",
           "rift": "le Rift de {m}'", "boss": "le Patron de {m}'", "and": " et ",
           "flat": "Pas de pic net : son impact reste à peu près le même toute la partie."},
    "en": {"title": "When it is strong", "head": "Its impact on fights by souls (■ = stronger), measured after the lane:",
           "strong": "◆ STRONG", "window": "Strong between {a} and {b} souls (around minute {ma} to {mb})", "obj": ": force {list}.",
           "rift": "the {m}' Rift", "boss": "the {m}' Mid-Boss", "and": " and ",
           "flat": "No clear peak: its impact stays about the same all game."},
}


def ingame_power(doc, p, lang="fr", group="ranked"):
    """The power line as in-game text (category description): one line per 5,000 souls with a bar of ■, the only
    kind of chart the game's font can draw (proportional font, no block characters; verified 2026-11-18).
    Bars are relative to the hero's own range: the longest line is where it weighs most on fights."""
    g, T = p.get(group), INGAME[lang]
    if not g:
        return None
    buckets, fights, nwq, sp = doc["buckets"], g["fights"], g.get("nw_by_minute") or {}, g.get("spike") or {}
    rows = []
    for nw in range(10000, 50001, 5000):
        vals = [fights[i] for i in range(len(buckets)) if nw - 2500 <= buckets[i] < nw + 2500 and fights[i] is not None]
        if vals:
            rows.append((nw, sum(vals) / len(vals)))
    if len(rows) < 3:
        return None
    lo, hi = min(v for _, v in rows), max(v for _, v in rows)
    lines = [T["head"]]
    for nw, v in rows:
        n = 1 + round((v - lo) / (hi - lo) * 9) if hi > lo else 5
        mm = minute_at(nwq, nw)
        strong = sp.get("from") and sp["from"] <= nw < sp["to"] + 2500
        when = f" ≈{mm:.0f}'" if mm is not None else ""
        lines.append(f"{k(nw, lang)}{when} {'■' * n}" + (f" {T['strong']}" if strong else ""))
    if sp.get("from") and not sp.get("flat"):
        txt = T["window"].format(a=k(sp["from"], lang), b=k(sp["to"], lang),
                                 ma=f"{sp.get('min_from') or 0:.0f}", mb=f"{sp.get('min_to') or 0:.0f}")
        objs = [T[key].format(m=mn) for key in ("rift", "boss") for mn in doc["events"].get(key, [])
                if sp.get("min_from") is not None and sp["min_from"] <= mn <= sp["min_to"]]
        lines.append(txt + (T["obj"].format(list=T["and"].join(objs)) if objs else "."))
    else:
        lines.append(T["flat"])
    return {"name": T["title"], "description": "\n".join(lines)}


def hero_charts(doc, p, group="ranked"):
    g = p.get(group)
    if not g:
        return []
    name = f"{p['fr']} ({'Oracle+' if group == 'top' else 'tous les rangs'})"
    blocks = [power(g, doc["buckets"], doc["events"], name), timing(g, doc["time_bins"]), fed(g), farm(g)]
    return [line for b in blocks if b for line in b + [""]]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    with open(PROFILES, encoding="utf-8") as f:
        doc = json.load(f)
    q = args[0].lower()
    p = next((h for h in doc["heroes"] if q in (h["fr"].lower(), h["en"].lower(), str(h["id"]))), None) \
        or next((h for h in doc["heroes"] if q in h["fr"].lower() or q in h["en"].lower()), None)
    if not p:
        sys.exit(f"Hero not found in profiles.json: {args[0]}")
    print("\n".join(hero_charts(doc, p, "top" if "--top" in sys.argv else "ranked")))


if __name__ == "__main__":
    main()
