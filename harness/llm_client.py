"""독립 vLLM(gemma-4-text) REST 클라이언트.

WTMS_REVERSE의 llmapi 패키지를 import하지 않는다 — 이 저장소는 완전히 독립적이어야
한다. `llmapi/_daily_inspect4_gemma4_only_agent.py::_call_llm`의 OpenAI 호환
`/v1/chat/completions` 호출 방식과 환경변수 이름(VLLM_BASE_URL/VLLM_MODEL)만 참고했다.
이 하네스의 LLM 역할은 "이미 계산된 사실을 보고 판정·서술"뿐이라 도구 호출(function
calling)이 필요 없어, 원본의 ReAct 도구 루프는 가져오지 않았다.
"""
from __future__ import annotations

import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000").rstrip("/")
VLLM_MODEL = os.getenv("VLLM_MODEL", "gemma-4-text")
VLLM_TIMEOUT_S = float(os.getenv("VLLM_TIMEOUT_S", "20"))


class LLMUnavailable(Exception):
    """vLLM 엔드포인트에 접속할 수 없거나 응답을 이해할 수 없을 때 발생한다.
    호출자는 반드시 이 예외를 잡아 결정론적 폴백 경로로 넘어가야 한다."""


def call_llm(system_prompt: str, user_prompt: str, *, temperature: float = 0.0,
             max_tokens: int = 500) -> str:
    """단일 /v1/chat/completions 호출. assistant 메시지의 content(문자열)를 반환한다."""
    payload = {
        "model": VLLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{VLLM_BASE_URL}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json=payload, timeout=VLLM_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise LLMUnavailable(str(e)) from e

    choices = data.get("choices") or []
    if not choices:
        raise LLMUnavailable("빈 응답(choices 없음)")
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise LLMUnavailable("빈 응답(content 없음)")
    return content


def call_llm_json(system_prompt: str, user_prompt: str, **kwargs) -> dict:
    """call_llm을 호출하고 응답을 JSON으로 파싱한다. 모델이 코드블록(```json ... ```)으로
    감싸거나 앞뒤에 설명을 붙이는 경우를 대비해 가장 바깥 {...} 구간만 추출해 재시도한다."""
    text = call_llm(system_prompt, user_prompt, **kwargs)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise LLMUnavailable(f"JSON 파싱 실패: {text[:200]!r}")
