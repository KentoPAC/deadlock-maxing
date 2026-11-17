import unittest

from tests import helpers  # noqa: F401
import common
import find
import i18n

ITEMS = {1: {"id": 1, "class_name": "a", "type": "upgrade"}, 2: {"id": 2, "class_name": "b", "type": "upgrade"},
         3: {"id": 3, "class_name": "c", "type": "upgrade", "component_items": ["a"]},
         4: {"id": 4, "class_name": "d", "type": "upgrade"}}


def stat(item, matches, sold=0, minute=10):
    return {"item_id": item, "matches": matches, "sold": sold, "avg_buy_time_s": minute * 60}


class EndgameTest(unittest.TestCase):
    def setUp(self):
        i18n.use("fr")
        self._items, self._stats = find.items, find.endgame_stats
        find.items = lambda: ITEMS

    def tearDown(self):
        find.items, find.endgame_stats = self._items, self._stats
        i18n.use(i18n.DEFAULT_LANG)

    def test_upgrade_takes_its_component_slot(self):
        find.endgame_stats = lambda h, s: [stat(3, 100, minute=35), stat(4, 100, minute=30), stat(2, 30, minute=20)]
        own = [stat(1, 20, minute=12), stat(2, 20, sold=15)]
        slots, options = find.endgame_slots(0, 0, own, 20)
        self.assertEqual([s["item_id"] for s, _ in slots], [4, 3])       # 1 upgraded into 3; 2 mostly sold
        self.assertEqual([s["item_id"] for s, _ in options], [2])

    def test_endgame_notes_are_localized(self):
        fr = i18n.t("otp.note_endgame", pct=82, rank="Oracle", souls=60, minute=39)
        self.assertEqual(common.localize_generated(fr, "en"),
                         "Kept to the end by 82% of Oracle+ players who finish with 60K souls. Bought around 39 min.")
        self.assertEqual(common.localize_generated(i18n.t("otp.cat.endgame", n=12), "en"), "Endgame: 12 slots")


if __name__ == "__main__":
    unittest.main()
