"""Game knowledge for the agent: every shop item and every hero kit, generated from deadlock-api, refreshed per patch.

Writes Markdown references Claude can read on demand (the deadlockmax-knowledge skill):
  index.md   items grouped by effect (anti-heal, % HP damage, resist shred, crowd control...), one line each
  items.md   every shop item: FR / EN name, slot, tier, cost, active or passive, effect tags, description, stats
  heroes.md  every playable hero: FR / EN name, type, tags, role, and its 4 abilities with their description
  meta.json  generation date and the patch it reflects

Tags come from the items' technical properties (not from guesses), completed by a few description keywords
(purge, disarm...). They are what lets the agent answer "which item gives anti-heal?" without guessing.

Usage: python3 -I knowledge.py <out_dir>            (re)generate
       python3 -I knowledge.py <out_dir> --check    say whether a patch came out since the last generation
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get  # noqa: E402
import patchnotes  # noqa: E402
from tooltips import number, plain  # noqa: E402

# tag -> (French label, English label, technical properties that define it)
TAGS = {
    "antiheal": ("Anti-soin", "Anti-heal", ["HealAmpReceivePenaltyPercent", "HealAmpRegenPenaltyPercent"]),
    "pct_hp": ("Dégâts en % des PV (anti-tank)", "% HP damage (anti-tank)",
               ["CurrentHealthDamage", "MaxHealthPercentAsDPS", "MaxHealthDamage", "MaxHPDamage", "HealthPctDamage",
                "DotHealthPercent"]),
    "bullet_shred": ("Réduit la résistance aux balles adverse", "Bullet resist shred",
                     ["BulletArmorReduction", "BulletResistReduction"]),
    "spirit_shred": ("Réduit la résistance à l'esprit adverse", "Spirit resist shred",
                     ["MagicResistReduction", "TechArmorDamageReduction"]),
    "bullet_res": ("Résistance aux balles", "Bullet resist",
                   ["BulletResist", "BulletResistBelowThreshold", "BulletResistPerStack", "BuffBulletResist"]),
    "spirit_res": ("Résistance à l'esprit", "Spirit resist", ["TechResist", "TechResistBelowThreshold", "BuffTechResist"]),
    "status_res": ("Résistance aux effets (contrôles, ralentissements)", "Status / slow resist",
                   ["StatusResistancePercent", "StatusImmuneDuration", "SlowResistancePercent"]),
    "anti_gun": ("Réduit la cadence de tir adverse", "Enemy fire rate slow", ["FireRateSlow"]),
    "anti_spirit": ("Réduit la puissance spirituelle adverse", "Enemy spirit power reduction", ["TechPowerReduction"]),
    "dmg_reduction": ("Réduit les dégâts infligés par l'adversaire", "Enemy damage reduction", ["OutgoingDamagePenaltyPercent"]),
    "stun": ("Étourdit / gèle", "Stun / freeze", ["StunDuration", "FreezeDuration", "DazeDuration"]),
    "silence": ("Silence (bloque les capacités)", "Silence", ["SilenceDuration"]),
    "slow": ("Ralentit", "Slow", ["SlowPercent", "MovementSpeedSlow", "MaxSlowPercent"]),
    "lift": ("Soulève / immobilise", "Lift / tether", ["LiftHeight", "TetherDuration"]),
    "barrier": ("Barrière (bouclier)", "Barrier",
                ["CombatBarrier", "VexBarrierCombatBarrier", "GuardianWardCombatBarrier", "BarrierDuration"]),
    "lifesteal": ("Vol de vie / soin sur soi", "Lifesteal / self heal",
                  ["BulletLifestealPercent", "BonusSpiritLifesteal", "ImbueAbilityLifesteal", "HealthStealPctHero",
                   "LifestealHeal", "HealPercentPerHeadshot", "BonusHealthRegen", "Regeneration", "HealOnKill",
                   "ActiveBonusLifesteal", "HealOnActivate"]),
    "ally_heal": ("Soigne les alliés", "Heals allies", ["HealPercentAmount", "TotalHealthRegen", "AllyPercentage", "HealAmount"]),
    "heal_amp": ("Augmente les soins", "Healing amplification", ["HealAmpCastPercent", "HealAmpRegenPercent"]),
    "mobility": ("Mobilité (endurance, glissade, vol)", "Mobility",
                 ["Stamina", "StaminaCooldownReduction", "SlideScale", "AirControlPercent", "AirMoveIncreasePercent"]),
    "invis": ("Invisibilité", "Invisibility", ["InvisDuration", "InvisFadeToDuration"]),
    "cooldown": ("Réduit les temps de recharge", "Cooldown reduction",
                 ["CooldownReduction", "ItemCooldownReduction", "ImbuedCooldownMultiplier", "UltimateCooldownReduction",
                  "CooldownReductionOnHitPct"]),
    "farm": ("Farm (âmes en plus)", "Farm (extra souls)",
             ["BonusSoulsPct", "BonusGoldPerMinute", "StackingGoldPerMinute", "NonPlayerBonusWeaponPower"]),
    "reflect": ("Renvoie les dégâts", "Damage reflect", ["BulletDamageReflectedPct", "SpiritDamageReflectedPct"]),
    "death_save": ("Évite la mort", "Prevents death", ["DeathImmunityDuration"]),
    "purge": ("Purge (retire les effets)", "Purge / dispel", []),
    "disarm": ("Désarme (bloque le tir)", "Disarm", []),
}
# English description keywords for effects without a dedicated property
# (only verbs applied to an enemy: "immune to stuns" or "cannot be used while silenced" must not tag the item)
_TARGET = r"(?:all |nearby |the |an |a |your |enemies|enemy|target|them)"
_ING = r"(?<!immune to )(?<!while )(?<!from )"
KEYWORDS = {"purge": r"\bpurges?\b|\bdispels? (?:all|negative|debuff)",
            "disarm": r"\bdisarms? " + _TARGET + r"|" + _ING + r"\bdisarming\b(?! hex)",
            "silence": r"\bsilences? " + _TARGET + r"|" + _ING + r"\bsilencing\b", "stun": r"\bstuns? " + _TARGET}
SELF_PENALTY = {"upgrade_cheat_death"}  # its heal penalty hits its owner: not an anti-heal
SLOT = {"weapon": ("Arme", "Weapon"), "vitality": ("Vitalité", "Vitality"), "spirit": ("Esprit", "Spirit")}


def nonzero(prop):
    value = (prop or {}).get("value")
    try:
        return float(str(value).split()[0]) != 0
    except (TypeError, ValueError, IndexError):
        return False


def description(item):
    """Plain text of every description block of an item or ability."""
    parts = []
    for section in item.get("tooltip_sections") or []:
        for attr in section.get("section_attributes") or []:
            if attr.get("loc_string"):
                parts.append(plain(attr["loc_string"]))
    for section in (item.get("tooltip_details") or {}).get("info_sections") or []:
        text = section.get("loc_string") or ""
        if text and not text.strip().startswith("#"):
            parts.append(plain(text))
    desc = item.get("description")
    if not parts and isinstance(desc, dict):
        parts.append(plain(desc.get("desc") or ""))
    return " ".join(p for p in parts if p).strip()


def stats(item):
    """'Label value' strings of the item's labelled, non-empty stats."""
    out = []
    for key, prop in (item.get("properties") or {}).items():
        label, value = prop.get("label"), prop.get("value")
        if not label or not nonzero(prop) or key.startswith("Ability"):
            continue
        postfix = "" if re.search(r"[a-zA-Z%]$", str(value)) else (prop.get("postfix") or "")
        out.append(f"{label} {number(value)}{postfix}")
    return out


def tags(item_en):
    props = item_en.get("properties") or {}
    text = description(item_en).lower()
    out = []
    for tag, (_, _, keys) in TAGS.items():
        if tag == "antiheal" and item_en.get("class_name") in SELF_PENALTY:
            continue
        if any(nonzero(props.get(k)) for k in keys) or (tag in KEYWORDS and re.search(KEYWORDS[tag], text)):
            out.append(tag)
    return out


def latest_patch():
    try:
        notes = get("/v2/patches")  # v1 stops at older notes
        best = max(notes, key=lambda n: n.get("pub_date") or "")
        return {"date": (best.get("pub_date") or "")[:10], "title": best.get("title")}
    except Exception:
        return None


def short(text, n=150):
    text = text.split(". ")[0].rstrip(".") + "." if text else ""
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def generate(out_dir):
    fr = {i["id"]: i for i in get("/v1/assets/items", language="french")}
    en = {i["id"]: i for i in get("/v1/assets/items")}
    shop = sorted((i for i in en.values() if i.get("type") == "upgrade" and i.get("shopable")),
                  key=lambda i: (i.get("item_slot_type") or "", i.get("item_tier") or 0, i.get("name")))
    patch = latest_patch()
    head = f"Généré le {time.strftime('%Y-%m-%d')} depuis deadlock-api" + (
        f", dernier patch : {patch['date']} ({patch['title']})" if patch else "") + "."

    rows = []
    for item in shop:
        f = fr.get(item["id"], item)
        rows.append({"id": item["id"], "fr": f.get("name"), "en": item.get("name"), "slot": item.get("item_slot_type"),
                     "tier": item.get("item_tier"), "cost": item.get("cost"), "active": bool(item.get("is_active_item")),
                     "tags": tags(item), "desc_fr": description(f), "desc_en": description(item), "stats": stats(f)})

    def label(r):
        slot = SLOT.get(r["slot"], (r["slot"], r["slot"]))[0]
        return (f"**{r['fr']}** ({r['en']}) — {slot} T{r['tier']}, {r['cost']} âmes"
                f"{', actif' if r['active'] else ''}")

    index = ["# Objets Deadlock par effet", "", head,
             "Une ligne par objet : nom français (nom anglais), emplacement, palier, prix, puis l'effet en bref.",
             "Le détail (description complète, statistiques) est dans items.md.", ""]
    for tag, (lab_fr, lab_en, _) in TAGS.items():
        hits = [r for r in rows if tag in r["tags"]]
        if not hits:
            continue
        index += [f"## {lab_fr} ({lab_en})", ""]
        index += [f"- {label(r)} : {short(r['desc_fr'])}" for r in sorted(hits, key=lambda r: (r["tier"], r["cost"]))]
        index.append("")

    try:
        recent = patchnotes.changes(120)["items"]
    except Exception:
        recent = {}
    items_md = ["# Tous les objets de la boutique", "", head, ""]
    for slot in ("weapon", "vitality", "spirit"):
        items_md += [f"## {SLOT[slot][0]} ({SLOT[slot][1]})", ""]
        for r in (r for r in rows if r["slot"] == slot):
            tag_txt = ", ".join(TAGS[t][0] for t in r["tags"]) or "aucune étiquette"
            items_md += [f"### {r['fr']} ({r['en']})", f"T{r['tier']}, {r['cost']} âmes, {'actif' if r['active'] else 'passif'}. "
                         f"Effets : {tag_txt}.", "", r["desc_fr"] or "(pas de description)", ""]
            if r["stats"]:
                items_md += ["Stats : " + " ; ".join(r["stats"]), ""]
            if recent.get(r["id"]):
                items_md += ["Changements récents (notes de patch, à prendre en compte avant de le conseiller) :"]
                items_md += [f"- {c['date']} : {c['text']}" for c in recent[r["id"]]] + [""]

    heroes_fr = {h["id"]: h for h in get("/v1/assets/heroes", language="french")}
    heroes_en = {h["id"]: h for h in get("/v1/assets/heroes")}
    by_class_fr = {i.get("class_name"): i for i in fr.values()}
    by_class_en = {i.get("class_name"): i for i in en.values()}
    hero_md = ["# Héros jouables et leurs capacités", "", head, ""]
    hero_rows = []
    for hid, h in sorted(heroes_fr.items(), key=lambda x: x[1]["name"]):
        # in_development stays true on some released heroes (Baba, Violet): development_state is the reliable flag
        if not h.get("player_selectable") or h.get("disabled") or h.get("development_state") != "release":
            continue
        he = heroes_en.get(hid, h)
        desc = h.get("description") or {}
        hero_md += [f"## {h['name']} ({he['name']})",
                    f"Type : {h.get('hero_type')}. Étiquettes : {', '.join(h.get('tags') or [])}. "
                    f"Arme : {h.get('gun_tag')}. Complexité {h.get('complexity')}/3.",
                    f"Rôle : {plain(desc.get('role') or '')}", f"Style : {plain(desc.get('playstyle') or '')}", ""]
        abilities = []
        for n in (1, 2, 3, 4):
            cls = (h.get("items") or {}).get(f"signature{n}")
            a_fr, a_en = by_class_fr.get(cls), by_class_en.get(cls)
            if not a_fr:
                continue
            cd = ((a_fr.get("properties") or {}).get("AbilityCooldown") or {}).get("value")
            cd_txt = f" Recharge {number(cd)} s." if cd not in (None, "0", 0, "0.0") else ""
            hero_md += [f"### {n}. {a_fr['name']} ({(a_en or a_fr)['name']})", (description(a_fr) or "(pas de description)") + cd_txt, ""]
            abilities.append({"n": n, "fr": a_fr["name"], "en": (a_en or a_fr)["name"]})
        hero_rows.append({"id": hid, "fr": h["name"], "en": he["name"], "abilities": abilities})

    os.makedirs(out_dir, exist_ok=True)
    for name, lines in (("index.md", index), ("items.md", items_md), ("heroes.md", hero_md)):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines).rstrip() + "\n")
    meta = {"generated": time.strftime("%Y-%m-%d"), "patch": patch, "items": len(rows), "heroes": len(hero_rows)}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "items.json"), "w", encoding="utf-8") as fh:
        json.dump({"items": rows, "heroes": hero_rows}, fh, ensure_ascii=False)
    print(f"{len(rows)} objets, {len(hero_rows)} héros -> {out_dir} ({meta['patch']})")


def check(out_dir):
    path = os.path.join(out_dir, "meta.json")
    if not os.path.exists(path):
        print("Pas encore généré : lance la génération.")
        return 1
    with open(path, encoding="utf-8") as fh:
        meta = json.load(fh)
    patch = latest_patch()
    known = (meta.get("patch") or {}).get("date")
    if patch and known and patch["date"] > known:
        print(f"Patch sorti le {patch['date']} ({patch['title']}) après la génération ({known}) : régénère.")
        return 1
    print(f"À jour : généré le {meta['generated']}, dernier patch {known}.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(check(sys.argv[1]) if "--check" in sys.argv else generate(sys.argv[1]))
