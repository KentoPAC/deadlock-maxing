import unittest

from tests import helpers  # noqa: F401
import review

# 1-3 vitality, 4-6 spirit, 7 weapon; 3 is built from 2 (an upgrade replaces its component)
ITEMS = {1: ("vitality", 1600), 2: ("vitality", 1600), 3: ("vitality", 3200), 4: ("spirit", 1600),
         5: ("spirit", 1600), 6: ("spirit", 3200), 7: ("weapon", 3200)}
ITEMS = {i: {"id": i, "name": f"I{i}", "class_name": f"c{i}", "item_slot_type": col, "cost": cost,
             "type": "upgrade", "shopable": True} for i, (col, cost) in ITEMS.items()}
ITEMS[3]["component_items"] = ["c2"]


def spec(lane, core, answers=None):
    return {"categories": [{"name": "Lane", "mods": [{"id": i} for i in lane]},
                           {"name": "Core", "core": True, "mods": [{"id": i} for i in core]}],
            "review": answers or {}}


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self._items = review.items
        review.items = lambda lang=None: ITEMS

    def tearDown(self):
        review.items = self._items

    def test_an_upgrade_replaces_its_component_in_the_invested_value(self):
        steps = review.investments([1, 2, 3])
        self.assertEqual([s["spent"] for s in steps], [1600, 3200, 4800])      # 3 costs 3,200, 1,600 already paid
        self.assertEqual(steps[-1]["invested"]["vitality"], 4800)               # 1 + 3, not 1 + 2 + 3

    def test_the_vitality_step_must_come_as_early_as_in_good_builds(self):
        late = spec([7], [4, 5, 6, 1, 2, 3])
        self.assertIn("invest:vitality", review.investment_flags(late))         # no good builds: the usual mark
        early = spec([7], [1, 2, 3, 4, 5, 6])
        self.assertNotIn("invest:vitality", review.investment_flags(early))
        self.assertIsNone(review.marks([{"order": [2, 3, 4]}] * 4)["vitality"])  # never 4,800 in them: no mark
        good = [{"order": [7, 4, 5, 6, 1, 2, 3]}] * 4                           # good builds reach it late too
        self.assertNotIn("invest:vitality", review.investment_flags(late, good))

    def test_flags_need_an_answer(self):
        raised = {"invest:vitality": "late"}
        self.assertEqual(review.unanswered(spec([], []), raised), raised)
        answered = spec([], [], {"invest:vitality": "Fixed: the greens now come right after the lane."})
        self.assertEqual(review.unanswered(answered, raised), {})

    def test_what_good_builds_agree_on(self):
        good = [{"items": [1, 2, 4], "imbue": {}}] * review.GOOD_MIN
        flags = review.build_flags(spec([1], [2, 7]), good, otps=set())
        self.assertIn("absent:7", flags)                                       # in the core, in no good build
        self.assertIn("missing:4", flags)                                      # in all of them, not here
        self.assertNotIn("absent:7", review.build_flags(spec([1], [2, 7]), good, otps={7}))   # one-tricks buy it

    def test_in_game_line_names_the_item_that_reaches_each_step(self):
        line = review.thresholds_line(spec([7], [1, 2, 3, 4, 5, 6]), 0, "en")
        self.assertIn("Vitality with I3 · Spirit with I6", line)


if __name__ == "__main__":
    unittest.main()
