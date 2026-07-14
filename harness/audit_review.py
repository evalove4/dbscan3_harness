"""[03_reviewed] 감사 리뷰 — LLM 판정을 코드로 교차검증한다.

`revfactory/harness-100`의 `28-security-audit` 하네스에서 audit-reviewer가 다른
에이전트들의 결과를 교차검증하고, 불일치("required modification")가 있으면 해당
단계에 재작업을 요청(최대 2회)하는 패턴을 응용했다. 여기서는 두 가지를 검사한다.

1. 수치 환각(check_hallucination): anomaly_judge가 서술한 reason에 등장하는 숫자가
   실제로 판정에 제공된 사실(row) 안에 있는지 재검증한다.
2. 근거-판정 불일치(check_consistency): 결정론적 신호가 매우 강한데 N으로 판정하거나,
   반대로 근거가 약한데 확신도 높게 Y로 판정한 경우를 잡아낸다.

지적사항이 있으면 anomaly_judge에 재판정을 요청한다(최대 max_retry회). 재시도 후에도
해소되지 않으면 판정을 임의로 덮어쓰지 않고 "보류(사람 재검토 필요)"로 남긴다 —
harness-100의 🔴→재작업 패턴을 계승하되, 무한 신뢰 대신 최종적으로는 사람에게 넘긴다.
"""
from __future__ import annotations

import re

from harness import anomaly_judge, config

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_numbers(text: str) -> list[float]:
    return [float(m) for m in _NUM_RE.findall(text)]


def _allowed_numbers(row: dict) -> set[float]:
    """판정에 제공된 사실 수치(반올림 허용) + 자연스럽게 등장할 수 있는 범용값."""
    allowed: set[float] = set()
    for key in ("sep_l2_mean", "sep_l2_max", "excl_margin_mean", "excl_margin_max",
                "n_months_eval", "n_months_strong", "wast_no"):
        v = row.get(key)
        if v is None:
            continue
        for nd in (0, 1, 2):
            allowed.add(round(float(v), nd))
    if row.get("chart_evidence"):
        for n in _extract_numbers(row["chart_evidence"]):
            allowed.add(round(n, 0))
            allowed.add(round(n, 1))
    allowed |= {0.0, 1.0}          # "1건", "0회" 등
    allowed |= set(float(m) for m in range(2, 13))  # 월(2~12)
    allowed.add(2026.0)
    return allowed


def _matches(n: float, allowed: set[float], tol_abs: float = 0.05, tol_rel: float = 0.02) -> bool:
    return any(abs(n - a) <= max(tol_abs, tol_rel * abs(a)) for a in allowed)


def check_hallucination(row: dict, judgment: dict) -> list[str]:
    reason = judgment.get("reason")
    if not reason:
        return []
    allowed = _allowed_numbers(row)
    bad = [n for n in _extract_numbers(reason) if not _matches(n, allowed)]
    if bad:
        return [f"근거 문장에 제공된 사실에 없는 숫자가 포함됨: {bad}"]
    return []


def check_consistency(row: dict, judgment: dict) -> list[str]:
    verdict = judgment.get("verdict")
    if verdict is None:
        return []
    issues = []
    very_strong = (row["n_months_strong"] == row["n_months_eval"]
                   and row["sep_l2_max"] >= 2 * config.STRONG_SEP_L2)
    very_weak = (row["n_months_strong"] <= 1 and row["sep_l2_max"] < 2 * config.STRONG_SEP_L2)
    if very_strong and verdict == "N":
        issues.append(
            f"매우 강한 반복 신호(n_months_strong={row['n_months_strong']}=="
            f"n_months_eval={row['n_months_eval']}, sep_l2_max={row['sep_l2_max']})인데 N으로 판정함"
        )
    if very_weak and verdict == "Y" and judgment.get("confidence") == "상":
        issues.append(
            f"근거가 약한데(강한 개월수={row['n_months_strong']}, sep_l2_max={row['sep_l2_max']}) "
            f"확신도 '상'으로 Y 판정함"
        )
    return issues


def audit_review(row: dict, judgment: dict, max_retry: int = 2) -> dict:
    issues = check_hallucination(row, judgment) + check_consistency(row, judgment)
    retry_count = 0
    while issues and judgment.get("error") is None and retry_count < max_retry:
        judgment = anomaly_judge.judge_candidate(row, retry_note="; ".join(issues))
        issues = check_hallucination(row, judgment) + check_consistency(row, judgment)
        retry_count += 1

    if judgment.get("error") is not None:
        status = "판정불가(LLM 미접속)"
    elif issues:
        status = "보류(사람 재검토 필요)"
    else:
        status = "확정"

    return {**row, **judgment, "status": status, "issues": issues, "retry_count": retry_count}
