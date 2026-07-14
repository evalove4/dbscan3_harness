"""[02_judgments] LLM 판정 — 후보가 실제 이상 사업장인지 스스로 판단한다.

WTMS_REVERSE의 daily_inspect5E(`_enrich`)는 "판단은 절대 바꾸지 마세요"가 원칙이었지만,
이 하네스는 사용자 요청에 따라 의도적으로 판정 권한을 LLM에 위임한다 — 결정론적 후보
탐지(candidate_scanner)만으로는 후보가 너무 많아(항목당 수십 건) 사람이 다 검토하기
어렵기 때문이다. 대신 사실(수치)은 100% 결정론적 계산 결과만 주입하고, 근거 없는
숫자를 지어내면 안 된다고 명시한다 — 이 약속이 지켜졌는지는 audit_review.py가
재검증한다.

이 샘플 데이터는 항목당 기기모델을 하나만 담고 있어(교차 모델 비교 불가), dist_ratio·
suspect 플래그가 항상 신뢰할 수 없다. 그래서 판정 근거는 sep_l2·excl_margin·반복
개월수(n_months_strong)를 중심으로 제시하고, dist_ratio·suspect는 "참고용, 이 샘플에서는
교차 모델 비교 불가"라고 명시해 LLM이 그 필드에 과도한 의미를 부여하지 않게 한다.
"""
from __future__ import annotations

from harness.llm_client import LLMUnavailable, call_llm_json

JUDGE_SYSTEM_PROMPT = """당신은 수질 원격감시 이상 사업장 판정관입니다.

아래는 결정론적 통계 알고리즘이 이미 계산한 사실입니다(분리도 sep_l2, 배타우위
excl_margin, 반복 개월수, 차트 재확인 근거). 이 사업장이 실제로 이상(비정상) 사업장인지,
통계적으로는 튀어도 설명 가능한 정상 범위의 편차인지 스스로 판단하세요.

규칙:
1. 제시된 수치 외의 사실(새로운 숫자·시각·사업장명)을 지어내지 마세요.
2. dist_ratio·suspect 필드가 null이거나 "참고불가"로 표시되어 있으면, 그 필드는
   무시하고 sep_l2·excl_margin·반복 개월수만으로 판단하세요.
3. 5개월 내내(n_months_strong == n_months_eval) 강한 신호가 반복되면 실제 이상일
   가능성이 높고, 1~2개월만 간헐적으로 튀면 일시적 편차일 가능성도 함께 고려하세요.
4. 반드시 아래 JSON 형식으로만 응답하세요(다른 텍스트를 덧붙이지 마세요):
{"verdict": "Y 또는 N", "confidence": "상 또는 중 또는 하", "reason": "두세 문장 한국어 설명"}
"""


def _facts_block(row: dict) -> str:
    dist_note = "참고불가(이 샘플은 교차 모델 비교용 다른 모델 데이터가 없음)"
    lines = [
        f"항목: {row.get('item_code', row.get('item'))}",
        f"기기모델: {row['model_name']}",
        f"피처 그룹: {row['group']}",
        f"사업장: {row['fact_name']} (방류구 {row['wast_no']})",
        f"평가 가능 개월수: {row['n_months_eval']}",
        f"강한 신호를 보인 개월수: {row['n_months_strong']}",
        f"분리도(sep_l2) 평균/최대: {row['sep_l2_mean']} / {row['sep_l2_max']}",
        f"배타우위(excl_margin) 평균/최대: {row.get('excl_margin_mean')} / {row.get('excl_margin_max')}",
        f"과거 1차 통계 판정(suspect) 이력: {row.get('ever_suspect')} ({dist_note})",
        f"차트 재확인 근거: {row.get('chart_evidence')}",
    ]
    return "\n".join(lines)


def judge_candidate(row: dict, retry_note: str | None = None) -> dict:
    """row = find_persistent_anomalies의 한 행(사실 근거만). retry_note가 있으면
    audit_review 단계의 재판정 요청 지적사항을 프롬프트에 덧붙인다.

    반환: {"verdict": "Y"|"N"|None, "confidence": str|None, "reason": str|None,
           "error": str|None}
    LLM 미접속/파싱 실패는 예외를 던지지 않고 error 필드로 표시한다(파이프라인이
    계속 진행되어야 하므로)."""
    prompt = _facts_block(row)
    if retry_note:
        prompt += (
            f"\n\n[재판정 요청] 이전 판정에 다음과 같은 지적사항이 있었습니다. "
            f"이를 반영해 다시 판단하세요: {retry_note}"
        )
    try:
        result = call_llm_json(JUDGE_SYSTEM_PROMPT, prompt)
    except LLMUnavailable as e:
        return {"verdict": None, "confidence": None, "reason": None, "error": str(e)}

    verdict = result.get("verdict")
    if verdict not in ("Y", "N"):
        return {"verdict": None, "confidence": None, "reason": None,
                "error": f"판정값이 Y/N이 아님: {verdict!r}"}
    return {
        "verdict": verdict,
        "confidence": result.get("confidence"),
        "reason": result.get("reason"),
        "error": None,
    }
