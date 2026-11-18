"""The DeadlockMax build: written by the agent from everything gathered (real builds, creators, measured profiles,
the kit), then checked here and turned into a candidate like the others (key "dlmax", source "DeadlockMax").

Input (the "agent_build" key of finish.py), texts in the content language, the same texts in English under "en":
  {"name": "...", "description": "...",
   "categories": [{"name": "...", "description": "...", "core": false, "endgame": false,
                   "optional": <default: every category but the first one and the core>,
                   "mods": [{"id": <item id>, "note": "if <situation>, buy it around <minute> because <reason>",
                             "imbue": <ability id, required for items that imbue an ability>,
                             "sell": <0-100, default 95 for tier 1 and 85 for tier 2 passives: sold first by Quickbuy>}]}],
   "abilities": [<ability id>, ...],            # point order: the first time an ability appears is its unlock
   "tags": ["Weapon", "Spirit", "Crowd Control"],  # up to 3 game tags (TAGS)
   (advice on abilities goes in plan.abilities: the game refuses a build with notes on its ability order)
   "en": {"name": "...", "description": "...", "categories": [{"name": "...", "description": "...", "notes": ["..."]}],
          }}
Organisation: lane, one "core": true category (bought every game, left to right), cheap situational categories
(slipped into the core when the game calls for it), one "endgame": true category (no order: picked against the
enemy team, each note saying against what).
Core + endgame list at least 12 tier 4 or active items (more when more are useful: the notes say which one to pick
in which situation); the smaller passives are sold one by one to make room (an upgrade takes its component's slot).
"""
import os
import time

from common import STAT_NOTE, fill, heroes, items, make_strings, read_json, write_candidate, write_json
from i18n import CONTENT_LANG, LANGS

KEY, SOURCE = "dlmax", "DeadlockMax"
BUILD_NAME = "DeadlockMaxing"   # the project's name, first in every agent build's title (builds get published)
# Build tags of the game (ids from the game data, as copied builds carry them): up to 3 per build.
TAGS = {"Weapon": 47026193, "Vitality": 4213205702, "Spirit": 36498494, "For New Players": 1052421347,
        "For Intermediate Players": 1150155374, "For Advanced Players": 3797987367, "Damage": 2592289373,
        "Utility": 953263904, "Healing": 38758251, "Crowd Control": 4216803923, "Mobility": 3238474489,
        "Melee": 3401565923, "Headshots": 2579669585, "Debuff": 255841590}
# The game ignores the build description when a code is pasted (verified 2026-11-18, even with its own codes):
# the description goes into a first category without items, whose description is imported.
READ_FIRST = {"fr": "À lire", "en": "Read first"}
SLOTS = 12
MIN_NOTE = 25        # characters: a note says when and why, not just "good"


def hero_abilities(hero_id):
    """The hero's 4 ability ids (signature1..4)."""
    by_class = {i.get("class_name"): i["id"] for i in items().values()}
    slots = (heroes().get(hero_id) or {}).get("items") or {}
    return {by_class.get(slots.get(f"signature{n}")) for n in range(1, 5)} - {None}


def check(spec, hero_id):
    """Every reason the build cannot be published (empty when it is fine)."""
    errors, all_items = [], items()
    comps = lambda i: {c for c in all_items.get(i, {}).get("component_items") or []}
    en = spec.get("en") or {}
    cats, cats_en = spec.get("categories") or [], en.get("categories") or []
    for field in ("name", "description"):
        if not spec.get(field) or not en.get(field):
            errors.append(f"{field}: missing (in both languages)")
    for name in (spec.get("name") or "", en.get("name") or ""):
        if not name.startswith(BUILD_NAME):
            errors.append(f"name: starts with \"{BUILD_NAME}\", the project's name (e.g. \"{BUILD_NAME} · <hero>\")")
    if len(cats) != len(cats_en):
        errors.append(f"en.categories: {len(cats_en)} categories for {len(cats)}")
    for flag, what in (("core", "the items bought every game"), ("endgame", "the endgame proposals")):
        n = sum(1 for c in cats if c.get(flag))
        if n != 1:
            errors.append(f"{n} categories marked {flag}: exactly one lists {what}")
    final = [m.get("id") for c in cats if c.get("core") or c.get("endgame") for m in c.get("mods") or []]
    slots = {i for i in final if not any(all_items.get(i, {}).get("class_name") in comps(j) for j in final if j != i)}
    # the final inventory is tier 4, except actives worth their slot: smaller passives are sold to make room
    lasting = {i for i in slots if all_items.get(i, {}).get("item_tier") == 4 or all_items.get(i, {}).get("is_active_item")}
    if len(lasting) < SLOTS:
        sold = sorted(all_items.get(i, {}).get("name", str(i)) for i in slots - lasting)
        errors.append(f"core + endgame give {len(lasting)} tier 4 or active items: list at least enough to fill the {SLOTS} "
                      f"slots, more if they are useful, each note saying when to pick it "
                      f"(passives sold for room: {', '.join(sold) or 'none'})")
    for ci, cat in enumerate(cats):
        where = f"category {ci + 1} ({cat.get('name')})"
        ce = cats_en[ci] if ci < len(cats_en) else {}
        if not cat.get("name") or not cat.get("description") or not ce.get("name") or not ce.get("description"):
            errors.append(f"{where}: a name and a description in both languages")
        mods = cat.get("mods") or []
        if len(ce.get("notes") or []) != len(mods):
            errors.append(f"{where}: {len(ce.get('notes') or [])} English notes for {len(mods)} items")
        ids = [m.get("id") for m in mods]
        if len(set(ids)) != len(ids):
            errors.append(f"{where}: an item is listed twice")
        for m in mods:
            item = all_items.get(m.get("id"))
            if not item or item.get("type") != "upgrade" or not item.get("shopable"):
                errors.append(f"{where}: {m.get('id')} is not a shop item")
                continue
            if item.get("imbue") and m.get("imbue") not in (hero_abilities(hero_id) or {m.get("imbue")}):
                errors.append(f"{where}: {item['name']} imbues an ability: say which one (\"imbue\": <ability id>)")
            note = STAT_NOTE.sub("", m.get("note") or "").strip()
            if len(note) < MIN_NOTE:
                errors.append(f"{where}: {item['name']}: the note must say when and why ({MIN_NOTE}+ characters, no pick or win rates)")
    # upgrade paths: a component missing from the build is listed, or named in the note (buying it first is
    # cheaper and gives its effect earlier: e.g. Compress Cooldown before Superior Cooldown)
    by_class = {i.get("class_name"): i for i in all_items.values()}
    in_build = {m.get("id") for c in cats for m in c.get("mods") or []}
    for cat in cats:
        for m in cat.get("mods") or []:
            for comp in (by_class.get(c) for c in comps(m.get("id"))):
                names = {items(lang).get(comp["id"], {}).get("name", "").lower() for lang in LANGS} if comp else set()
                if comp and comp["id"] not in in_build and not any(n and n in (m.get("note") or "").lower() for n in names):
                    errors.append(f"{all_items[m['id']]['name']} is built from {comp['name']}: list {comp['name']} "
                                  f"before it, or name it in the note")
    tags = spec.get("tags") or []
    if len(tags) > 3 or any(t not in TAGS for t in tags):
        errors.append(f"tags: up to 3 among {', '.join(TAGS)}")
    order = spec.get("abilities") or []
    own = hero_abilities(hero_id)
    if own and set(order) != own:
        errors.append("abilities: the order must unlock the hero's 4 abilities and only them")
    if any(order.count(a) > 4 for a in set(order)):
        errors.append("abilities: an ability takes at most 4 points (unlock + 3 upgrades)")
    return errors


SELL_PRIORITY = {1: 95, 2: 85}   # what good builds do: small passives are sold first when slots run out


def game_fields(mod, upgraded=()):
    """Imbue target and Quickbuy sell priority of an item (game build fields). Items that evolve into another item
    of the build get no default priority: they are upgraded, not sold."""
    item = items().get(mod["id"], {})
    out = {}
    if mod.get("imbue"):
        out["imbue_target_ability_id"] = mod["imbue"]
    default = None if item.get("is_active_item") or mod["id"] in upgraded else SELL_PRIORITY.get(item.get("item_tier"))
    sell = mod.get("sell", default)
    if sell:
        out["sell_priority"] = sell
    return out


def to_build(spec, hero_id, lang_field=None):
    """Game build format; lang_field="en" takes the English texts (same structure, same items)."""
    en = spec.get("en") or {}
    tx = (lambda key, base: en.get(key)) if lang_field else (lambda key, base: spec.get(key))
    all_items = items()
    ids = {m["id"] for c in spec["categories"] for m in c["mods"]}
    classes = {c for i in ids for c in all_items.get(i, {}).get("component_items") or []}
    upgraded = {i for i in ids if all_items.get(i, {}).get("class_name") in classes}
    cats = []
    for ci, cat in enumerate(spec["categories"]):
        ce = en["categories"][ci] if lang_field else {}
        cats.append({"name": ce.get("name") if lang_field else cat["name"],
                     "description": ce.get("description") if lang_field else cat["description"],
                     "optional": cat.get("optional", ci > 0 and not cat.get("core")),
                     "mods": [dict({"ability_id": m["id"], "annotation": ce["notes"][mi] if lang_field else m["note"]},
                                   **game_fields(m, upgraded)) for mi, m in enumerate(cat["mods"])]})
    changes, seen = [], {}
    for a in spec.get("abilities") or []:
        k = seen[a] = seen.get(a, 0) + 1
        change = ({"ability_id": a, "currency_type": 2, "delta": -1} if k == 1 else
                  {"ability_id": a, "currency_type": 1, "delta": -[1, 2, 5][min(k - 2, 2)]})
        changes.append(change)
    intro = {"name": READ_FIRST["en" if lang_field else "fr"], "description": tx("description", None), "mods": []}
    return {"hero_id": hero_id, "name": tx("name", None), "description": tx("description", None), "language": 2,
            "details": {"mod_categories": [intro] + cats, "ability_order": {"currency_changes": changes}},
            "tags": [TAGS[t] for t in spec.get("tags") or []]}


def publish(folder, spec):
    """Check the build, write it as the "dlmax" candidate (first in the list) with both languages filled."""
    data = read_json(f"{folder}/candidates.json")
    hero_id = data["hero"]["id"]
    errors = check(spec, hero_id)
    if errors:
        raise SystemExit("DeadlockMax build refused:\n- " + "\n- ".join(errors))
    build = to_build(spec, hero_id)
    write_candidate(f"{folder}/{KEY}", build, prefill=CONTENT_LANG == "fr")
    english = [s["text"] for s in make_strings(to_build(spec, hero_id, "en"))]
    fill(f"{folder}/{KEY}", english, "en")
    write_json(f"{folder}/{KEY}/spec.json", spec, indent=1)
    count = lambda flag: sum(len(c["mods"]) for c in spec["categories"] if c.get(flag))
    others = [c for c in data["candidates"] if c["key"] != KEY]
    entry = {"key": KEY, "source": SOURCE, "title": build["name"], "author": SOURCE, "updated": int(time.time()),
             "language": 2, "needs_translation": False,
             "agent": {"core": count("core"), "proposals": count("endgame"),
                       "situations": sum(1 for c in spec["categories"][2:] if not c.get("core") and not c.get("endgame")),
                       "builds": len(others), "otp": sum(1 for c in others if c["source"] == "OTP")}}
    data["candidates"] = [entry] + [c for c in data["candidates"] if c["key"] != KEY]
    write_json(f"{folder}/candidates.json", data, indent=1)
    return entry


def exists(folder):
    return os.path.exists(f"{folder}/{KEY}/spec.json")
