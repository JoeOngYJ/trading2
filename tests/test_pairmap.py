import pytest

from trading_platform.pairmap import PairMap


def test_pair_map_is_explicit_and_bidirectional():
    mapping = PairMap({"BTC-USD": "BTC/USDT"})
    assert mapping.pair_for("BTC-USD") == "BTC/USDT"
    assert mapping.symbol_for("BTC/USDT") == "BTC-USD"
    with pytest.raises(ValueError, match="unmapped"):
        mapping.pair_for("BTC/USDT")


def test_duplicate_pair_mapping_is_rejected():
    with pytest.raises(ValueError, match="one-to-one"):
        PairMap({"BTC-USD": "BTC/USDT", "BTC-USDT": "BTC/USDT"})

