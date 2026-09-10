import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts/acquire_btc_carry_data.py"
SPEC = importlib.util.spec_from_file_location("carry_acquisition", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CarryDataAcquisitionTests(unittest.TestCase):
    def test_expected_sidecar_digest(self):
        digest = "a" * 64
        payload = f"{digest}  BTCUSDT-1h-2020-01.zip\n".encode()
        self.assertEqual(MODULE.expected_sidecar_digest(payload, "BTCUSDT-1h-2020-01.zip"), digest)

    def test_sidecar_filename_must_match(self):
        with self.assertRaises(ValueError):
            MODULE.expected_sidecar_digest(("a" * 64 + "  wrong.zip\n").encode(), "right.zip")

    def test_archive_routes(self):
        url, filename = MODULE.archive_url("markPriceKlines", 2020, 1)
        self.assertEqual(filename, "BTCUSDT-1h-2020-01.zip")
        self.assertTrue(url.endswith("/markPriceKlines/BTCUSDT/1h/BTCUSDT-1h-2020-01.zip"))
        funding_url, funding_file = MODULE.archive_url("fundingRate", 2020, 1)
        self.assertEqual(funding_file, "BTCUSDT-fundingRate-2020-01.zip")
        self.assertTrue(funding_url.endswith("/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2020-01.zip"))

    def test_allowlist_rejects_http_and_credentials(self):
        allowed = {"data.binance.vision"}
        with self.assertRaises(ValueError):
            MODULE.allowed_url("http://data.binance.vision/file", allowed)
        with self.assertRaises(ValueError):
            MODULE.allowed_url("https://user:pass@data.binance.vision/file", allowed)


if __name__ == "__main__":
    unittest.main()
