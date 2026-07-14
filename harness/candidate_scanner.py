"""[01_candidates] 이격 후보 탐지 — 결정론적 통계 로직.

WTMS_REVERSE(dashboard/dbscan_viewer.py)의 `detect_site_outliers`/`find_persistent_anomalies`를
그대로 이식했다. 계산식(robust z-score, 배타우위, 타모델 거리비, 반복성 필터, 차트 재확인)은
한 줄도 바꾸지 않았다. 바뀐 것은 두 가지뿐이다.

1. 사업장명 조회: 원본은 SQLite `facilities` 테이블을 조회했지만, 이 저장소는 DB 의존성이
   없어야 하므로 샘플 parquet 자체에 미리 조인해둔 `fact_name` 컬럼에서 직접 dict를 만든다.
2. 캐싱: 원본의 `@DASHBOARD_CACHE.memoize`(TTL 캐시, Flask 대시보드용)는 제거했다 — 이
   저장소는 단발성 CLI 프로세스라 캐시가 무의미하다.

원본과 달리 이 하네스는 DBSCAN3 데이터셋 하나만 다루므로, 모든 함수에서 `dataset` 인자를
없앴다(dbscan1/dbscan2 분기 자체가 존재할 필요가 없다).
"""
from __future__ import annotations

import glob
import os
import re

import numpy as np
import pandas as pd

from harness import config

ITEMS = config.ITEMS


def _months() -> list[str]:
    pat = config.DATASET["file_tmpl"].format(tag="*")
    months = []
    for p in sorted(glob.glob(os.path.join(config.DATASET["label_dir"], pat))):
        mtc = re.search(r"(\d{4})_(\d{2})", os.path.basename(p))
        if mtc:
            months.append(f"{mtc.group(1)}-{mtc.group(2)}")
    return sorted(set(months))


def _label_path(month: str) -> str:
    return os.path.join(config.DATASET["label_dir"], config.DATASET["file_tmpl"].format(tag=month.replace("-", "_")))


_FACT_NAME_CACHE: dict[str, str] | None = None


def _fact_name_map() -> dict:
    """샘플 parquet에 미리 조인된 fact_name 컬럼에서 fact_code→fact_name dict를 만든다."""
    global _FACT_NAME_CACHE
    if _FACT_NAME_CACHE is not None:
        return _FACT_NAME_CACHE
    frames = []
    for month in _months():
        p = _label_path(month)
        if os.path.exists(p):
            frames.append(pd.read_parquet(p, columns=["fact_code", "fact_name"]))
    if not frames:
        _FACT_NAME_CACHE = {}
        return _FACT_NAME_CACHE
    df = pd.concat(frames, ignore_index=True).drop_duplicates("fact_code")
    _FACT_NAME_CACHE = df.set_index("fact_code")["fact_name"].to_dict()
    return _FACT_NAME_CACHE


def get_meta() -> dict:
    """월 목록 · 항목별 기기모델 목록(라벨이 실제로 존재하는 것만)."""
    months = _months()
    models_by_item: dict[str, set] = {it: set() for it in ITEMS}
    for month in months:
        p = _label_path(month)
        if not os.path.exists(p):
            continue
        df = pd.read_parquet(p, columns=["item_code", "model_name"])
        for it, sub in df.groupby("item_code"):
            if it in models_by_item:
                models_by_item[it] |= set(sub.model_name.dropna().unique())
    return {"label": config.DATASET["label"], "months": months, "items": ITEMS,
            "models": {it: sorted(v) for it, v in models_by_item.items()}}


def _load_slice(item: str, model: str, month: str) -> pd.DataFrame | None:
    lab = pd.read_parquet(_label_path(month))
    m = lab[(lab.item_code == item) & (lab.model_name == model)].copy()
    if m.empty:
        return None
    m["wast_no"] = m["wast_no"].astype(int)
    return m


def _colors_unused() -> None:  # 원본의 plotly _colors()는 UI 전용이라 제거했다(의존성 없음).
    raise NotImplementedError


META_COLS = ["사업장", "방류구", "측정일시"]


def _series_rows(df: pd.DataFrame, cols: list[str]) -> dict:
    out = {}
    for c in cols:
        if c not in df.columns:
            out[c] = [None] * len(df)
        elif pd.api.types.is_integer_dtype(df[c]):
            out[c] = [None if pd.isna(v) else int(v) for v in df[c]]
        elif pd.api.types.is_numeric_dtype(df[c]):
            out[c] = [None if pd.isna(v) else round(float(v), 4) for v in df[c]]
        else:
            out[c] = [None if pd.isna(v) else str(v) for v in df[c]]
    return out


def build_scatter(item: str, model: str, month: str) -> dict | None:
    """지정한 (항목, 기기모델, 월) 조합의 4패널 산포도 데이터. _chart_evidence가 내부적으로
    쓴다(원본의 PCA/색상 분기는 DBSCAN3에서 쓰이지 않아 제거했다)."""
    if item not in ITEMS:
        raise ValueError(f"알 수 없는 항목: {item}")

    m = _load_slice(item, model, month)
    if m is None or m.empty:
        return None

    panels = config.DATASET["panels"]
    fn_map = _fact_name_map()
    m = m.assign(**{
        "사업장": m.fact_code.map(fn_map).fillna(m.fact_code),
        "방류구": m.wast_no,
        "측정일시": m.measure_time.astype(str),
    })

    feat_cols = sorted({c for xc, yc, _ in panels for c in (xc, yc)})
    if "icpt" in feat_cols and "slop" in feat_cols:
        feat_cols.remove("icpt")
        feat_cols.insert(feat_cols.index("slop") + 1, "icpt")
    tab_cols = META_COLS + feat_cols

    # DBSCAN3의 cluster는 sub1×sub2 조합 ID라 수백 개까지 나올 수 있어(예: 27개×8개),
    # 원본과 동일하게 noise 여부만 구분하고 나머지는 "cluster(전체)" 하나로 묶는다.
    series_list = []
    non_noise = m[m.cluster != -1]
    if len(non_noise):
        series_list.append({"name": "cluster(전체)", "rows": _series_rows(non_noise, tab_cols)})
    noise_sub = m[m.cluster == -1]
    if len(noise_sub):
        series_list.append({"name": "noise", "rows": _series_rows(noise_sub, tab_cols)})

    return {
        "meta": {"item": item, "model": model, "month": month, "n_total": int(len(m)),
                 "n_noise": int(len(noise_sub))},
        "panels": [{"title": title, "x": xc, "y": yc} for xc, yc, title in panels],
        "series": series_list,
    }


# ────────────────────────────────────────────────────────────────
# 사업장 이격 사례 탐지(1차 후보 생성) — 원본 dashboard/dbscan_viewer.py 1:1 이식
# ────────────────────────────────────────────────────────────────

def _outlier_robust_scale(x: np.ndarray) -> tuple[float, float]:
    """MAD 기반 robust 중앙값·표준편차."""
    med = np.nanmedian(x)
    return med, 1.4826 * np.nanmedian(np.abs(x - med))


def _outlier_item_context(df_item: pd.DataFrame, feats: list[str]):
    inst_med = df_item.groupby(["model_name"] + config.OUTLIER_IKEY)[feats].median()
    gscale = {}
    for f in feats:
        _, s = _outlier_robust_scale(inst_med[f].to_numpy(dtype=float))
        gscale[f] = max(s, 1e-9)
    cent = inst_med.groupby("model_name").median()
    n_inst = inst_med.groupby("model_name").size()
    return inst_med, gscale, cent, n_inst


def _outlier_score_group(g: pd.DataFrame, gscale: dict, feats: list[str]) -> pd.DataFrame | None:
    """한 (item, model) 그룹 내 사업장별 분리도(feats 그룹 기준, robust z-score RMS 결합)."""
    cnt = g.groupby(config.OUTLIER_IKEY).size()
    insts = cnt[cnt >= config.OUTLIER_MIN_REC].index
    if len(insts) < config.OUTLIER_MIN_INST:
        return None
    med_i = g.groupby(config.OUTLIER_IKEY)[feats].median()
    rows = []
    for inst in insts:
        others = g[~((g.fact_code == inst[0]) & (g.wast_no == inst[1]))]
        zs = {}
        for f in feats:
            xo = others[f].to_numpy(dtype=float)
            if np.isnan(xo).all() or pd.isna(med_i.loc[inst, f]):
                continue
            mo, so = _outlier_robust_scale(xo)
            denom = max(so, 0.05 * gscale.get(f, 0.0), 0.01 * max(abs(mo), 1e-6), 1e-9)
            zs[f] = min(abs(med_i.loc[inst, f] - mo) / denom, config.OUTLIER_Z_CAP)
        if not zs:
            continue
        z = np.array(list(zs.values()))
        rows.append(dict(
            fact_code=inst[0], wast_no=int(inst[1]), n_rec=int(cnt[inst]),
            sep_l2=round(float(np.sqrt(np.mean(z ** 2))), 2),
            sep_max=round(float(z.max()), 2),
            sep_top_feat=max(zs, key=zs.get),
        ))
    return pd.DataFrame(rows) if rows else None


def _outlier_excl_margins(sc: pd.DataFrame) -> list[float | None]:
    """그룹 내 사업장별 배타우위 = 이 사업장의 sep_l2 / 같은 그룹 다른 사업장들의 중앙값."""
    sep_vals = sc["sep_l2"].to_numpy()
    margins = []
    for i, v in enumerate(sep_vals):
        others = np.delete(sep_vals, i)
        other_med = np.median(others) if len(others) > 0 else 0.0
        margins.append(round(min(v / other_med, config.OUTLIER_MARGIN_CAP), 2) if other_med > 1e-9 else None)
    return margins


def _outlier_cross_model_guess(inst_med, gscale, cent, n_inst, med_row, reg_model, inst, feats: list[str]):
    """가장 가까운 타 모델과 그 거리, 등록 모델까지의 거리(leave-self-out)를 반환한다."""
    def dist(c):
        vals = [((med_row[f] - c[f]) / gscale[f]) ** 2
                for f in feats if pd.notna(med_row[f]) and pd.notna(c[f])]
        return np.sqrt(np.mean(vals)) if vals else np.nan

    best, best_d, reg_d = None, np.inf, np.nan
    for model in cent.index:
        if n_inst[model] < config.OUTLIER_MIN_INST:
            continue
        if model == reg_model:
            own = inst_med.loc[model]
            own_loo = own[~((own.index.get_level_values(0) == inst[0]) &
                            (own.index.get_level_values(1) == inst[1]))]
            reg_d = dist(own_loo.median())
        else:
            d = dist(cent.loc[model])
            if pd.notna(d) and d < best_d:
                best, best_d = model, d
    return (best, round(float(best_d), 2) if np.isfinite(best_d) else None,
            round(float(reg_d), 2) if pd.notna(reg_d) else None)


def _month_bounds(month: str) -> tuple[str, str]:
    y, mo = int(month[:4]), int(month[5:7])
    s = f"{month}-01"
    e = f"{y}-{mo + 1:02d}-01" if mo < 12 else f"{y + 1}-01-01"
    return s, e


def _overlapping_months(sdate: str, edate: str, available_months: list[str]) -> list[tuple[str, str, str]]:
    out = []
    for month in available_months:
        ms, me = _month_bounds(month)
        clip_s, clip_e = max(ms, sdate), min(me, edate)
        if clip_s < clip_e:
            out.append((month, clip_s, clip_e))
    return out


def _load_outlier_bulk(item: str, month: str, clip_s: str, clip_e: str) -> pd.DataFrame | None:
    df = pd.read_parquet(_label_path(month))
    df = df[(df.item_code == item) & (df.measure_time >= clip_s) & (df.measure_time < clip_e)].copy()
    if df.empty:
        return None
    df["wast_no"] = df["wast_no"].astype(int)
    return df


def _outlier_evidence_text(group: str, row: dict) -> str:
    parts = [f"[{group}] 그룹 전체 기준 다른 사업장들 대비 {row['sep_l2']:.1f}배(z-score) 벗어남"
             f"(주 요인: {row['sep_top_feat']})"]
    if row.get("excl_margin") is not None:
        parts.append(f"그룹 내 평범한 사업장들(중앙값)보다 {row['excl_margin']:.1f}배 더 배타적으로 이격")
    if row.get("guess_model") and row.get("dist_ratio") is not None:
        parts.append(f"등록 모델보다 {row['guess_model']} 모델에 {row['dist_ratio']:.1f}배 더 근접")
    return " · ".join(parts) + "."


def detect_site_outliers(item: str, sdate: str, edate: str) -> dict:
    """[item] 안에서 [sdate, edate) 기간 동안, 같은 기기모델 그룹의 다른 사업장들과 비교해
    피처 분포가 이례적으로 이격된 사업장을 찾는다(월별·그룹별 원행 — 반복성 필터 이전)."""
    if item not in ITEMS:
        raise ValueError(f"알 수 없는 항목: {item}")
    if not (sdate and edate and sdate < edate):
        raise ValueError("sdate < edate 형태의 유효한 기간이 필요합니다.")

    fn_map = _fact_name_map()
    out_rows = []
    for month, clip_s, clip_e in _overlapping_months(sdate, edate, _months()):
        bulk = _load_outlier_bulk(item, month, clip_s, clip_e)
        if bulk is None or bulk.empty:
            continue
        for group, feats in config.OUTLIER_FEATURE_GROUPS.items():
            inst_med, gscale, cent, n_inst = _outlier_item_context(bulk, feats)
            for model, g in bulk.groupby("model_name"):
                sc = _outlier_score_group(g, gscale, feats)
                if sc is None:
                    continue
                excl_margins = _outlier_excl_margins(sc)
                for r, excl_margin in zip(sc.itertuples(index=False), excl_margins):
                    inst = (r.fact_code, int(r.wast_no))
                    med_row = inst_med.loc[(model, r.fact_code, inst[1])]
                    guess, gd, rd = _outlier_cross_model_guess(
                        inst_med, gscale, cent, n_inst, med_row, model, inst, feats)
                    ratio = round(rd / gd, 2) if (gd and rd is not None and gd > 0) else None
                    row = dict(
                        month=month, group=group, item_code=item, model_name=str(model),
                        fact_code=str(r.fact_code), fact_name=fn_map.get(r.fact_code, r.fact_code),
                        wast_no=int(r.wast_no), n_rec=int(r.n_rec),
                        sep_l2=float(r.sep_l2), sep_max=float(r.sep_max), sep_top_feat=r.sep_top_feat,
                        excl_margin=excl_margin,
                        guess_model=guess, guess_dist=gd, reg_dist=rd, dist_ratio=ratio,
                    )
                    row["suspect"] = bool(
                        row["sep_l2"] >= 4.0 and (row["excl_margin"] or 0) >= 2.0 and (row["dist_ratio"] or 0) >= 2.0
                    )
                    row["evidence_text"] = _outlier_evidence_text(group, row)
                    out_rows.append(row)

    out_rows.sort(key=lambda r: r["sep_l2"], reverse=True)
    columns = ["month", "group", "item_code", "model_name", "fact_code", "fact_name", "wast_no", "n_rec",
               "sep_l2", "sep_max", "sep_top_feat", "excl_margin",
               "guess_model", "guess_dist", "reg_dist", "dist_ratio", "suspect", "evidence_text"]
    return {"item": item, "sdate": sdate, "edate": edate, "columns": columns, "rows": out_rows}


def _panel_feats_for(group: str, sep_top_feat: str | None = None) -> tuple[str, str] | None:
    feats = config.OUTLIER_FEATURE_GROUPS.get(group, [])
    if len(feats) < 2:
        return None
    real_panels = [(x, y) for x, y, _ in config.DATASET["panels"]]
    candidates = [p for p in real_panels if p[0] in feats and p[1] in feats]
    if sep_top_feat:
        top_match = [p for p in candidates if sep_top_feat in p]
        if top_match:
            return top_match[0]
    if candidates:
        return candidates[0]
    return config.OUTLIER_PANEL_FEATS_OVERRIDE.get(group) or (feats[0], feats[1])


def _chart_evidence(item: str, model: str, fact_name: str, wast_no: int,
                     group: str, month: str, sep_top_feat: str | None = None) -> str | None:
    """산포도 Viewer가 화면에 그리는 것과 동일한 원본 좌표를 다시 불러와, 이 사업장 점들이
    실제로 다른 사업장들과 얼마나 떨어져 있는지를 수치로 설명한다."""
    panel_feats = _panel_feats_for(group, sep_top_feat)
    if panel_feats is None or month is None:
        return None
    scat = build_scatter(item, model, month)
    if scat is None:
        return None
    px, py = panel_feats
    site_pts, other_pts = [], []
    for s in scat["series"]:
        xs, ys = s["rows"].get(px), s["rows"].get(py)
        fac, wast = s["rows"].get("사업장"), s["rows"].get("방류구")
        if xs is None or ys is None or fac is None:
            continue
        for x, y, f, w in zip(xs, ys, fac, wast):
            if x is None or y is None:
                continue
            (site_pts if (f == fact_name and w == wast_no) else other_pts).append((x, y))
    if not site_pts or not other_pts:
        return None
    sx = np.array([p[0] for p in site_pts]); sy = np.array([p[1] for p in site_pts])
    ox = np.array([p[0] for p in other_pts]); oy = np.array([p[1] for p in other_pts])
    other_spread = (ox.std() + oy.std()) / 2 or 1e-9
    dist = float(np.hypot(sx.mean() - ox.mean(), sy.mean() - oy.mean()))
    site_spread = float((sx.std() + sy.std()) / 2)
    return (f"{px}×{py} 패널 {month}월 기준, 이 사업장 점 {len(site_pts)}개의 중심이 나머지 "
            f"사업장 점들의 중심으로부터 (나머지 산포 기준) {dist / other_spread:.1f}배 거리에 "
            f"있고, 자체 산포는 나머지의 {site_spread / other_spread:.1f}배(1 미만이면 자기들끼리 "
            f"뭉쳐 있는 계단식 오프셋, 1을 크게 넘으면 자체적으로도 값이 흔들리는 불안정성 이상).")


def build_candidate_chart(item: str, model: str, group: str, fact_name: str, wast_no: int,
                           month: str | None) -> dict | None:
    """GUI가 후보 하나를 산포도로 보여줄 때 쓰는 좌표 데이터. `_chart_evidence`와 같은
    (item, model, month) 원본 좌표를 다시 불러오되, 거리 요약 문장 대신 그려서 확인할 수 있는
    좌표 목록 그대로를 돌려준다."""
    panel_feats = _panel_feats_for(group)
    if panel_feats is None or month is None:
        return None
    scat = build_scatter(item, model, month)
    if scat is None:
        return None
    px, py = panel_feats
    site_pts, other_pts = [], []
    for s in scat["series"]:
        xs, ys = s["rows"].get(px), s["rows"].get(py)
        fac, wast = s["rows"].get("사업장"), s["rows"].get("방류구")
        if xs is None or ys is None or fac is None:
            continue
        for x, y, f, w in zip(xs, ys, fac, wast):
            if x is None or y is None:
                continue
            (site_pts if (f == fact_name and w == wast_no) else other_pts).append([x, y])
    if not site_pts and not other_pts:
        return None
    return {
        "item": item, "model": model, "group": group, "month": month,
        "fact_name": fact_name, "wast_no": wast_no,
        "x_label": px, "y_label": py,
        "site_points": site_pts, "other_points": other_pts,
    }


def find_persistent_anomalies(item: str, sdate: str, edate: str) -> dict:
    """detect_site_outliers()의 월별·그룹별 원행을 사업장 단위로 집계해, [sdate, edate)
    범위에서 평가 가능했던 달 중 최소 2개월(1개월뿐이면 1개월) 이상 "강한" 조건을 반복적으로
    만족하는 사업장만 남긴다. 이 결과가 이 하네스의 "01_candidates"다."""
    base = detect_site_outliers(item, sdate, edate)
    df = pd.DataFrame(base["rows"])
    empty_cols = ["group", "model_name", "fact_code", "fact_name", "wast_no",
                  "n_months_eval", "n_months_strong", "sep_l2_mean", "sep_l2_max",
                  "excl_margin_mean", "excl_margin_max", "ever_suspect", "chart_evidence", "chart_month"]
    if df.empty:
        return {"item": item, "sdate": sdate, "edate": edate, "n_months_total": 0,
                "min_strong_months": 0, "columns": empty_cols, "rows": []}

    df["is_strong"] = (df.sep_l2 >= config.STRONG_SEP_L2) & (df.excl_margin.fillna(0) >= config.STRONG_EXCL_MARGIN)
    n_months_total = df.month.nunique()
    min_strong = max(1, min(2, n_months_total))

    key = ["group", "model_name", "fact_code", "fact_name", "wast_no"]
    agg = df.groupby(key).agg(
        n_months_eval=("month", "nunique"),
        n_months_strong=("is_strong", "sum"),
        sep_l2_mean=("sep_l2", "mean"), sep_l2_max=("sep_l2", "max"),
        excl_margin_mean=("excl_margin", "mean"), excl_margin_max=("excl_margin", "max"),
        ever_suspect=("suspect", "any"),
    ).reset_index()
    cand = agg[agg.n_months_strong >= min_strong].sort_values(
        ["n_months_strong", "sep_l2_max"], ascending=[False, False]).reset_index(drop=True)

    strong_row = (df[df.is_strong].sort_values("sep_l2", ascending=False)
                  .drop_duplicates(subset=key).set_index(key))
    evidences, chart_months = [], []
    for _, r in cand.iterrows():
        k = tuple(r[c] for c in key)
        sr = strong_row.loc[k] if k in strong_row.index else None
        month = sr["month"] if sr is not None else None
        top_feat = sr["sep_top_feat"] if sr is not None else None
        ev = _chart_evidence(item, r["model_name"], r["fact_name"], int(r["wast_no"]),
                              r["group"], month, top_feat)
        evidences.append(ev or "(2축 산포도 패널이 없어 차트 재확인 생략)")
        chart_months.append(month)
    cand = cand.assign(chart_evidence=evidences, chart_month=chart_months)

    rows = []
    for _, r in cand.iterrows():
        rows.append(dict(
            group=r["group"], model_name=str(r["model_name"]), fact_code=str(r["fact_code"]),
            fact_name=r["fact_name"], wast_no=int(r["wast_no"]),
            n_months_eval=int(r["n_months_eval"]), n_months_strong=int(r["n_months_strong"]),
            sep_l2_mean=round(float(r["sep_l2_mean"]), 2), sep_l2_max=round(float(r["sep_l2_max"]), 2),
            excl_margin_mean=(round(float(r["excl_margin_mean"]), 2) if pd.notna(r["excl_margin_mean"]) else None),
            excl_margin_max=(round(float(r["excl_margin_max"]), 2) if pd.notna(r["excl_margin_max"]) else None),
            ever_suspect=bool(r["ever_suspect"]), chart_evidence=r["chart_evidence"],
            chart_month=r["chart_month"],
        ))
    return {"item": item, "sdate": sdate, "edate": edate, "n_months_total": int(n_months_total),
            "min_strong_months": int(min_strong), "columns": empty_cols, "rows": rows}


def get_outlier_site_records(item: str, model: str, fact_code: str, wast_no: int, month: str) -> dict:
    """디버그/탐색용 보조 유틸: 한 사업장의 그 달 레코드 전체를 반환한다."""
    if item not in ITEMS:
        raise ValueError(f"알 수 없는 항목: {item}")
    m = _load_slice(item, model, month)
    if m is None or m.empty:
        return {"columns": ["측정일시"], "rows": [], "n_total": 0}
    sub = m[(m.fact_code == fact_code) & (m.wast_no == int(wast_no))].sort_values("measure_time")
    if sub.empty:
        return {"columns": ["측정일시"], "rows": [], "n_total": 0}
    feat_cols = sorted({c for xc, yc, _ in config.DATASET["panels"] for c in (xc, yc)})
    if "icpt" in feat_cols and "slop" in feat_cols:
        feat_cols.remove("icpt")
        feat_cols.insert(feat_cols.index("slop") + 1, "icpt")
    columns = ["측정일시"] + feat_cols + ["성향"]
    sub = sub.assign(**{"측정일시": sub.measure_time.astype(str),
                         "성향": np.where(sub.cluster == -1, "noise", "cluster")})
    row_data = _series_rows(sub, columns)
    rows = [{c: row_data[c][i] for c in columns} for i in range(len(sub))]
    return {"columns": columns, "rows": rows, "n_total": len(rows)}
