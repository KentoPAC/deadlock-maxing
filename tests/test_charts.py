import unittest

from tests import helpers  # noqa: F401
import charts

BUCKETS = list(range(0, 62501, 2500))
EVENTS = {"rift": [20], "boss": [30]}


def group(curve):
    return {"fights": curve, "spike": {"from": 30000, "to": 37500, "min_from": 27, "min_to": 34},
            "nw_by_minute": {"5": [0, 3000, 0], "10": [0, 8000, 0], "20": [0, 20000, 0], "30": [0, 32000, 0],
                             "50": [0, 60000, 0]},
            "lane": {"end_min": 9, "kd10": -0.2, "duo_souls": -145}, "timing": [0.2, -0.1], "fed": [0.1, None, -0.2], "farm": []}


class ChartsTest(unittest.TestCase):
    def test_power_chart_draws_above_and_below_zero_and_marks_the_spike(self):
        curve = [None, None] + [0.5 if 12 <= i < 15 else -0.3 for i in range(2, 26)]
        out = charts.power(group(curve), BUCKETS, EVENTS, "Hero")
        zero = next(i for i, line in enumerate(out) if line.strip().startswith("0 ┤"))
        self.assertIn("██", "".join(out[:zero]))            # positive buckets above the zero line
        self.assertIn("██", "".join(out[zero + 1:zero + 3]))  # negative ones below
        spike = next(line for line in out if line.strip().startswith("SPIKE"))
        self.assertEqual(spike.count("▔"), 6)                 # 30K to 37.5K = 3 buckets of 2 characters
        self.assertIn("R", next(line for line in out if "repères" in line))

    def test_ingame_power_is_one_bar_per_5000_souls_with_the_strong_window_marked(self):
        doc = {"buckets": BUCKETS, "events": EVENTS}
        curve = [None, None] + [0.5 if 12 <= i < 15 else -0.3 for i in range(2, 26)]
        cat = charts.ingame_power(doc, {"ranked": group(curve)}, "en")
        lines = cat["description"].split("\n")
        self.assertEqual(len([x for x in lines if x.startswith("■")]), 9)    # one bar per 5K, 10K to 50K
        self.assertTrue(all(ch not in cat["description"] for ch in "█▁░│─"))  # characters the game cannot draw
        self.assertIn("◆ SPIKE", next(x for x in lines if "30K" in x))
        self.assertTrue(all(x.startswith("■") for x in lines if "K (" in x))      # bars first: they line up
        self.assertIn("30K and 37.5K", lines[-1])
        self.assertEqual(lines[0], "Game plan: survive the lane, farm for a long time, and wait for your power spike to "
                                   "play the teamfights.")                      # lane lost, spike late (30K+)
        self.assertIn("Lane: slightly unfavourable (−0.2 kills / 10 min, −145 souls for the duo): avoid long trades.", lines)
        with_role = charts.ingame_power(doc, {"ranked": group(curve)}, "fr", positions=[1])["description"]
        self.assertTrue(with_role.startswith("Rôle : hard carry (position 1)."))

    def test_numbers_use_the_french_decimal_comma(self):
        self.assertEqual(charts.k(27500), "27,5K")
        self.assertEqual(charts.num(-0.25), "−0,25")


if __name__ == "__main__":
    unittest.main()
