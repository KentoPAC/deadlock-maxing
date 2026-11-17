"""The DeadlockMax build: written by the agent from everything gathered (real builds, creators, measured profiles,
the kit), then checked here and turned into a candidate like the others (key "dlmax", source "DeadlockMax").

Input (the "agent_build" key of finish.py), texts in the content language, the same texts in English under "en":
  {"name": "...", "description": "...",
   "categories": [{"name": "...", "description": "...", "core": false, "endgame": false,
                   "mods": [{"id": <item id>, "note": "if <situation>, buy it around <minute> because <reason>"}]}],
   "abilities": [<ability id>, ...],            # point order: the first time an ability appears is its unlock
   "ability_notes": {"<ability id>": "..."},     # optional
   "en": {"name": "...", "description": "...", "categories": [{"name": "...", "description": "...", "notes": ["..."]}],
          "ability_notes": {"<ability id>": "..."}}}
Organisation: lane, one "core": true category (bought every game, left to right), cheap situational categories
(slipped into the core when the game calls for it), one "endgame": true category (no order: picked against the
enemy team, each note saying against what).
Core + endgame list at least 12 tier 4 or active items (more when more are useful: the notes say which one to pick
in which situation); the smaller passives are sold one by one to make room (an upgrade takes its component's slot).
"""
import os
import time

from common import STAT_NOTE, fill, heroes, items, make_strings, read_json, write_candidate, write_json
from i18n import CONTENT_LANG

KEY, SOURCE = "dlmax", "DeadlockMax"
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
            note = STAT_NOTE.sub("", m.get("note") or "").strip()
            if len(note) < MIN_NOTE:
                errors.append(f"{where}: {item['name']}: the note must say when and why ({MIN_NOTE}+ characters, no pick or win rates)")
    order = spec.get("abilities") or []
    own = hero_abilities(hero_id)
    if own and set(order) != own:
        errors.append("abilities: the order must unlock the hero's 4 abilities and only them")
    if any(order.count(a) > 4 for a in set(order)):
        errors.append("abilities: an ability takes at most 4 points (unlock + 3 upgrades)")
    return errors


def to_build(spec, hero_id, lang_field=None):
    """Game build format; lang_field="en" takes the English texts (same structure, same items)."""
    en = spec.get("en") or {}
    tx = (lambda key, base: en.get(key)) if lang_field else (lambda key, base: spec.get(key))
    cats = []
    for ci, cat in enumerate(spec["categories"]):
        ce = en["categories"][ci] if lang_field else {}
        cats.append({"name": ce.get("name") if lang_field else cat["name"],
                     "description": ce.get("description") if lang_field else cat["description"],
                     "mods": [{"ability_id": m["id"], "annotation": ce["notes"][mi] if lang_field else m["note"]}
                              for mi, m in enumerate(cat["mods"])]})
    notes = (en.get("ability_notes") if lang_field else spec.get("ability_notes")) or {}
    changes, seen = [], {}
    for a in spec.get("abilities") or []:
        k = seen[a] = seen.get(a, 0) + 1
        change = ({"ability_id": a, "currency_type": 2, "delta": -1} if k == 1 else
                  {"ability_id": a, "currency_type": 1, "delta": -[1, 2, 5][min(k - 2, 2)]})
        if k == 1 and notes.get(str(a)):
            change["annotation"] = notes[str(a)]
        changes.append(change)
    return {"hero_id": hero_id, "name": tx("name", None), "description": tx("description", None), "language": 2,
            "details": {"mod_categories": cats, "ability_order": {"currency_changes": changes}}, "tags": []}


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
