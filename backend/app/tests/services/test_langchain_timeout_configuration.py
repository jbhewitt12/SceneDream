from typing import Any

import pytest
from pydantic import BaseModel

from app.services.langchain import gemini_api, openai_api, xai_api


class _TestSchema(BaseModel):
    value: str


class _FakeResponse:
    def __init__(self, content: Any):
        self.content = content


class _FakeLLM:
    def __init__(self, response: Any):
        self._response = response

    async def ainvoke(self, *_args: Any, **_kwargs: Any) -> Any:
        return self._response

    def bind_tools(self, _tools: list[Any]) -> "_FakeLLM":
        return self

    def with_structured_output(
        self,
        _schema: type[BaseModel],
        method: str | None = None,
    ) -> "_FakeLLM":
        _ = method
        return self


@pytest.mark.anyio("asyncio")
@pytest.mark.parametrize(
    ("function_name", "call_kwargs", "expected_timeout"),
    [
        ("simple_call", {"prompt": "hello"}, 120),
        (
            "chat_call",
            {"messages": [{"role": "user", "content": "hello"}]},
            120,
        ),
        ("call_with_tools", {"prompt": "hello", "tools": []}, 180),
        ("structured_output", {"prompt": "hello", "schema": _TestSchema}, 240),
        ("json_output", {"prompt": "hello"}, 360),
    ],
)
async def test_gemini_functions_apply_expected_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
    function_name: str,
    call_kwargs: dict[str, Any],
    expected_timeout: int,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    response: Any = _FakeResponse("ok")
    if function_name == "structured_output":
        response = _TestSchema(value="ok")
    if function_name == "json_output":
        response = _FakeResponse('{"ok": true}')

    def fake_get_llm(
        _model: str,
        _temperature: float,
        **kwargs: Any,
    ) -> _FakeLLM:
        captured_kwargs.update(kwargs)
        return _FakeLLM(response)

    monkeypatch.setattr(gemini_api, "_get_llm", fake_get_llm)

    function = getattr(gemini_api, function_name)
    await function(**dict(call_kwargs))

    assert captured_kwargs["request_timeout"] == expected_timeout


@pytest.mark.anyio("asyncio")
@pytest.mark.parametrize(
    ("function_name", "call_kwargs", "expected_timeout"),
    [
        ("simple_call", {"prompt": "hello"}, 120),
        (
            "chat_call",
            {"messages": [{"role": "user", "content": "hello"}]},
            120,
        ),
        ("call_with_tools", {"prompt": "hello", "tools": []}, 180),
        ("structured_output", {"prompt": "hello", "schema": _TestSchema}, 240),
        ("json_output", {"prompt": "hello"}, 360),
    ],
)
async def test_openai_functions_apply_expected_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
    function_name: str,
    call_kwargs: dict[str, Any],
    expected_timeout: int,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    response: Any = _FakeResponse("ok")
    if function_name == "structured_output":
        response = _TestSchema(value="ok")
    if function_name == "json_output":
        response = _FakeResponse('{"ok": true}')

    def fake_get_llm(
        _model: str,
        _temperature: float,
        _response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeLLM:
        captured_kwargs.update(kwargs)
        return _FakeLLM(response)

    monkeypatch.setattr(openai_api, "_get_llm", fake_get_llm)

    function = getattr(openai_api, function_name)
    await function(**dict(call_kwargs))

    assert captured_kwargs["request_timeout"] == expected_timeout


def test_openai_get_llm_omits_response_format_when_not_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(openai_api, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    openai_api._get_llm(
        model="gpt-4o-mini",
        temperature=0.0,
        request_timeout=360,
    )

    assert "response_format" not in captured_kwargs
    assert "max_tokens" not in captured_kwargs


def test_openai_get_llm_passes_response_format_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(openai_api, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    openai_api._get_llm(
        model="gpt-4o-mini",
        temperature=0.0,
        response_format={"type": "json_object"},
        request_timeout=360,
    )

    assert captured_kwargs["response_format"] == {"type": "json_object"}
    assert "max_tokens" not in captured_kwargs


def test_gemini_get_llm_omits_max_tokens_when_not_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeChatGoogleGenerativeAI:
        def __init__(self, **kwargs: Any):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(
        gemini_api, "ChatGoogleGenerativeAI", FakeChatGoogleGenerativeAI
    )
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    gemini_api._get_llm(
        model="gemini-2.5-flash-lite",
        temperature=0.0,
        request_timeout=360,
    )

    assert "max_tokens" not in captured_kwargs


def test_xai_api_initializes_chat_openai_with_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs: Any):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(xai_api, "ChatOpenAI", FakeChatOpenAI)

    xai_api.XAIAPI(api_key="test-api-key")

    assert captured_kwargs["request_timeout"] == 240
    assert "max_tokens" not in captured_kwargs
