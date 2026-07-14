"""DBSCAN3 이격 탐지 상수 — WTMS_REVERSE dashboard/dbscan_viewer.py의 값을 그대로 옮겼다.
이 하네스는 dbscan3 전용이므로 dbscan1/dbscan2 관련 키(self_contained, feat_cols,
pca_feats, 색상 등)는 애초에 존재할 필요가 없어 제거했다."""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("HARNESS_DATA_DIR", os.path.join(ROOT, "data", "sample"))
ITEMS = ["TOC00", "TON00", "TOP00"]

DATASET = dict(
    label_dir=DATA_DIR,
    file_tmpl="noise_labels_{tag}_dbscan3.parquet",
    panels=[
        ("mtm2_1_scaled", "mtm2_2_scaled", "mtm2_1_scaled × mtm2_2_scaled (sub1)"),
        ("mtm2_3_scaled", "mtm2_4_scaled", "mtm2_3_scaled × mtm2_4_scaled (sub1)"),
        ("msig_sum_ratio", "msig_max_ratio", "msig_sum_ratio × msig_max_ratio (sub2)"),
        ("icpt", "slop", "icpt × slop (sub2)"),
    ],
    label="DBSCAN3(서브그룹 분리, AND-noise)",
)

# 물리적 성격이 다른 피처를 하나로 섞으면 "무엇이 왜 이격되었는지"가 흐려지므로,
# DBSCAN3가 군집분석 자체를 나눈 경계(온도 sub1 / 신호비율+교정 sub2)를 그대로 따른다.
OUTLIER_FEATURE_GROUPS = {
    "온도(sub1)": ["mtm2_1_scaled", "mtm2_2_scaled", "mtm2_3_scaled", "mtm2_4_scaled"],
    "신호비율_교정(sub2)": ["msig_sum_ratio", "msig_max_ratio", "slop", "icpt"],
}
OUTLIER_PANEL_FEATS_OVERRIDE: dict[str, tuple[str, str]] = {}

OUTLIER_MIN_REC = 100        # 사업장(기기) 최소 레코드 수
OUTLIER_MIN_INST = 3         # 그룹 최소 사업장 수
OUTLIER_Z_CAP = 100.0
OUTLIER_MARGIN_CAP = 1000.0  # 배타우위(excl_margin) 상한 — 분모가 극히 작을 때 폭주 방지
OUTLIER_IKEY = ["fact_code", "wast_no"]

STRONG_SEP_L2 = 4.0       # "강한" 분리도 하한
STRONG_EXCL_MARGIN = 2.0  # "강한" 배타우위 하한(그룹 내 다른 사업장들의 중앙값 대비 최소 2배)
