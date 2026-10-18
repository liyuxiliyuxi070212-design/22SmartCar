import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from legacy_corr import pearson_r


class PearsonRTests(unittest.TestCase):
    def test_perfect_positive(self):
        r, _, _ = pearson_r([1, 2, 3], [2, 4, 6])
        self.assertAlmostEqual(r, 1.0, places=12)

    def test_perfect_negative(self):
        r, _, _ = pearson_r([1, 2, 3], [6, 4, 2])
        self.assertAlmostEqual(r, -1.0, places=12)

    def test_zero_variance(self):
        with self.assertRaises(ValueError):
            pearson_r([5, 5, 5], [1, 2, 3])

    def test_matches_numpy(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy 未安装")

        xs = [0.1, 0.5, 1.2, 2.0, 3.1, 5.0]
        ys = [0.3, 0.2, 1.7, 1.5, 3.9, 4.4]
        r, _, _ = pearson_r(xs, ys)
        self.assertAlmostEqual(r, float(np.corrcoef(xs, ys)[0, 1]), places=12)


class CliTests(unittest.TestCase):
    def test_config_from_other_directory(self):
        config = os.path.join(ROOT, "config.yaml")
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "legacy_corr.py"), "--config", config],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("r = 0.5634747254", result.stdout)

    def test_missing_config_exit_code(self):
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT, "legacy_corr.py"),
                "--config",
                "no_such_config.yaml",
            ],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("错误", result.stderr)


if __name__ == "__main__":
    unittest.main()
