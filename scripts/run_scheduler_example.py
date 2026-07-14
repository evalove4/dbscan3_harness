"""자동 실행 예시 코드 — 매일 09:00에 3개 항목(TOC00/TON00/TOP00) × 기간 D-31~D-1로
파이프라인을 실행하는 방법을 보여준다.

**이것은 예시 코드다.** 이 스크립트 자체는 상시 데몬이 아니며 내부에 스케줄 루프가
없다 — 실제로 매일 09:00에 돌리려면 외부 스케줄러(cron 등)에 등록해야 한다.

    0 9 * * * cd /path/to/dbscan3-harness && .venv/bin/python scripts/run_scheduler_example.py

이 예시는 WTMS_REVERSE의 agent.py(실제 운영 스케줄러)와 무관하며, agent.py를
수정하거나 그곳에 등록되지 않는다.

샘플 데이터는 2026-02~06만 담고 있으므로, 오늘 날짜 기준으로 그냥 실행하면 표본
범위 밖이라 후보가 없다. 데모 시에는 --as-of로 표본 범위 안의 날짜를 지정한다.

사용 예:
    python scripts/run_scheduler_example.py --once --as-of 2026-07-01
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import pipeline  # noqa: E402
from harness.candidate_scanner import ITEMS  # noqa: E402


def compute_window(as_of: date) -> tuple[str, str]:
    """D-31 ~ D-1(오늘 자정 기준, edate는 배타적 상한이므로 D-1의 다음날 자정)."""
    d31 = as_of - timedelta(days=31)
    d1 = as_of - timedelta(days=1)
    return d31.isoformat(), (d1 + timedelta(days=1)).isoformat()


def scheduled_job(as_of: date | None = None, use_llm: bool = True) -> list[dict]:
    as_of = as_of or date.today()
    sdate, edate = compute_window(as_of)
    results = []
    for item in ITEMS:
        print(f"=== {item} ({sdate} ~ {edate}) ===")
        results.append(pipeline.run([item], sdate, edate, use_llm=use_llm))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true",
                     help="1회 즉시 실행(이 스크립트는 항상 1회만 실행하며, 이 플래그는 "
                          "실제 크론에 등록해 반복 실행할 의도임을 명시하는 용도)")
    ap.add_argument("--as-of", default=None, help="기준일(YYYY-MM-DD). 생략 시 오늘 날짜.")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    scheduled_job(as_of=as_of, use_llm=not args.no_llm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
