"""vLLM 엔드포인트에 접속할 수 없을 때도 파이프라인이 예외 없이 완주하는지 확인한다."""
from harness import anomaly_judge, pipeline
from harness.llm_client import LLMUnavailable

ROW = dict(
    fact_name="가상사업장 X", model_name="MODEL-N1", group="온도(sub1)", wast_no=1,
    item_code="TON00", n_months_eval=5, n_months_strong=5,
    sep_l2_mean=38.0, sep_l2_max=41.2, excl_margin_mean=70.0, excl_margin_max=80.0,
    chart_evidence="근거 문장",
)


def test_judge_candidate_returns_error_not_exception(monkeypatch):
    def raise_unavailable(*a, **kw):
        raise LLMUnavailable("connection refused")

    monkeypatch.setattr(anomaly_judge, "call_llm_json", raise_unavailable)
    result = anomaly_judge.judge_candidate(ROW)
    assert result["verdict"] is None
    assert result["error"]


def test_pipeline_completes_without_llm_connectivity(monkeypatch, tmp_path):
    def raise_unavailable(*a, **kw):
        raise LLMUnavailable("connection refused")

    monkeypatch.setattr(anomaly_judge, "call_llm_json", raise_unavailable)
    result = pipeline.run(["TON00"], "2026-02-01", "2026-06-30", use_llm=True,
                           out_dir=str(tmp_path))
    assert result["n_candidates"] > 0
    assert result["n_confirmed"] == 0
    assert result["n_normal"] == 0
    assert all(r["status"] == "판정불가(LLM 미접속)" for r in result["pending"])
