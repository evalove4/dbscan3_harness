"""candidate_scanner가 data/sample의 합성 시나리오를 정확히 재현하는지 확인한다.
LLM/네트워크가 전혀 필요 없다 — 항상 결정론적으로 통과해야 한다."""
import pytest

from harness import candidate_scanner as cs


def test_ton00_flagship_persists_5_months():
    res = cs.find_persistent_anomalies("TON00", "2026-02-01", "2026-06-30")
    by_name = {r["fact_name"]: r for r in res["rows"]}
    assert {"가상사업장 G", "가상사업장 H"} <= set(by_name)
    for name in ("가상사업장 G", "가상사업장 H"):
        assert by_name[name]["n_months_strong"] == 5
        assert by_name[name]["n_months_eval"] == 5
        assert by_name[name]["sep_l2_max"] > 4.0
        assert by_name[name]["excl_margin_max"] > 2.0


def test_toc00_intermittent_case_not_fully_persistent():
    res = cs.find_persistent_anomalies("TOC00", "2026-02-01", "2026-06-30")
    by_name = {r["fact_name"]: r for r in res["rows"]}
    assert "가상사업장 L" in by_name
    row = by_name["가상사업장 L"]
    assert row["n_months_strong"] < row["n_months_eval"]
    assert row["sep_l2_max"] > 4.0  # 통계적으로는 튄다


def test_top00_dual_anomaly_both_flagged():
    res = cs.find_persistent_anomalies("TOP00", "2026-02-01", "2026-06-30")
    names = {r["fact_name"] for r in res["rows"]}
    assert {"가상사업장 O", "가상사업장 P"} <= names


def test_normal_facilities_are_not_candidates():
    res = cs.find_persistent_anomalies("TON00", "2026-02-01", "2026-06-30")
    names = {r["fact_name"] for r in res["rows"]}
    assert "가상사업장 A" not in names  # 정상 사업장은 후보로 나오면 안 됨


def test_unknown_item_raises():
    with pytest.raises(ValueError):
        cs.find_persistent_anomalies("XXXXX", "2026-02-01", "2026-06-30")


def test_invalid_date_range_raises():
    with pytest.raises(ValueError):
        cs.detect_site_outliers("TON00", "2026-06-30", "2026-02-01")


def test_chart_evidence_present_for_candidates():
    res = cs.find_persistent_anomalies("TON00", "2026-02-01", "2026-06-30")
    for row in res["rows"]:
        assert row["chart_evidence"]
        assert "mtm2" in row["chart_evidence"]
