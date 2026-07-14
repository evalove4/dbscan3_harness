"""audit_review의 환각 검사·불일치 검사·재판정 로직 단위 테스트. LLM 호출은 전부
monkeypatch로 대체해 네트워크 없이 실행된다."""
from harness import anomaly_judge, audit_review as ar

ROW = dict(
    fact_name="가상사업장 X", model_name="MODEL-N1", group="온도(sub1)", wast_no=1,
    n_months_eval=5, n_months_strong=5,
    sep_l2_mean=38.0, sep_l2_max=41.2,
    excl_margin_mean=70.0, excl_margin_max=80.0,
    chart_evidence="mtm2_1_scaled×mtm2_2_scaled 패널 기준, 중심 거리 3.3배, 자체 산포 0.3배.",
)


def test_check_hallucination_flags_unsupported_number():
    judgment = {"verdict": "Y", "confidence": "상", "reason": "분리도가 123.4배입니다.", "error": None}
    issues = ar.check_hallucination(ROW, judgment)
    assert issues and "123.4" in issues[0]


def test_check_hallucination_accepts_grounded_numbers():
    judgment = {"verdict": "Y", "confidence": "상",
                "reason": "5개월 내내 강한 신호이며 분리도 41.2, 배타우위 80.0, 중심거리 3.3배입니다.",
                "error": None}
    assert ar.check_hallucination(ROW, judgment) == []


def test_check_consistency_flags_strong_signal_verdict_n():
    judgment = {"verdict": "N", "confidence": "중", "reason": "근거 부족", "error": None}
    issues = ar.check_consistency(ROW, judgment)
    assert issues and "N으로 판정" in issues[0]


def test_check_consistency_flags_weak_signal_high_confidence_y():
    weak_row = {**ROW, "n_months_strong": 1, "sep_l2_max": 4.5, "excl_margin_max": 2.1}
    judgment = {"verdict": "Y", "confidence": "상", "reason": "조금 튐", "error": None}
    issues = ar.check_consistency(weak_row, judgment)
    assert issues and "확신도 '상'" in issues[0]


def test_audit_review_self_corrects_on_retry(monkeypatch):
    calls = {"n": 0}

    def fake_judge(row, retry_note=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"verdict": "Y", "confidence": "상", "reason": "분리도가 999.9배.", "error": None}
        return {"verdict": "Y", "confidence": "상", "reason": "5개월 내내 지속됩니다.", "error": None}

    monkeypatch.setattr(anomaly_judge, "judge_candidate", fake_judge)
    first = fake_judge(ROW)
    result = ar.audit_review(ROW, first)
    assert result["status"] == "확정"
    assert result["retry_count"] == 1
    assert calls["n"] == 2


def test_audit_review_gives_up_after_max_retry(monkeypatch):
    def always_hallucinating(row, retry_note=None):
        return {"verdict": "Y", "confidence": "상", "reason": "분리도가 999.9배.", "error": None}

    monkeypatch.setattr(anomaly_judge, "judge_candidate", always_hallucinating)
    result = ar.audit_review(ROW, always_hallucinating(ROW), max_retry=2)
    assert result["status"] == "보류(사람 재검토 필요)"
    assert result["retry_count"] == 2


def test_audit_review_llm_unreachable_short_circuits():
    judgment = {"verdict": None, "confidence": None, "reason": None, "error": "llm_unreachable"}
    result = ar.audit_review(ROW, judgment)
    assert result["status"] == "판정불가(LLM 미접속)"
    assert result["retry_count"] == 0
