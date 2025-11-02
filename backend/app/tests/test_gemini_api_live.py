import asyncio
import os

import pytest
from dotenv import load_dotenv
from langchain_core.pydantic_v1 import BaseModel
from langchain_core.tools import tool

from app.services.langchain import gemini_api

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def _require_api_key():
    """Skip the entire module when the Gemini API key is unavailable."""
    load_dotenv()
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY must be set to run live Gemini API tests")


def test_simple_call_returns_expected_text():
    # Prompt keeps response deterministic while still exercising the API.
    result = asyncio.run(
        gemini_api.simple_call(
            "Respond with only the single word integration.",
            temperature=0.0,
        )
    )
    assert isinstance(result, str)
    assert "integration" in result.lower()


def test_chat_call_responds_to_conversation():
    result = asyncio.run(
        gemini_api.chat_call(
            [
                {"role": "system", "content": "You reply concisely."},
                {"role": "user", "content": "Say only the word acknowledged."},
            ],
            temperature=0.0,
        )
    )
    assert isinstance(result, str)
    assert "acknowledged" in result.lower()


@tool
def multiply(a: int, b: int) -> int:
    """Return the product of the two integers."""
    return a * b


def test_call_with_tools_invokes_model():
    response = asyncio.run(
        gemini_api.call_with_tools(
            "If you need to, call the multiply tool to compute 3 * 4 and answer with the result.",
            tools=[multiply],
            temperature=0.0,
        )
    )
    assert hasattr(response, "content")
    # The model may answer directly or request a tool call; make sure one of those happened.
    has_tool_call = bool(getattr(response, "tool_calls", None))
    has_content = bool(response.content and response.content.strip())
    assert has_tool_call or has_content


class WeatherReport(BaseModel):
    city: str
    conditions: str


def test_structured_output_returns_schema_instance():
    result = asyncio.run(
        gemini_api.structured_output(
            "Provide weather info for Paris with conditions set to cloudy.",
            schema=WeatherReport,
            temperature=0.0,
        )
    )
    assert isinstance(result, WeatherReport)
    assert result.city.lower() == "paris"
    assert "cloud" in result.conditions.lower()


def test_json_output_parses_valid_json():
    payload = asyncio.run(
        gemini_api.json_output(
            "Return a JSON object with a single key colors mapped to ['red','blue'].",
            temperature=0.0,
        )
    )
    assert isinstance(payload, dict)
    assert payload.get("colors")
    assert {color.lower() for color in payload["colors"]} >= {"red", "blue"}
