import unittest

from tests import helpers  # noqa: F401
import agent_build

NOTE = "Si la lane est dure, vers 3 min, parce que le soin compte."
ITEMS = {i: {"id": i, "name": f"I{i}", "class_name": f"c{i}", "type": "upgrade", "shopable": True} for i in range(1, 15)}
for i in ITEMS:
    ITEMS[i]["item_tier"] = 4
ITEMS[1]["item_tier"], ITEMS[2]["item_tier"], ITEMS[2]["is_active_item"] = 3, 2, True
ITEMS[13]["component_items"] = ["c1"]
ITEMS.update({100 + a: {"id": 100 + a, "class_name": f"ab{a}", "type": "ability"} for a in range(1, 5)})
HEROES = {7: {"items": {f"signature{a}": f"ab{a}" for a in range(1, 5)}}}


def spec(core_ids, endgame_ids=(11, 12)):
    cats = [{"name": "Lane", "description": "Pour la lane.", "mods": [{"id": 1, "note": NOTE}]},
            {"name": "Core", "description": "Toujours.", "core": True, "mods": [{"id": i, "note": NOTE} for i in core_ids]},
            {"name": "Fin", "description": "Au choix.", "endgame": True, "mods": [{"id": i, "note": NOTE} for i in endgame_ids]}]
    return {"name": "DeadlockMaxing · H", "description": "D", "categories": cats, "abilities": [101, 102, 103, 104, 101],
            "en": {"name": "DeadlockMaxing · H", "description": "D",
                   "categories": [{"name": c["name"], "description": "x", "notes": ["n"] * len(c["mods"])} for c in cats]}}


class AgentBuildTest(unittest.TestCase):
    def setUp(self):
        self._i, self._h, self._p = agent_build.items, agent_build.heroes, agent_build.power_category
        agent_build.power_category = lambda hero_id, lang: None          # no measured profile in these tests
        agent_build.items, agent_build.heroes = (lambda lang=None: ITEMS), (lambda: HEROES)

    def tearDown(self):
        agent_build.items, agent_build.heroes, agent_build.power_category = self._i, self._h, self._p

    def test_valid_build(self):
        self.assertEqual(agent_build.check(spec(range(2, 11), (11, 12, 13, 14)), 7), [])

    def test_core_and_proposals_fill_twelve_slots_an_upgrade_taking_its_component_slot(self):
        self.assertEqual(agent_build.check(spec(range(1, 11), (11, 12, 13, 14)), 7), [])   # 13 replaces T3 1: 13 slots
        errors = " ".join(agent_build.check(spec(range(1, 10), (11, 13)), 7))           # 13 replaces 1: 10 slots
        self.assertIn("give 10 tier 4 or active items", errors)

    def test_small_passives_do_not_count_but_actives_do(self):
        ITEMS[3]["item_tier"] = 3
        try:
            errors = " ".join(agent_build.check(spec(range(1, 11), (11, 12)), 7))        # 1 is T3, 3 is T3: 10 count
            self.assertIn("give 10 tier 4 or active items", errors)
            self.assertIn("I1, I3", errors)                                              # 2 is a T2 active: kept
        finally:
            ITEMS[3]["item_tier"] = 4

    def test_every_item_needs_a_real_note(self):
        s = spec(range(1, 11))
        s["categories"][0]["mods"][0]["note"] = "Pick Rate: 62% WR: +1%"
        self.assertIn("the note must say when and why", " ".join(agent_build.check(s, 7)))

    def test_imbue_target_sell_priority_and_optional_categories(self):
        s = spec(range(2, 11), (11, 12, 13, 14))
        ITEMS[12]["imbue"] = True
        try:
            self.assertIn("imbues an ability", " ".join(agent_build.check(s, 7)))
            s["categories"][2]["mods"][1]["imbue"] = 103
            self.assertEqual(agent_build.check(s, 7), [])
            cats = agent_build.to_build(s, 7)["details"]["mod_categories"]
        finally:
            del ITEMS[12]["imbue"]
        self.assertEqual([c.get("optional") for c in cats], [None, False, False, True, None])   # read first, footer
        self.assertEqual(cats[0]["mods"], [])
        mods = {m["ability_id"]: m for c in cats for m in c["mods"]}
        self.assertEqual(mods[12]["imbue_target_ability_id"], 103)
        self.assertNotIn("sell_priority", mods[1])                       # tier 3: no default
        self.assertNotIn("sell_priority", mods[2])                       # tier 2 active: kept

    def test_an_item_that_evolves_in_the_build_is_not_sold_first(self):
        ITEMS.update({20: {"id": 20, "class_name": "c20", "type": "upgrade", "shopable": True, "item_tier": 1},
                      21: {"id": 21, "class_name": "c21", "type": "upgrade", "shopable": True, "item_tier": 1}})
        try:
            s = spec(range(2, 11), (11, 12, 13, 14))
            s["categories"][0]["mods"] += [{"id": 20, "note": NOTE}, {"id": 21, "note": NOTE}]
            s["en"]["categories"][0]["notes"] += ["n", "n"]
            ITEMS[11]["component_items"] = ["c20"]
            mods = {m["ability_id"]: m for c in agent_build.to_build(s, 7)["details"]["mod_categories"] for m in c["mods"]}
            self.assertNotIn("sell_priority", mods[20])                  # evolves into 11
            self.assertEqual(mods[21]["sell_priority"], 95)
        finally:
            del ITEMS[20], ITEMS[21], ITEMS[11]["component_items"]

    def test_a_missing_component_is_listed_or_named_in_the_note(self):
        s = spec(range(2, 11), (11, 12, 13, 14))                    # 13 is built from 1 (the lane item)
        s["categories"][0]["mods"][0]["id"] = 14
        self.assertIn("built from I1", " ".join(agent_build.check(s, 7)))
        s["categories"][2]["mods"][2]["note"] = NOTE + " En passant par I1."
        self.assertNotIn("built from I1", " ".join(agent_build.check(s, 7)))

    def test_an_item_changed_during_the_data_window_needs_a_review(self):
        changes = {"items": {11: [{"date": "2026-10-30", "ts": 2000, "title": "P", "text": "Heal reduced from 65 to 40"}]},
                   "heroes": {}}
        old = agent_build.patchnotes.changes
        agent_build.patchnotes.changes = lambda days=120: changes
        try:
            s = spec(range(2, 11), (11, 12, 13, 14))
            self.assertIn("Heal reduced from 65 to 40", " ".join(agent_build.check(s, 7, since=1000)))
            self.assertEqual(agent_build.check(s, 7, since=3000), [])                     # changed before the data
            s["patch_review"] = {"11": "Still the best answer to burst after the nerf."}
            self.assertEqual(agent_build.check(s, 7, since=1000), [])
        finally:
            agent_build.patchnotes.changes = old

    def test_symbols_the_game_refuses_are_caught(self):
        s = spec(range(2, 11), (11, 12, 13, 14))
        s["categories"][0]["description"] = "Lane □ forte"
        self.assertIn("□", " ".join(agent_build.check(s, 7)))
        s["categories"][0]["description"] = "Lane ◆ forte · ≈13' → « joue » ■"
        self.assertEqual(agent_build.check(s, 7), [])

    def test_tags_are_game_tag_ids(self):
        s = spec(range(2, 11), (11, 12, 13, 14))
        s["tags"] = ["Weapon", "Crowd Control"]
        self.assertEqual(agent_build.check(s, 7), [])
        self.assertEqual(agent_build.to_build(s, 7)["tags"], [47026193, 4216803923])
        s["tags"] = ["Fun"]
        self.assertIn("tags: up to 3", " ".join(agent_build.check(s, 7)))

    def test_ability_order_becomes_unlocks_then_upgrades(self):
        order = agent_build.to_build(spec(range(1, 11)), 7)["details"]["ability_order"]["currency_changes"]
        self.assertEqual([(c["ability_id"], c["currency_type"]) for c in order],
                         [(101, 2), (102, 2), (103, 2), (104, 2), (101, 1)])


if __name__ == "__main__":
    unittest.main()
