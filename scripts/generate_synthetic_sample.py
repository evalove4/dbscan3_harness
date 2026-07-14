"""데모용 샘플 데이터를 합성(synthetic)으로 생성한다.

애초 계획은 WTMS_REVERSE 원본 저장소의 실제 사업장 측정 데이터를 소량 발췌해
샘플로 쓰는 것이었으나, 실제 사업장 식별정보·측정데이터를 외부 공유 가능성이 있는
별도 저장소로 복사하는 시도가 자동 보안 검사(데이터 유출 방지 규칙)에 의해 두 차례
모두 차단되었다("사용자 동의 여부와 무관하게 유출로 간주되어 차단, 우회 불가"). 그래서
이 스크립트는 원본 저장소를 전혀 읽지 않고, 실제 DBSCAN3 이격 사례에서 관찰된 통계적
패턴(반복적으로 강하게 벗어난 사업장 vs 정상 범위 사업장)만 코드로 재현한 가짜 데이터를
새로 만든다. 사업장명도 전부 가상(가상사업장 A/B 등)이다.

이격 탐지 로직(harness/candidate_scanner.py)이 실제로 읽는 컬럼만 채운다:
fact_code, fact_name, wast_no, item_code, measure_time, model_name,
mtm2_1~4_scaled, msig_sum_ratio, msig_max_ratio, slop, icpt, cluster.

사용법:
    python scripts/generate_synthetic_sample.py --out-dir data/sample
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

MONTHS = ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
RECORDS_PER_FACILITY_PER_MONTH = 150  # OUTLIER_MIN_REC(100) 이상

# (item_code, model_name, 그룹, 정상 사업장 수, 이상 사업장 목록) — 시나리오 정의.
# "이상 사업장"은 지정한 피처에서 5개월 내내 정상 사업장들과 뚜렷이 다른 분포를 갖는다.
SCENARIOS = [
    dict(item="TON00", model="MODEL-N1", group="온도(sub1)",
         normal=["가상사업장 A", "가상사업장 B", "가상사업장 C", "가상사업장 D",
                 "가상사업장 E", "가상사업장 F"],
         anomaly=["가상사업장 G", "가상사업장 H"],  # 플래그십: 2곳 동시 이상, 5개월 내내 강한 신호
         anomaly_months=[0, 1, 2, 3, 4]),
    dict(item="TOC00", model="MODEL-C1", group="신호비율_교정(sub2)",
         normal=["가상사업장 I", "가상사업장 J", "가상사업장 K"],
         anomaly=["가상사업장 L"],  # 교육적 사례: 통계적으로는 튀지만 2개월만 강한 신호(간헐적)
         anomaly_months=[1, 3]),
    dict(item="TOP00", model="MODEL-P1", group="신호비율_교정(sub2)",
         normal=["가상사업장 M", "가상사업장 N", "가상사업장 Q", "가상사업장 R",
                 "가상사업장 S", "가상사업장 T"],
         anomaly=["가상사업장 O", "가상사업장 P"],  # 2곳 동시 이상(정상 다수 대비 소수)
         anomaly_months=[0, 1, 2, 3, 4]),
]


def _facility_rows(rng: np.random.Generator, fact_name: str, item: str, model: str,
                    group: str, month: str, is_anomaly_this_month: bool) -> pd.DataFrame:
    n = RECORDS_PER_FACILITY_PER_MONTH
    y, mo = int(month[:4]), int(month[5:7])
    base_time = datetime(y, mo, 1)
    times = [base_time + timedelta(minutes=15 * i) for i in range(n)]

    if group == "온도(sub1)":
        center = 0.85 if is_anomaly_this_month else 0.50
        noise = 0.04
        mtm2 = {f"mtm2_{i}_scaled": np.clip(rng.normal(center, noise, n), 0, 1.2) for i in range(1, 5)}
        msig_sum_ratio = rng.normal(0.5, 0.03, n)
        msig_max_ratio = rng.normal(0.5, 0.03, n)
        slop = rng.normal(1.0, 0.01, n)
        icpt = rng.normal(0.0, 0.01, n)
    else:  # 신호비율_교정(sub2)
        center = 3.5 if is_anomaly_this_month else 0.0
        mtm2 = {f"mtm2_{i}_scaled": np.clip(rng.normal(0.5, 0.04, n), 0, 1.2) for i in range(1, 5)}
        msig_sum_ratio = rng.normal(0.5 + center * 0.15, 0.05, n)
        msig_max_ratio = rng.normal(0.5 + center * 0.15, 0.05, n)
        slop = rng.normal(1.0 + center * 0.02, 0.015, n)
        icpt = rng.normal(0.0 + center * 0.02, 0.015, n)

    df = pd.DataFrame({
        "fact_code": fact_name.replace(" ", "_"),
        "fact_name": fact_name,
        "wast_no": 1,
        "item_code": item,
        "model_name": model,
        "measure_time": [t.strftime("%Y-%m-%d %H:%M:%S") for t in times],
        **mtm2,
        "msig_sum_ratio": msig_sum_ratio,
        "msig_max_ratio": msig_max_ratio,
        "slop": slop,
        "icpt": icpt,
        "cluster": -1 if is_anomaly_this_month else 0,
    })
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "..", "data", "sample"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    for mi, month in enumerate(MONTHS):
        frames = []
        for sc in SCENARIOS:
            for fac in sc["normal"]:
                frames.append(_facility_rows(rng, fac, sc["item"], sc["model"], sc["group"], month, False))
            for fac in sc["anomaly"]:
                is_anom = mi in sc["anomaly_months"]
                frames.append(_facility_rows(rng, fac, sc["item"], sc["model"], sc["group"], month, is_anom))
        df = pd.concat(frames, ignore_index=True)
        dst = os.path.join(out_dir, f"noise_labels_{month.replace('-', '_')}_dbscan3.parquet")
        df.to_parquet(dst, index=False)
        print(f"{month}: {len(df):,} rows -> {dst}")


if __name__ == "__main__":
    main()
