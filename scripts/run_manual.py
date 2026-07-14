"""수동 실행 진입점 — 항목과 기간을 지정해 파이프라인을 1회 실행한다.

사용 예:
    python scripts/run_manual.py --item TON00 --sdate 2026-02-01 --edate 2026-06-30
    python scripts/run_manual.py --item TON00 --item TOC00 --item TOP00 \
        --sdate 2026-02-01 --edate 2026-06-30 --no-llm
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness.pipeline import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
