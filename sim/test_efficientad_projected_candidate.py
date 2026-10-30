"""Mathematical checks for the experimental projected EfficientAD bundle.

The system Python test suite skips these when PyTorch is unavailable. Run the
same tests in the isolated EfficientAD environment to exercise the projection.
"""

from __future__ import annotations

import importlib.util
import unittest


HAS_TORCH = importlib.util.find_spec("torch") is not None


@unittest.skipUnless(HAS_TORCH, "requires the isolated EfficientAD PyTorch environment")
class ProjectedCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        import torch
        from torch import nn
        from sim import efficientad_projected_candidate as projected

        cls.np = np
        cls.torch = torch
        cls.nn = nn
        cls.projected = projected

    def test_projector_is_seeded_and_orthonormal(self):
        p = self.projected.projector()
        self.assertEqual(tuple(p.shape), (320, 384))
        self.assertTrue(self.torch.equal(p, self.projected.projector()))
        identity = p @ p.T
        self.assertLess(float((identity - self.torch.eye(320)).abs().max()), 2e-6)

    def test_folded_final_convolutions_match_explicit_projection(self):
        torch = self.torch
        torch.manual_seed(71)
        full = (
            self.nn.Sequential(self.nn.Identity(), self.nn.Conv2d(2, 384, 1)),
            self.nn.Sequential(self.nn.Identity(), self.nn.Conv2d(2, 768, 1)),
            self.nn.Sequential(self.nn.Identity(), self.nn.Conv2d(2, 384, 1)),
        )
        mean = self.np.linspace(-0.4, 0.6, 384, dtype=self.np.float32).reshape(1, 384, 1, 1)
        std = self.np.linspace(0.5, 1.5, 384, dtype=self.np.float32).reshape(1, 384, 1, 1)
        p = self.projected.projector()
        folded = self.projected.project_models(full, p, mean, std)
        x = torch.randn(1, 2, 3, 3)
        with torch.inference_mode():
            original_t, original_s, original_ae = (model(x) for model in full)
            expected_t = torch.einsum(
                "kc,bchw->bkhw", p,
                (original_t - torch.from_numpy(mean)) / torch.from_numpy(std))
            expected_st = torch.einsum("kc,bchw->bkhw", p, original_s[:, :384])
            expected_sae = torch.einsum("kc,bchw->bkhw", p, original_s[:, 384:])
            expected_ae = torch.einsum("kc,bchw->bkhw", p, original_ae)
            got_t, got_s, got_ae = (model(x) for model in folded)
        self.assertTrue(torch.allclose(got_t, expected_t, atol=3e-5, rtol=3e-5))
        self.assertTrue(torch.allclose(got_s[:, :320], expected_st, atol=3e-5, rtol=3e-5))
        self.assertTrue(torch.allclose(got_s[:, 320:], expected_sae, atol=3e-5, rtol=3e-5))
        self.assertTrue(torch.allclose(got_ae, expected_ae, atol=3e-5, rtol=3e-5))
        st, ae = self.projected.raw_maps(x, folded)
        self.assertTrue(torch.allclose(st, ((expected_t - expected_st) ** 2).mean(1, keepdim=True),
                                       atol=3e-5, rtol=3e-5))
        self.assertTrue(torch.allclose(ae, ((expected_ae - expected_sae) ** 2).mean(1, keepdim=True),
                                       atol=3e-5, rtol=3e-5))

    def test_validation_only_quantiles_and_fused_peak(self):
        torch = self.torch
        from torch.nn import functional as F

        validation = [
            (torch.tensor([[[[0., 1.], [2., 3.]]]]),
             torch.tensor([[[[2., 4.], [6., 8.]]]])),
            (torch.tensor([[[[4., 5.], [6., 7.]]]]),
             torch.tensor([[[[10., 12.], [14., 16.]]]])),
        ]
        q = self.projected.calibration_from_maps(validation)
        self.assertAlmostEqual(q[0], float(torch.quantile(torch.arange(8.), 0.9)))
        self.assertAlmostEqual(q[1], float(torch.quantile(torch.arange(8.), 0.995)))
        ae_values = torch.arange(2., 18., 2.)
        self.assertAlmostEqual(q[2], float(torch.quantile(ae_values, 0.9)))
        self.assertAlmostEqual(q[3], float(torch.quantile(ae_values, 0.995)))

        st, ae = validation[1]
        expected_fused = 0.05 * ((st - q[0]) / (q[1] - q[0])
                                 + (ae - q[2]) / (q[3] - q[2]))
        expected_score = float(F.interpolate(F.pad(expected_fused, (4, 4, 4, 4)),
                                             size=(256, 256), mode="bilinear").amax())
        self.assertAlmostEqual(self.projected.score_from_maps(st, ae, q), expected_score)
        # A later test image must never enter the validation quantiles.
        test_map = (torch.full_like(st, 1000.), torch.full_like(ae, 1000.))
        self.assertGreater(self.projected.score_from_maps(*test_map, q), expected_score)
        self.assertEqual(q, self.projected.calibration_from_maps(validation))
        with self.assertRaises(ValueError):
            self.projected.calibration_from_maps([])


if __name__ == "__main__":
    unittest.main()
