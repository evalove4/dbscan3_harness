"""[04_report] 최종 리포트 조립 — 확정 이상 / 정상 판정 / 보류 3분류."""
from __future__ import annotations

import json
import os


def build_result(items: list[str], sdate: str, edate: str, reviewed_rows: list[dict]) -> dict:
    confirmed = [r for r in reviewed_rows if r["status"] == "확정" and r.get("verdict") == "Y"]
    normal = [r for r in reviewed_rows if r["status"] == "확정" and r.get("verdict") == "N"]
    pending = [r for r in reviewed_rows if r["status"] not in ("확정",)]
    return {
        "items": items, "sdate": sdate, "edate": edate,
        "n_candidates": len(reviewed_rows),
        "n_confirmed": len(confirmed), "n_normal": len(normal), "n_pending": len(pending),
        "confirmed": confirmed, "normal": normal, "pending": pending,
    }


def _row_line(r: dict) -> str:
    reason = r.get("reason") or r.get("evidence_text") or "(근거 없음)"
    return (f"- **{r['fact_name']}**({r['model_name']}, {r['group']}, {r.get('item_code')}) "
            f"— {reason} [확신도: {r.get('confidence')}]")


def to_markdown(result: dict) -> str:
    lines = [
        "# 이상 사업장 이격 사례 탐지 리포트",
        "",
        f"- 항목: {', '.join(result['items'])}",
        f"- 기간: {result['sdate']} ~ {result['edate']}",
        f"- 통계 후보 {result['n_candidates']}건 → 확정 이상 {result['n_confirmed']}건 / "
        f"정상 판정 {result['n_normal']}건 / 보류 {result['n_pending']}건",
        "",
        "## 확정 이상 사업장 (LLM 판정 Y, 감사 리뷰 통과)",
    ]
    lines += [_row_line(r) for r in result["confirmed"]] or ["(없음)"]
    lines += ["", "## 정상 판정 (통계상 후보였으나 LLM이 정상 편차로 판정)"]
    lines += [_row_line(r) for r in result["normal"]] or ["(없음)"]
    lines += ["", "## 판정 보류/불가 (사람 재검토 필요)"]
    if result["pending"]:
        for r in result["pending"]:
            lines.append(
                f"- **{r['fact_name']}**({r['model_name']}) — status={r['status']}, "
                f"issues={r.get('issues')}"
            )
    else:
        lines.append("(없음)")
    return "\n".join(lines) + "\n"


def write_report(result: dict, out_dir: str) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "04_report.json")
    md_path = os.path.join(out_dir, "04_report.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(result))
    return json_path, md_path


def print_summary(result: dict) -> None:
    print(f"통계 후보 {result['n_candidates']}건 -> 확정 이상 {result['n_confirmed']}건 / "
          f"정상 판정 {result['n_normal']}건 / 보류 {result['n_pending']}건")
