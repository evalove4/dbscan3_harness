"""오케스트레이터 — 00_input → 01_candidates → 02_judgments → 03_reviewed → 04_report
순서로 산출물 파일을 만든다(`revfactory/harness-100`의 번호매김 산출물 컨벤션을 그대로
채택했다). Input → Process(candidate-scanner + anomaly-judge) → Verify(audit-review) →
Output(report) 흐름이 이 함수 하나에 순서대로 드러난다."""
from __future__ import annotations

import argparse
import json
import os

from harness import anomaly_judge, audit_review, candidate_scanner, input_stage, report


def _dump(ws_dir: str, name: str, data) -> None:
    with open(os.path.join(ws_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def run(items: list[str], sdate: str, edate: str, *, use_llm: bool = True,
        out_dir: str = "outputs") -> dict:
    req = input_stage.validate(items, sdate, edate, use_llm)  # 00_input

    run_id = f"{req.sdate}_{req.edate}_{'-'.join(req.items)}"
    run_dir = os.path.join(out_dir, run_id)
    ws_dir = os.path.join(run_dir, "_workspace")
    os.makedirs(ws_dir, exist_ok=True)
    _dump(ws_dir, "00_input.json", {"items": req.items, "sdate": req.sdate,
                                     "edate": req.edate, "use_llm": req.use_llm})

    # 01_candidates — candidate-scanner(결정론적 통계 후보 탐지)
    candidates = []
    for item in req.items:
        base = candidate_scanner.find_persistent_anomalies(item, req.sdate, req.edate)
        for row in base["rows"]:
            row["item_code"] = item
            candidates.append(row)
    _dump(ws_dir, "01_candidates.json", candidates)
    print(f"[01_candidates] {len(candidates)}건")

    # 02_judgments — anomaly-judge(LLM 판정) / 03_reviewed — audit-review(교차검증+재판정)
    reviewed = []
    for row in candidates:
        if req.use_llm:
            judgment = anomaly_judge.judge_candidate(row)
            reviewed.append(audit_review.audit_review(row, judgment))
        else:
            reviewed.append({**row, "verdict": None, "confidence": None, "reason": None,
                              "error": None, "status": "판정생략(--no-llm)", "issues": [],
                              "retry_count": 0})
    _dump(ws_dir, "02_judgments.json", [
        {"fact_name": r["fact_name"], "verdict": r.get("verdict"),
         "confidence": r.get("confidence"), "reason": r.get("reason")} for r in reviewed
    ])
    _dump(ws_dir, "03_reviewed.json", reviewed)

    # 04_report — report(확정/정상/보류 3분류)
    result = report.build_result(req.items, req.sdate, req.edate, reviewed)
    json_path, md_path = report.write_report(result, run_dir)
    report.print_summary(result)
    print(f"[04_report] {json_path}\n[04_report] {md_path}")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="이상 사업장 이격 사례 탐지 파이프라인(수동 실행)")
    ap.add_argument("--item", action="append", required=True, dest="items",
                     help="TOC00/TON00/TOP00 중 하나, 여러 번 지정 가능")
    ap.add_argument("--sdate", required=True)
    ap.add_argument("--edate", required=True)
    ap.add_argument("--no-llm", action="store_true", help="LLM 판정 단계를 건너뛰고 후보만 확인")
    ap.add_argument("--out-dir", default="outputs")
    args = ap.parse_args(argv)

    run(args.items, args.sdate, args.edate, use_llm=not args.no_llm, out_dir=args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
