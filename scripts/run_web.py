"""GUI 실행 진입점 — 브라우저에서 파이프라인을 실행하고 결과를 본다.

사용 예:
    python scripts/run_web.py
    python scripts/run_web.py --port 8080 --no-debug
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webapp.app import app  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="dbscan3-harness GUI 서버")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--no-debug", action="store_true")
    args = ap.parse_args(argv)

    app.run(host=args.host, port=args.port, debug=not args.no_debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
