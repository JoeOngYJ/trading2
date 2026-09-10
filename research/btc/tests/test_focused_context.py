import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts/validate_btc_focused_context.py"
SPEC = importlib.util.spec_from_file_location("focused_context", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FocusedContextTests(unittest.TestCase):
    def test_current_context_passes(self):
        result = MODULE.validate()
        self.assertEqual(result["status"], "context_valid")
        self.assertEqual(result["actionable_arm_id"], "no_trade")
        self.assertIsNone(result["active_experiment"])

    def test_decision_log_chain_passes(self):
        count, digest = MODULE.validate_decision_log(MODULE.ROOT / "research/btc/DECISIONS.jsonl")
        index = MODULE.load_canonical(MODULE.INDEX_PATH)
        self.assertGreaterEqual(count, 13)
        self.assertEqual(digest, index["latest_decision_digest"])


if __name__ == "__main__":
    unittest.main()
