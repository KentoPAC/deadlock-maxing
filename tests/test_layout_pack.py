import unittest

from tests import helpers  # noqa: F401
import apply


def cat(name, n_items, desc=""):
    return {"name": name, "description": desc, "mods": [{"ability_id": i} for i in range(n_items)]}


class PackTest(unittest.TestCase):
    def test_rows_keep_the_order_fill_the_width_and_share_a_height(self):
        cats = [cat("Lane", 3), cat("Hard lane", 2), cat("Core", 12), cat("A", 1), cat("B", 2)]
        rows = apply.pack(cats)
        self.assertEqual([c["name"] for r in rows for c in r], ["Lane", "Hard lane", "Core", "A", "B"])
        self.assertEqual([[c["name"] for c in r] for r in rows], [["Lane", "Hard lane"], ["Core"], ["A", "B"]])
        for r in rows:
            self.assertEqual(sum(c["width"] for c in r) + apply.GAP * (len(r) - 1), apply.ROW_W)
            self.assertEqual(len({c["height"] for c in r}), 1)

    def test_a_category_wider_than_a_row_wraps_its_items(self):
        big = cat("All", 20)
        apply.pack([big])
        self.assertEqual(big["width"], apply.ROW_W)
        self.assertGreater(big["height"], apply.height_at(cat("One", 1), apply.ROW_W))


if __name__ == "__main__":
    unittest.main()
