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
    "fr": {"title": "Power spike", "role_title": "Rôle et lane",
           "head": "Impact sur les teamfights selon ses âmes (■ = plus fort), mesuré après la lane :",
           "spike": "◆ SPIKE", "window": "Power spike entre {a} et {b} âmes (≈{ma}-{mb} min), en {phase}",
           "obj": " : joue {list}.", "rift": "le Rift de {m}'", "boss": "le Patron de {m}'", "and": " et ",
           "phase": {"early": "early game", "mid": "mid game", "late": "late game"},
           "flat": "Pas de vrai power spike : son impact reste à peu près le même toute la partie.",
           "lane": {"win": "Lane : forte, souvent gagnée ({kd} kill / 10 min, {souls} âmes pour le duo).",
                    "win_bit": "Lane : un peu favorable ({kd} kill / 10 min, {souls} âmes pour le duo).",
                    "lose": "Lane : faible, souvent perdue ({kd} kill / 10 min, {souls} âmes pour le duo) : joue safe.",
                    "lose_bit": "Lane : un peu défavorable ({kd} kill / 10 min, {souls} âmes pour le duo) : évite les échanges longs.",
                    "even": "Lane : neutre, ni forte ni faible ({kd} kill / 10 min, {souls} âmes pour le duo)."}},
    "en": {"title": "Power spike", "role_title": "Role and lane",
           "head": "Impact on teamfights by souls (■ = stronger), measured after the lane:",
           "spike": "◆ SPIKE", "window": "Power spike between {a} and {b} souls (≈{ma}-{mb} min), {phase}",
           "obj": ": play {list}.", "rift": "the {m}' Rift", "boss": "the {m}' Mid-Boss", "and": " and ",
           "phase": {"early": "early game", "mid": "mid game", "late": "late game"},
           "flat": "No real power spike: its impact stays about the same all game.",
           "lane": {"win": "Lane: strong, often won ({kd} kills / 10 min, {souls} souls for the duo).",
                    "win_bit": "Lane: slightly favourable ({kd} kills / 10 min, {souls} souls for the duo).",
                    "lose": "Lane: weak, often lost ({kd} kills / 10 min, {souls} souls for the duo): play safe.",
                    "lose_bit": "Lane: slightly unfavourable ({kd} kills / 10 min, {souls} souls for the duo): avoid long trades.",
                    "even": "Lane: neutral, neither strong nor weak ({kd} kills / 10 min, {souls} souls for the duo)."}},
}


# The hero's role (community positions guide, roles.json) and the game plan that follows from the measured lane and
# power spike: generated by code, one tone for every hero.
ROLE = {
    "fr": {1: "hard carry (position 1). Il te faut un maximum d'âmes : farme en priorité (lanes, jungle) et ne force "
              "pas les combats avant tes objets clés, c'est toi qui gagnes la fin de partie.",
           2: "soft carry (position 2). Beaucoup d'âmes aussi, mais ton pic arrive plus tôt : dès tes premiers objets "
              "clés, va chercher les kills, les combats et les objectifs.",
           3: "frontline (position 3). Farm moyen : tu engages les combats en premier et tu encaisses pour ton équipe.",
           4: "roamer (position 4). Peu de farm : quitte ta lane pour les ganks et les picks, et farme en te déplaçant.",
           5: "soft support (position 5). Tu fais des dégâts, mais ton vrai travail est de faire gagner tes carries "
              "(contrôles, contre-achats sur le carry adverse).",
           6: "hard support (position 6). Peu de farm : soigne, protège et sauve tes carries.",
           "head": "Rôle : {roles}", "or": " Ou ",
           "plan": {("lose", "early"): "Plan de jeu : survis à la lane, ton moment arrive juste après. Force les combats "
                                       "pendant ton power spike.",
                    ("lose", "mid"): "Plan de jeu : survis en lane, farme, puis joue les teamfights pendant ton power spike.",
                    ("lose", "late"): "Plan de jeu : survis en lane, farme longtemps, et attends ton power spike pour jouer "
                                      "les teamfights.",
                    ("win", "early"): "Plan de jeu : prends l'avantage en lane, puis force les objectifs avant que les "
                                      "autres te rattrapent.",
                    ("win", "mid"): "Plan de jeu : prends l'avantage en lane pour arriver plus vite à ton power spike.",
                    ("win", "late"): "Plan de jeu : profite de la lane pour farmer, sans forcer les combats avant ton "
                                     "power spike.",
                    ("even", "early"): "Plan de jeu : farme proprement, puis force les combats pendant ton power spike.",
                    ("even", "mid"): "Plan de jeu : farme proprement et joue les teamfights pendant ton power spike.",
                    ("even", "late"): "Plan de jeu : farme longtemps et garde les teamfights pour ton power spike."}},
    "en": {1: "hard carry (position 1). You need the most souls: farm first (lanes, jungle) and do not force fights "
              "before your key items, you are the one who wins the late game.",
           2: "soft carry (position 2). Lots of souls too, but your peak comes earlier: as soon as you have your first "
              "key items, hunt kills, fights and objectives.",
           3: "frontline (position 3). Medium farm: you start the fights and take the damage for your team.",
           4: "roamer (position 4). Low farm: leave your lane for ganks and picks, and farm while you move.",
           5: "soft support (position 5). You deal damage, but your real job is to make your carries win (crowd "
              "control, counter-buys against the enemy carry).",
           6: "hard support (position 6). Low farm: heal, shield and save your carries.",
           "head": "Role: {roles}", "or": " Or ",
           "plan": {("lose", "early"): "Game plan: survive the lane, your moment comes right after. Force fights during "
                                       "your power spike.",
                    ("lose", "mid"): "Game plan: survive the lane, farm, then play the teamfights during your power spike.",
                    ("lose", "late"): "Game plan: survive the lane, farm for a long time, and wait for your power spike to "
                                      "play the teamfights.",
                    ("win", "early"): "Game plan: get ahead in lane, then force objectives before the others catch up.",
                    ("win", "mid"): "Game plan: get ahead in lane to reach your power spike sooner.",
                    ("win", "late"): "Game plan: use the lane to farm, without forcing fights before your power spike.",
                    ("even", "early"): "Game plan: farm cleanly, then force fights during your power spike.",
                    ("even", "mid"): "Game plan: farm cleanly and play the teamfights during your power spike.",
                    ("even", "late"): "Game plan: farm for a long time and keep the teamfights for your power spike."}},
}


def lane_verdict(ln):
    """win / win_bit / even / lose_bit / lose, from the duo's kills and souls at the end of the lane."""
    kd, souls = ln["kd10"], ln["duo_souls"]
    return ("win" if kd >= 0.3 or souls >= 250 else "lose" if kd <= -0.3 or souls <= -250 else
            "win_bit" if kd >= 0.1 or souls >= 100 else "lose_bit" if kd <= -0.1 or souls <= -100 else "even")


def spike_phase(sp):
    return "early" if sp["to"] <= 20000 else "late" if sp["from"] >= 30000 else "mid"


# Role measured from the data, used when the community guide's position contradicts it (Lady Geist, ranked as a soft
# carry with an early peak, keeps growing until the end of the game and farms more than average).
MEASURED_ROLE = {
    "fr": {"scaling_carry": "carry qui scale. Il te faut beaucoup d'âmes : ton impact grandit jusqu'en fin de partie, "
                            "ne gâche pas ton farm en début de partie.",
           "late": "héros de fin de partie. Ton impact grandit avec le temps : garde-toi pour les gros teamfights.",
           "early": "héros de début de partie. Ton impact est maximal tôt : joue agressif et convertis ton avance en "
                    "objectifs avant que la partie s'allonge.",
           "guide": " (le guide des rôles le classe {pos}, les mesures disent autre chose)",
           "names": {1: "hard carry", 2: "soft carry"}},
    "en": {"scaling_carry": "scaling carry. You need lots of souls: your impact grows until the end of the game, do "
                            "not waste your farm early.",
           "late": "late game hero. Your impact grows with time: save yourself for the big teamfights.",
           "early": "early game hero. Your impact peaks early: play aggressively and turn your lead into objectives "
                    "before the game drags on.",
           "guide": " (the roles guide ranks it {pos}, the measurements say otherwise)",
           "names": {1: "hard carry", 2: "soft carry"}},
}


def measured_style(g):
    """(scaling, farm ratio): scaling is "late" when the impact at an equal game state grows by 0.3 or more from
    before 20 min to 25-45 min, "early" when it drops as much or the power spike ends by 20K souls."""
    t = g.get("timing") or []
    early = [v for v in t[:2] if v is not None]
    late = [v for v in t[3:6] if v is not None]
    trend = (sum(late) / len(late) - sum(early) / len(early)) if early and late else 0
    sp = g.get("spike") or {}
    farm = [x["per_min"] / x["avg_per_min"] for x in (g.get("farm") or [])[1:] if x and x.get("avg_per_min")]
    ratio = sum(farm) / len(farm) if farm else 1
    if trend >= 0.3:
        return "late", ratio
    if trend <= -0.3 or (sp.get("to") and sp["to"] <= 20000):
        return "early", ratio
    return "steady", ratio


def role_text(g, lang, positions):
    """The guide's positions when the measurements agree, else the measured role (saying the guide disagrees)."""
    R, M = ROLE[lang], MEASURED_ROLE[lang]
    scaling, farm = measured_style(g)
    agree = {1: scaling == "late" or farm >= 1.05, 2: scaling == "early"}
    kept = [p for p in positions if p in R and agree.get(p, True)]
    if kept:
        return R["head"].format(roles=R["or"].join(R[p] for p in kept))
    if scaling == "steady":
        return R["head"].format(roles=R["or"].join(R[p] for p in positions if p in R)) if positions else None
    key = "scaling_carry" if scaling == "late" and farm >= 1.03 else scaling
    if not positions:                       # not in the guide: the measured role alone
        return R["head"].format(roles=M[key])
    name, rest = M[key].split(". ", 1)
    guide = M["guide"].format(pos=" / ".join(M["names"].get(p, str(p)) for p in positions))
    return R["head"].format(roles=f"{name}{guide}. {rest}")


def role_lines(g, lang, positions):
    """The role (community position checked against the measurements) and the game plan (lane x spike phase)."""
    R, out = ROLE[lang], []
    role = role_text(g, lang, positions or [])
    if role:
        out.append(role)
    sp, ln = g.get("spike") or {}, g.get("lane")
    if ln and "kd10" in ln and sp.get("from") and not sp.get("flat"):
        lane = {"win": "win", "win_bit": "win", "lose": "lose", "lose_bit": "lose"}.get(lane_verdict(ln), "even")
        out.append(R["plan"][(lane, spike_phase(sp))])
    return out


def ingame_power(doc, p, lang="fr", group="ranked", positions=None):
    """The lane and the power spike as in-game text (category description). The game's font is proportional and
    has no block characters (verified 2026-11-18): each line starts with its bar of ■ so the bars line up, then
    the souls and the minute. Bars are relative to the hero's own range: the longest is where it weighs most."""
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
    lines = role_lines(g, lang, positions)
    lines += [""] if lines else []
    ln = g.get("lane")
    if ln and "kd10" in ln:
        verdict = lane_verdict(ln)

        def num_(v, d):
            txt = f"{abs(v):.{d}f}".replace(".", "," if lang == "fr" else ".")
            return txt if round(v, d) == 0 else ("+" if v > 0 else "−") + txt
        lines += [T["lane"][verdict].format(kd=num_(ln["kd10"], 1), souls=num_(ln["duo_souls"], 0)), ""]
    lo, hi = min(v for _, v in rows), max(v for _, v in rows)
    lines.append(T["head"])
    for nw, v in rows:
        n = 1 + round((v - lo) / (hi - lo) * 9) if hi > lo else 5
        mm = minute_at(nwq, nw)
        spike = sp.get("from") and sp["from"] <= nw < sp["to"] + 2500
        when = f" (≈{mm:.0f}')" if mm is not None else ""
        lines.append(f"{'■' * n}  {k(nw, lang)}{when}" + (f"  {T['spike']}" if spike else ""))
    if sp.get("from") and not sp.get("flat"):
        phase = T["phase"][spike_phase(sp)]
        txt = T["window"].format(a=k(sp["from"], lang), b=k(sp["to"], lang), phase=phase,
                                 ma=f"{sp.get('min_from') or 0:.0f}", mb=f"{sp.get('min_to') or 0:.0f}")
        objs = [T[key].format(m=mn) for key in ("rift", "boss") for mn in doc["events"].get(key, [])
                if sp.get("min_from") is not None and sp["min_from"] <= mn <= sp["min_to"]]
        lines.append(txt + (T["obj"].format(list=T["and"].join(objs)) if objs else "."))
    else:
        lines.append(T["flat"])
    # the game keeps 1,024 bytes of a category description (verified 2026-11-18): role and lane, then the power line
    text = "\n".join(lines)
    if "\n\n" + T["head"] in text:
        role, power = text.split("\n\n" + T["head"], 1)
        return [{"name": T["role_title"], "description": role.strip()},
                {"name": T["title"], "description": T["head"] + power}]
    return [{"name": T["title"], "description": text}]


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
