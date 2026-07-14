"""[00_input] 입력 검증 — 항목·기간을 확인하고 실행 요청 객체를 만든다."""
from __future__ import annotations

from dataclasses import dataclass

from harness import candidate_scanner


@dataclass
class RunRequest:
    items: list[str]
    sdate: str
    edate: str
    use_llm: bool


def validate(items: list[str], sdate: str, edate: str, use_llm: bool = True) -> RunRequest:
    bad = [it for it in items if it not in candidate_scanner.ITEMS]
    if bad:
        raise ValueError(f"알 수 없는 항목: {bad} (허용: {candidate_scanner.ITEMS})")
    if not (sdate and edate and sdate < edate):
        raise ValueError("sdate < edate 형태의 유효한 기간이 필요합니다.")
    months = candidate_scanner._months()
    overlap = candidate_scanner._overlapping_months(sdate, edate, months)
    if not overlap:
        raise ValueError(
            f"[{sdate}, {edate}) 기간과 겹치는 샘플 데이터가 없습니다. 사용 가능한 월: {months}"
        )
    return RunRequest(items=list(items), sdate=sdate, edate=edate, use_llm=use_llm)


def list_available_months() -> list[str]:
    return candidate_scanner._months()
