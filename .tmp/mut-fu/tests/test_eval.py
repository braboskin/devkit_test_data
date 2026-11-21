import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval as eval_module  # noqa: E402


class EvalTests(unittest.TestCase):
    def test_recall_at_k(self):
        results = [{"doc_id": "a"}, {"doc_id": "b"}]
        self.assertEqual(eval_module.recall_at_k(results, {"b"}, k=2), 1.0)
        self.assertEqual(eval_module.recall_at_k(results, {"b"}, k=1), 0.0)
        self.assertEqual(eval_module.recall_at_k(results, {"c"}, k=2), 0.0)

    def test_reciprocal_rank(self):
        results = [{"doc_id": "a"}, {"doc_id": "b"}]
        self.assertEqual(eval_module.reciprocal_rank(results, {"a"}), 1.0)
        self.assertEqual(eval_module.reciprocal_rank(results, {"b"}), 0.5)
        self.assertEqual(eval_module.reciprocal_rank(results, {"c"}), 0.0)

    def test_percentile(self):
        values = [10, 20, 30, 40]
        self.assertEqual(eval_module.percentile(values, 50), 20)
        self.assertEqual(eval_module.percentile(values, 95), 40)
        self.assertEqual(eval_module.percentile([], 95), 0.0)


if __name__ == "__main__":
    unittest.main()
