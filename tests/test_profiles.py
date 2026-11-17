import unittest

from tests import helpers  # noqa: F401
import profiles


class ProfilesTest(unittest.TestCase):
    def test_smooth_weights_neighbours_and_keeps_gaps(self):
        self.assertEqual(profiles.smooth([1.0, None, 3.0, 5.0], [1, 1, 1, 3], 1), [1.0, None, 4.5, 4.5])

    def test_spike_window_is_the_shape_above_the_hero_own_average(self):
        # a hero above average everywhere still gets a window only where he is furthest above his own level
        curve = [None, None] + [1.0] * 6 + [1.6, 1.7, 1.6] + [1.0] * 13 + [1.0]
        minutes = [9999] * len(curve)
        spike = profiles.spike_window(curve, minutes, 5000)
        self.assertEqual((spike["from"], spike["to"], spike["peak"]), (20000, 27500, 22500))

    def test_spike_window_flat_and_ignores_thin_buckets(self):
        self.assertEqual(profiles.spike_window([0.5] * 25, [9999] * 25, 5000), {"flat": True})
        curve = [0.0] * 24 + [3.0]
        minutes = [9999] * 24 + [10]          # the peak bucket has almost no play time: not a spike
        self.assertEqual(profiles.spike_window(curve, minutes, 5000), {"flat": True})

    def test_minute_at_interpolates_the_median_net_worth(self):
        nwq = {10: [6000, 7000, 8000], 20: [15000, 17000, 19000]}
        self.assertEqual(profiles.minute_at(nwq, 12000), 15.0)
        self.assertIsNone(profiles.minute_at(nwq, 40000))

    def test_french_numbers(self):
        self.assertEqual(profiles.fmt(-0.123), "−0,12")
        self.assertEqual(profiles.k(22500), "22,5K")
        self.assertEqual(profiles.k(30000), "30K")


if __name__ == "__main__":
    unittest.main()
