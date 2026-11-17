import unittest

from tests import helpers  # noqa: F401
import agent_build

NOTE = "Si la lane est dure, vers 3 min, parce que le soin compte."
ITEMS = {i: {"id": i, "name": f"I{i}", "class_name": f"c{i}", "type": "upgrade", "shopable": True} for i in range(1, 15)}
ITEMS[13]["component_items"] = ["c1"]
ITEMS.update({100 + a: {"id": 100 + a, "class_name": f"ab{a}", "type": "ability"} for a in range(1, 5)})
HEROES = {7: {"items": {f"signature{a}": f"ab{a}" for a in range(1, 5)}}}


def spec(core_ids, endgame_ids=(11, 12)):
    cats = [{"name": "Lane", "description": "Pour la lane.", "mods": [{"id": 1, "note": NOTE}]},
            {"name": "Core", "description": "Toujours.", "core": True, "mods": [{"id": i, "note": NOTE} for i in core_ids]},
            {"name": "Fin", "description": "Au choix.", "endgame": True, "mods": [{"id": i, "note": NOTE} for i in endgame_ids]}]
    return {"name": "B", "description": "D", "categories": cats, "abilities": [101, 102, 103, 104, 101],
            "en": {"name": "B", "description": "D",
                   "categories": [{"name": c["name"], "description": "x", "notes": ["n"] * len(c["mods"])} for c in cats]}}


class AgentBuildTest(unittest.TestCase):
    def setUp(self):
        self._i, self._h = agent_build.items, agent_build.heroes
        agent_build.items, agent_build.heroes = (lambda: ITEMS), (lambda: HEROES)

    def tearDown(self):
        agent_build.items, agent_build.heroes = self._i, self._h

    def test_valid_build(self):
        self.assertEqual(agent_build.check(spec(range(1, 11)), 7), [])

    def test_core_and_proposals_fill_twelve_slots_an_upgrade_taking_its_component_slot(self):
        self.assertEqual(agent_build.check(spec(range(1, 11), (11, 12, 13, 14)), 7), [])   # 13 replaces 1: 13 slots
        errors = " ".join(agent_build.check(spec(range(1, 10), (11, 13)), 7))           # 13 replaces 1: 10 slots
        self.assertIn("fill 10 slots", errors)

    def test_every_item_needs_a_real_note(self):
        s = spec(range(1, 11))
        s["categories"][0]["mods"][0]["note"] = "Pick Rate: 62% WR: +1%"
        self.assertIn("the note must say when and why", " ".join(agent_build.check(s, 7)))

    def test_ability_order_becomes_unlocks_then_upgrades(self):
        order = agent_build.to_build(spec(range(1, 11)), 7)["details"]["ability_order"]["currency_changes"]
        self.assertEqual([(c["ability_id"], c["currency_type"]) for c in order],
                         [(101, 2), (102, 2), (103, 2), (104, 2), (101, 1)])


if __name__ == "__main__":
    unittest.main()
