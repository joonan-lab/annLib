"""API 키 유효성 검증 — 실제 API 호출로 확인"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    ok: bool
    message: str


def validate_openai(api_key: str) -> ValidationResult:
    if not api_key.startswith("sk-"):
        return ValidationResult(False, "OpenAI 키는 'sk-' 로 시작해야 합니다.")
    try:
        from openai import OpenAI, AuthenticationError, APIConnectionError
        client = OpenAI(api_key=api_key)
        client.models.list()
        return ValidationResult(True, "연결 성공")
    except Exception as e:
        msg = str(e)
        if "Incorrect API key" in msg or "401" in msg:
            return ValidationResult(False, "API 키가 올바르지 않습니다.")
        if "connect" in msg.lower() or "network" in msg.lower():
            return ValidationResult(False, "네트워크 오류 — 인터넷 연결을 확인하세요.")
        return ValidationResult(False, f"오류: {msg[:80]}")


def validate_gemini(api_key: str) -> ValidationResult:
    if not api_key.startswith("AIza"):
        return ValidationResult(False, "Gemini 키는 'AIza' 로 시작해야 합니다.")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        list(client.models.list())
        return ValidationResult(True, "연결 성공")
    except Exception as e:
        msg = str(e)
        if "API_KEY_INVALID" in msg or "400" in msg:
            return ValidationResult(False, "API 키가 올바르지 않습니다.")
        return ValidationResult(False, f"오류: {msg[:80]}")


def validate_claude(api_key: str) -> ValidationResult:
    if api_key.startswith("sk-ant-oat"):
        return ValidationResult(
            False,
            "OAuth 토큰입니다. API 키가 아닙니다.\n"
            "console.anthropic.com → API Keys 탭에서 'sk-ant-api003-...' 형태의 키를 발급받으세요.",
        )
    if not api_key.startswith("sk-ant-api"):
        return ValidationResult(False, "Claude API 키는 'sk-ant-api003-' 로 시작해야 합니다.")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        client.models.list()
        return ValidationResult(True, "연결 성공")
    except Exception as e:
        msg = str(e)
        if "401" in msg or "invalid" in msg.lower():
            return ValidationResult(False, "API 키가 올바르지 않습니다.")
        return ValidationResult(False, f"오류: {msg[:80]}")


def validate_llm(provider: str, api_key: str) -> ValidationResult:
    if not api_key:
        return ValidationResult(False, "API 키를 입력해 주세요.")
    fn = {"openai": validate_openai, "gemini": validate_gemini, "claude": validate_claude}
    validator = fn.get(provider)
    if not validator:
        return ValidationResult(False, f"알 수 없는 프로바이더: {provider}")
    return validator(api_key)


def get_provider_hint(provider: str) -> str:
    """학생용 API 키 발급 안내 한 줄 메시지."""
    return {
        "gemini": "Google 계정으로 aistudio.google.com 에서 무료 발급",
        "openai": "platform.openai.com — 크레딧 충전 필요 (ChatGPT 구독과 별개)",
        "claude": "console.anthropic.com — 크레딧 충전 필요 (Claude 구독과 별개)",
    }.get(provider, "")
