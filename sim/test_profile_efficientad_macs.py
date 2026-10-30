"""Cross-check the static MAC profile against the pinned PyTorch model shapes."""

import unittest

from sim.profile_efficientad_macs import compare, profile


class ProfileEfficientadMacsTests(unittest.TestCase):
    def test_baseline_matches_pinned_model_forward_hooks(self):
        baseline = profile(384)
        self.assertEqual(baseline["total_conv_count"], 22)
        self.assertEqual(baseline["total_macs"], 37_947_289_600)
        self.assertEqual(
            {name: (model["conv_count"], model["macs"])
             for name, model in baseline["models"].items()},
            {"teacher": (4, 15_310_903_296),
             "student": (4, 20_243_404_800),
             "autoencoder": (14, 2_392_981_504)},
        )
        for model in baseline["models"].values():
            self.assertEqual(model["layers"][-1]["output_chw"][1:], [56, 56])

    def test_half_feature_width_retains_all_branches(self):
        comparison = compare(384, 192)
        candidate = comparison["candidate"]
        self.assertEqual(candidate["student_out_channels"], 384)
        self.assertEqual(candidate["total_conv_count"], 22)
        self.assertEqual(candidate["total_macs"], 30_201_720_832)
        self.assertEqual(comparison["saved_macs"], 7_745_568_768)
        self.assertAlmostEqual(comparison["saved_fraction"], 0.20411388664765137)

    def test_invalid_feature_width_rejected(self):
        for channels in (0, -1):
            with self.subTest(channels=channels), self.assertRaises(ValueError):
                profile(channels)


if __name__ == "__main__":
    unittest.main()
