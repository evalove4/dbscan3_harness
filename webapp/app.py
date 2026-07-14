"""dbscan3-harness GUI — harness/pipeline.run()을 브라우저에서 실행하고 결과를 본다.

이 파일은 오케스트레이션 로직을 새로 만들지 않는다. 기존 harness/pipeline.py의
run()을 그대로 호출하고, outputs/<run_id>/ 산출물 파일을 읽어 보여줄 뿐이다.
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for

from harness import candidate_scanner, config
from harness.pipeline import run as run_pipeline

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-not-for-production")


def _safe_run_dir(run_id: str) -> str:
    """outputs/ 바깥 경로 접근(경로 탈출)을 막는다."""
    if run_id != os.path.basename(run_id) or run_id in ("", ".", ".."):
        abort(404)
    run_dir = os.path.join(OUT_DIR, run_id)
    if not os.path.isdir(run_dir):
        abort(404)
    return run_dir


def _list_runs() -> list[dict]:
    runs = []
    if not os.path.isdir(OUT_DIR):
        return runs
    for name in sorted(os.listdir(OUT_DIR), reverse=True):
        run_dir = os.path.join(OUT_DIR, name)
        report_path = os.path.join(run_dir, "04_report.json")
        if not os.path.isfile(report_path):
            continue
        with open(report_path, encoding="utf-8") as f:
            result = json.load(f)
        runs.append({
            "run_id": name,
            "items": result.get("items", []),
            "sdate": result.get("sdate"),
            "edate": result.get("edate"),
            "n_candidates": result.get("n_candidates", 0),
            "n_confirmed": result.get("n_confirmed", 0),
            "n_normal": result.get("n_normal", 0),
            "n_pending": result.get("n_pending", 0),
        })
    return runs


@app.route("/")
def index():
    months = candidate_scanner._months()
    return render_template(
        "index.html",
        items=candidate_scanner.ITEMS,
        months=months,
        default_sdate=months[0] + "-01" if months else "",
        default_edate=months[-1] + "-28" if months else "",
        runs=_list_runs(),
    )


@app.route("/run", methods=["POST"])
def run_route():
    items = request.form.getlist("items")
    sdate = request.form.get("sdate", "")
    edate = request.form.get("edate", "")
    use_llm = request.form.get("use_llm") == "on"

    if not items:
        flash("항목을 하나 이상 선택하세요.")
        return redirect(url_for("index"))

    try:
        result = run_pipeline(items, sdate, edate, use_llm=use_llm, out_dir=OUT_DIR)
    except ValueError as e:
        flash(f"실행 실패: {e}")
        return redirect(url_for("index"))
    except Exception as e:  # LLM 연결 오류 등 — 파이프라인 자체는 예외 없이 완주해야 정상이지만 방어적으로 처리
        flash(f"파이프라인 실행 중 오류: {e}")
        return redirect(url_for("index"))

    run_id = f"{result['sdate']}_{result['edate']}_{'-'.join(result['items'])}"
    return redirect(url_for("run_detail", run_id=run_id))


@app.route("/runs/<run_id>")
def run_detail(run_id: str):
    run_dir = _safe_run_dir(run_id)
    with open(os.path.join(run_dir, "04_report.json"), encoding="utf-8") as f:
        result = json.load(f)
    ws_dir = os.path.join(run_dir, "_workspace")
    workspace_files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ws_dir, "*.json")))
    return render_template(
        "run_detail.html", run_id=run_id, result=result, workspace_files=workspace_files,
        strong_sep_l2=config.STRONG_SEP_L2, strong_excl_margin=config.STRONG_EXCL_MARGIN,
    )


@app.route("/runs/<run_id>/candidates/<int:idx>/chart")
def candidate_chart(run_id: str, idx: int):
    """산포도 데이터(JSON) — 후보 하나가 실제로 다른 사업장들과 얼마나 떨어져 있는지를
    후보 탐지에 쓰인 것과 같은 원본 좌표(candidate_scanner.build_candidate_chart)로 보여준다."""
    run_dir = _safe_run_dir(run_id)
    reviewed_path = os.path.join(run_dir, "_workspace", "03_reviewed.json")
    if not os.path.isfile(reviewed_path):
        abort(404)
    with open(reviewed_path, encoding="utf-8") as f:
        reviewed = json.load(f)
    row = next((r for r in reviewed if r.get("candidate_idx") == idx), None)
    if row is None:
        abort(404)

    chart = candidate_scanner.build_candidate_chart(
        row["item_code"], row["model_name"], row["group"], row["fact_name"], row["wast_no"],
        row.get("chart_month"),
    )
    if chart is None:
        return jsonify({"error": "이 후보는 산포도로 재확인할 좌표가 없습니다."}), 404
    return jsonify(chart)


@app.route("/runs/<run_id>/workspace/<filename>")
def workspace_file(run_id: str, filename: str):
    run_dir = _safe_run_dir(run_id)
    if filename != os.path.basename(filename) or not filename.endswith(".json"):
        abort(404)
    file_path = os.path.join(run_dir, "_workspace", filename)
    if not os.path.isfile(file_path):
        abort(404)
    with open(file_path, encoding="utf-8") as f:
        content = json.load(f)
    pretty = json.dumps(content, ensure_ascii=False, indent=2)
    return render_template("workspace_file.html", run_id=run_id, filename=filename, content=pretty)


def main() -> int:
    app.run(host="127.0.0.1", port=5000, debug=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
