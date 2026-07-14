"""00_input~04_report 전체 파이프라인이 실제로 파일을 써내는지 확인한다(LLM은 mock)."""
import json
import os

from harness import anomaly_judge, pipeline


def _fixed_judge(row, retry_note=None):
    return {"verdict": "Y", "confidence": "상",
            "reason": "지속적으로 강한 이상 신호가 관측됩니다.", "error": None}


def test_pipeline_writes_expected_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(anomaly_judge, "judge_candidate", _fixed_judge)
    result = pipeline.run(["TON00"], "2026-02-01", "2026-06-30", use_llm=True,
                           out_dir=str(tmp_path))

    run_dir = os.path.join(str(tmp_path), "2026-02-01_2026-06-30_TON00")
    ws_dir = os.path.join(run_dir, "_workspace")
    for name in ("00_input.json", "01_candidates.json", "02_judgments.json", "03_reviewed.json"):
        assert os.path.isfile(os.path.join(ws_dir, name)), name

    report_json = os.path.join(run_dir, "04_report.json")
    report_md = os.path.join(run_dir, "04_report.md")
    assert os.path.isfile(report_json)
    assert os.path.isfile(report_md)

    with open(report_json, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["n_confirmed"] == result["n_confirmed"] == 2  # 가상사업장 G, H

    with open(report_md, encoding="utf-8") as f:
        md = f.read()
    assert "가상사업장 G" in md and "가상사업장 H" in md


def test_pipeline_no_llm_skips_judgment(tmp_path):
    result = pipeline.run(["TOC00"], "2026-02-01", "2026-06-30", use_llm=False,
                           out_dir=str(tmp_path))
    assert result["n_candidates"] == 1
    assert result["pending"][0]["status"] == "판정생략(--no-llm)"
