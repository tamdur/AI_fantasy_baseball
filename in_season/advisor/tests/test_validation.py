"""Phase-2 §7: calibration reliability scoring (pure)."""

from advisor import validation as V


def test_reliability_perfectly_calibrated():
    # 100 predictions at p=0.7 with exactly 70 wins -> well-calibrated bin.
    pairs = [(0.7, True)] * 70 + [(0.7, False)] * 30
    rep = V.reliability(pairs)
    assert rep["n"] == 100
    bin70 = [b for b in rep["bins"] if b["lo"] == 0.7][0]
    assert abs(bin70["observed"] - 0.70) < 1e-9
    assert abs(rep["brier"] - 0.21) < 1e-9          # 0.7*0.09 + 0.3*0.49


def test_reliability_detects_miscalibration():
    # Claims 0.9 but only wins half the time -> large calibration error.
    pairs = [(0.9, i % 2 == 0) for i in range(100)]
    rep = V.reliability(pairs)
    assert rep["calibration_error"] > 0.3
    assert rep["n"] == 100


def test_reliability_empty():
    rep = V.reliability([])
    assert rep["n"] == 0 and rep["brier"] is None
    assert "no data" in V.format_report(rep)


def test_pairs_from_predictions_joins_on_period_and_cat():
    preds = [{"matchup_period": "1", "category": "HR", "predicted_p_win": "0.8"},
             {"matchup_period": "1", "category": "ERA", "predicted_p_win": "0.4"},
             {"matchup_period": "2", "category": "HR", "predicted_p_win": "0.6"}]
    actuals = [{"matchup_period": "1", "category": "HR", "result": "W"},
               {"matchup_period": "1", "category": "ERA", "result": "L"}]
    pairs = V.pairs_from_predictions(preds, actuals)
    assert (0.8, True) in pairs and (0.4, False) in pairs
    assert len(pairs) == 2          # MP2 has no actual -> dropped
